"""Gravação de tela: ffmpeg (X11) ou portal + GStreamer (Wayland)."""
import os
import shutil
import signal
import subprocess
import tempfile
import time

import cairo
from gi.repository import Gdk, GLib, GObject, Gtk, Pango, PangoCairo

from . import paths, utils
from .icons import Icon, rounded_rect

QUALITY_X264 = {"high": 18, "medium": 23, "low": 28}
QUALITY_VP9 = {"high": 24, "medium": 32, "low": 40}


def _logical(rect, scale):
    return tuple(int(round(v / scale)) for v in rect)


def _monitor_for(x, y):
    display = Gdk.Display.get_default()
    mon = display.get_monitor_at_point(int(x), int(y)) or display.get_monitor(0)
    g = mon.get_geometry()
    return g.x, g.y, g.width, g.height


# --------------------------------------------------------------------- OSDs
class Countdown(Gtk.Window):
    """Contagem regressiva grande no centro da área a ser gravada."""

    def __init__(self, seconds, rect, on_done):
        super().__init__(type=Gtk.WindowType.POPUP)
        self.remaining = seconds
        self.on_done = on_done
        self.caption = "Iniciando gravação"
        self._source = 0
        size = 150
        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        self._rgba = bool(visual and screen.is_composited())
        if self._rgba:
            self.set_visual(visual)
        self.set_app_paintable(True)
        self.set_default_size(size, size)
        x, y, w, h = rect
        self.move(x + (w - size) // 2, y + (h - size) // 2)
        self.connect("draw", self._on_draw)
        self.show_all()
        self._source = GLib.timeout_add(1000, self._tick)

    def _tick(self):
        self.remaining -= 1
        if self.remaining <= 0:
            self._source = 0
            self.destroy()
            GLib.timeout_add(120, lambda: (self.on_done(), False)[1])
            return False
        self.queue_draw()
        return True

    def set_caption(self, text):
        self.caption = text
        self.queue_draw()

    def cancel(self):
        if self._source:
            GLib.source_remove(self._source)
            self._source = 0
        self.destroy()

    def _on_draw(self, _w, ctx):
        w, h = self.get_allocated_width(), self.get_allocated_height()
        if self._rgba:
            ctx.set_operator(cairo.OPERATOR_CLEAR)
            ctx.paint()
            ctx.set_operator(cairo.OPERATOR_OVER)
        rounded_rect(ctx, 0, 0, w, h, 28)
        ctx.set_source_rgba(0.08, 0.08, 0.1, 0.82)
        ctx.fill()
        layout = PangoCairo.create_layout(ctx)
        layout.set_font_description(Pango.FontDescription.from_string("Sans Bold 54"))
        layout.set_text(str(self.remaining), -1)
        tw, th = layout.get_pixel_size()
        ctx.move_to((w - tw) / 2, (h - th) / 2 - 8)
        ctx.set_source_rgb(1, 1, 1)
        PangoCairo.show_layout(ctx, layout)
        small = PangoCairo.create_layout(ctx)
        small.set_font_description(Pango.FontDescription.from_string("Sans 9"))
        small.set_text(self.caption, -1)
        sw, _sh = small.get_pixel_size()
        ctx.move_to((w - sw) / 2, h - 30)
        ctx.set_source_rgba(1, 1, 1, 0.7)
        PangoCairo.show_layout(ctx, small)


class RecordingFrame:
    """Borda vermelha ao redor da área (fica do lado de fora, não aparece no vídeo)."""

    THICK, GAP = 3, 1

    def __init__(self, rect):
        x, y, w, h = rect
        t, g = self.THICK, self.GAP
        root = Gdk.get_default_root_window()
        rw, rh = root.get_width(), root.get_height()
        bars = [
            (x - g - t, y - g - t, w + 2 * (g + t), t),
            (x - g - t, y + h + g, w + 2 * (g + t), t),
            (x - g - t, y - g, t, h + 2 * g),
            (x + w + g, y - g, t, h + 2 * g),
        ]
        self.color = (1.0, 0.25, 0.25)
        self.windows = []
        for bx, by, bw, bh in bars:
            if bx + bw <= 0 or by + bh <= 0 or bx >= rw or by >= rh:
                continue
            win = Gtk.Window(type=Gtk.WindowType.POPUP)
            win.set_app_paintable(True)
            win.set_default_size(bw, bh)
            win.move(bx, by)
            win.connect("draw", self._on_draw)
            win.show()
            self.windows.append(win)

    def _on_draw(self, _w, ctx):
        ctx.set_source_rgb(*self.color)
        ctx.paint()

    def set_paused(self, paused):
        self.color = (1.0, 0.75, 0.1) if paused else (1.0, 0.25, 0.25)
        for w in self.windows:
            w.queue_draw()

    def destroy(self):
        for w in self.windows:
            w.destroy()
        self.windows = []


class RecordingToolbar(Gtk.Window):
    def __init__(self, recorder, rect, can_pause=True):
        super().__init__(type=Gtk.WindowType.POPUP)
        self.recorder = recorder
        self.get_style_context().add_class("rec-toolbar")
        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual and screen.is_composited():
            self.set_visual(visual)
            self.get_style_context().add_class("rgba")
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        box.set_border_width(5)
        self.dot = Icon("record", 14, rgba=(1, 0.3, 0.3, 1))
        self.dot.set_margin_start(6)
        self.time = Gtk.Label(label="00:00")
        self.time.get_style_context().add_class("rec-time")
        self.time.set_margin_end(6)
        box.pack_start(self.dot, False, False, 0)
        box.pack_start(self.time, False, False, 0)
        self.pause_icon = Icon("pause", 16, rgba=(1, 1, 1, 0.95))
        self.pause_btn = self._button(self.pause_icon, "Pausar / continuar", recorder.toggle_pause)
        if can_pause:
            box.pack_start(self.pause_btn, False, False, 0)
        box.pack_start(self._button(Icon("stop", 16, rgba=(1, 0.35, 0.35, 1)),
                                    "Parar e salvar", recorder.stop), False, False, 0)
        box.pack_start(self._button(Icon("close", 16, rgba=(1, 1, 1, 0.8)),
                                    "Cancelar (descarta a gravação)", recorder.cancel),
                       False, False, 0)
        self.add(box)
        box.show_all()
        self._place(rect)
        self.show()

    def _button(self, icon, tip, cb):
        btn = Gtk.Button()
        btn.add(icon)
        btn.set_relief(Gtk.ReliefStyle.NONE)
        btn.set_tooltip_text(tip)
        btn.get_style_context().add_class("rec-button")
        btn.connect("clicked", lambda *_: cb())
        return btn

    def _place(self, rect):
        x, y, w, h = rect
        _min, nat = self.get_preferred_size()
        tw, th = nat.width, nat.height
        mx, my, mw, mh = _monitor_for(x + w / 2, y + h / 2)
        tx = int(x + (w - tw) / 2)
        ty = y + h + 10
        if ty + th > my + mh:
            ty = y - th - 10
        tx = max(mx, min(tx, mx + mw - tw))
        if ty < my:
            # a área ocupa o monitor inteiro: vai para outro monitor, senão fica dentro
            display = Gdk.Display.get_default()
            for i in range(display.get_n_monitors()):
                g = display.get_monitor(i).get_geometry()
                if (g.x, g.y) != (mx, my):
                    tx = g.x + (g.width - tw) // 2
                    ty = g.y + g.height - th - 60
                    break
            else:
                ty = y + h - th - 12
        self.move(int(tx), int(ty))

    def update(self, elapsed, paused):
        self.time.set_text(utils.human_duration(elapsed))
        self.pause_icon.set_name_icon("play" if paused else "pause")
        blink = paused or int(time.monotonic() * 2) % 2 == 0
        self.dot.set_opacity(1.0 if blink else 0.35)


# ------------------------------------------------------------------ gravador
class Recorder(GObject.Object):
    __gsignals__ = {"changed": (GObject.SignalFlags.RUN_FIRST, None, ())}

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.cfg = app.config
        self.state = "idle"  # idle | countdown | recording | paused | finishing
        self.gif = False
        self._reset()

    def _reset(self):
        self.proc = None
        self.segments = []
        self.elapsed_before = 0.0
        self.seg_started = 0.0
        self.pending = None
        self.tmp = None
        self.frame = None
        self.toolbar = None
        self.countdown = None
        self.tick_id = 0
        self.audio_ok = True
        self.rect = None
        self.gst = None
        self.cast = None
        self._gst_done = False

    # ------------------------------------------------------------ estado
    @property
    def active(self):
        return self.state != "idle"

    def _set_state(self, state):
        self.state = state
        if self.frame:
            self.frame.set_paused(state == "paused")
        self._tick()
        self.emit("changed")

    def elapsed(self):
        extra = time.monotonic() - self.seg_started if self.state == "recording" else 0
        return self.elapsed_before + extra

    def _tick(self):
        if self.toolbar:
            self.toolbar.update(self.elapsed(), self.state == "paused")

    def _on_timer(self):
        self._tick()
        return True

    # --------------------------------------------------------------- API
    def start(self, rect, gif=False):
        if self.active:
            return
        self._reset()
        self.gif = gif
        self.tmp = tempfile.mkdtemp(prefix="rec-", dir=paths.CACHE_DIR)
        if utils.is_wayland():
            self._start_wayland()
            return
        if not utils.which("ffmpeg"):
            self.app.show_error("ffmpeg não encontrado",
                                "Instale com: sudo apt install ffmpeg")
            self._cleanup()
            return
        x, y, w, h = rect
        w -= w % 2
        h -= h % 2
        if w < 16 or h < 16:
            self.app.show_error("Área muito pequena", "Selecione uma área maior para gravar.")
            self._cleanup()
            return
        self.rect = (x, y, w, h)
        scale = Gdk.get_default_root_window().get_scale_factor() or 1
        lrect = _logical(self.rect, scale)
        if self.cfg["record_border"]:
            self.frame = RecordingFrame(lrect)
        if self.cfg["record_toolbar"]:
            self.toolbar = RecordingToolbar(self, lrect)
        self.tick_id = GLib.timeout_add(500, self._on_timer)
        secs = int(self.cfg["record_countdown"] or 0)
        if secs > 0:
            self.countdown = Countdown(secs, lrect, self._begin_segment)
            self._set_state("countdown")
        else:
            self._begin_segment()

    def toggle_pause(self):
        if self.state == "recording" and not self.gst:
            self.pending = "pause"
            self._send_quit()
        elif self.state == "paused":
            self.pending = None
            self._begin_segment()

    def stop(self):
        if self.pending == "cancel":
            return
        if self.state == "recording":
            self.pending = "stop"
            self._hide_ui()
            self._set_state("finishing")
            self._send_quit()
        elif self.state == "paused":
            self._finalize()
        elif self.state == "countdown":
            self.cancel()

    def cancel(self):
        if self.state in ("idle", "finishing"):
            return
        self.pending = "cancel"
        if self.countdown:
            self.countdown.cancel()
            self.countdown = None
        if self.proc or self.gst:
            self._hide_ui()
            self._send_quit()
        else:
            self._cleanup()
            self.app.notifier.show("Gravação cancelada")

    # ------------------------------------------------------------ ffmpeg
    def _audio_inputs(self):
        if self.gif or not self.audio_ok:
            return []
        sources = []
        if self.cfg["audio_system"]:
            sink = _default_sink()
            if sink:
                sources.append(sink + ".monitor")
        if self.cfg["audio_mic"]:
            sources.append("default")
        return sources

    def _ffmpeg_args(self, out):
        x, y, w, h = self.rect
        fps = int(self.cfg["gif_fps"] if self.gif else self.cfg["video_fps"])
        display = os.environ.get("DISPLAY", ":0")
        args = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostats", "-y",
                "-f", "x11grab", "-thread_queue_size", "512", "-framerate", str(fps),
                "-video_size", f"{w}x{h}",
                "-draw_mouse", "1" if self.cfg["record_cursor"] else "0",
                "-i", f"{display}+{x},{y}"]
        audio = self._audio_inputs()
        for src in audio:
            args += ["-f", "pulse", "-thread_queue_size", "1024", "-i", src]
        if len(audio) == 2:
            args += ["-filter_complex",
                     "[1:a][2:a]amix=inputs=2:duration=longest:dropout_transition=0[aout]",
                     "-map", "0:v", "-map", "[aout]"]
        elif len(audio) == 1:
            args += ["-map", "0:v", "-map", "1:a"]
        quality = self.cfg["video_quality"]
        if self.gif:
            args += ["-c:v", "libx264rgb", "-preset", "ultrafast", "-crf", "0"]
        elif self.cfg["video_format"] == "webm":
            args += ["-c:v", "libvpx-vp9", "-deadline", "realtime", "-cpu-used", "8",
                     "-row-mt", "1", "-b:v", "0", "-crf", str(QUALITY_VP9.get(quality, 32)),
                     "-pix_fmt", "yuv420p"]
            if audio:
                args += ["-c:a", "libopus", "-b:a", "128k"]
        else:
            args += ["-c:v", "libx264", "-preset", "veryfast",
                     "-crf", str(QUALITY_X264.get(quality, 23)), "-pix_fmt", "yuv420p"]
            if audio:
                args += ["-c:a", "aac", "-b:a", "160k"]
        args.append(out)
        return args

    def _begin_segment(self):
        self.countdown = None
        if self.tmp is None or self.state == "idle" or self.pending == "cancel":
            return
        n = len(self.segments)
        out = os.path.join(self.tmp, f"seg{n:03d}.mkv")
        log = os.path.join(self.tmp, f"seg{n:03d}.log")
        self.cur_seg = (out, log)
        self.seg_started = time.monotonic()
        try:
            self.proc = utils.run_async(self._ffmpeg_args(out), self._segment_exited,
                                        stderr_path=log, stdin_pipe=True)
        except GLib.Error as e:
            self.app.show_error("Falha ao iniciar a gravação", e.message)
            self._cleanup()
            return
        self._set_state("recording")
        if n == 0 and self.cfg["play_sound"]:
            utils.play_sound("message")

    def _send_quit(self):
        if self.gst:
            self._gst_stop()
            return
        proc = self.proc
        if not proc:
            return
        try:
            pipe = proc.get_stdin_pipe()
            pipe.write_bytes(GLib.Bytes.new(b"q"), None)
            pipe.close(None)
        except GLib.Error:
            proc.send_signal(signal.SIGINT)
        GLib.timeout_add(4000, self._escalate, proc, signal.SIGINT)
        GLib.timeout_add(8000, self._escalate, proc, signal.SIGKILL)

    def _escalate(self, proc, sig):
        if self.proc is proc:
            proc.send_signal(sig)
        return False

    def _segment_exited(self, ok, status):

        out, log = self.cur_seg
        duration = time.monotonic() - self.seg_started
        self.proc = None
        valid = os.path.exists(out) and os.path.getsize(out) > 2048
        pending, self.pending = self.pending, None

        if pending == "cancel":
            self._cleanup()
            self.app.notifier.show("Gravação cancelada")
            return
        if pending is None:
            # o ffmpeg saiu sozinho: provavelmente erro
            detail = utils.tail_file(log)
            if duration < 4 and self._audio_inputs():
                self.audio_ok = False
                self.app.notifier.show("Gravando sem áudio",
                                       "Não foi possível capturar o áudio; a gravação continua só com vídeo.")
                self._begin_segment()
                return
            if not valid:
                self.app.show_error("A gravação falhou", detail or f"ffmpeg saiu com código {status}")
                self._cleanup()
                return
            pending = "stop"
        if valid:
            self.segments.append(out)
            self.elapsed_before += duration
        if pending == "pause":
            self._set_state("paused")
        else:
            self._finalize()

    # ------------------------------------------------------- finalização
    def _finalize(self):
        try:
            self._finalize_inner()
        except (OSError, GLib.Error) as e:
            self.app.show_error("Falha ao salvar a gravação", str(getattr(e, "message", e)))
            self._keep_failed()

    def _finalize_inner(self):
        self._hide_ui()
        self._set_state("finishing")
        if not self.segments:
            self.app.notifier.show("Nada foi gravado")
            self._cleanup()
            return
        kind = "gif" if self.gif else "video"
        ext = "gif" if self.gif else self.cfg["video_format"]
        self.output = utils.build_output_path(self.cfg, kind, ext)
        steps = []
        source = self.segments[0]
        if len(self.segments) > 1:
            listing = os.path.join(self.tmp, "list.txt")
            with open(listing, "w", encoding="utf-8") as f:
                for s in self.segments:
                    f.write("file '%s'\n" % s.replace("'", "'\\''"))
            source = os.path.join(self.tmp, "joined.mkv")
            steps.append(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "concat",
                          "-safe", "0", "-i", listing, "-c", "copy", source])
        if self.gif:
            self.app.notifier.show("Convertendo GIF…", "Isso pode levar alguns segundos.")
            steps.append(self._gif_args(source, self.output))
        else:
            steps.append(self._remux_args(source, self.output))
        self._run_steps(steps)

    def _remux_args(self, src, out):
        args = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", src]
        if self.gst and self.cfg["video_format"] == "webm":
            args += ["-c:v", "libvpx-vp9", "-deadline", "good", "-cpu-used", "4", "-b:v", "0",
                     "-crf", "32", "-c:a", "libopus"]
        elif self.gst and self.cfg["video_format"] == "mp4":
            args += ["-c:v", "copy", "-c:a", "aac"]
        else:
            args += ["-c", "copy"]
        if out.endswith(".mp4"):
            args += ["-movflags", "+faststart"]
        return args + [out]

    def _gif_args(self, src, out):
        fps = int(self.cfg["gif_fps"])
        maxw = int(self.cfg["gif_max_width"] or 0)
        scale = ""
        if maxw and self.rect and self.rect[2] > maxw:
            scale = f"scale={maxw}:-1:flags=lanczos,"
        vf = (f"fps={fps},{scale}split[a][b];[a]palettegen=stats_mode=diff[p];"
              "[b][p]paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle")
        return ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", src, "-vf", vf,
                "-loop", "0", out]

    def _run_steps(self, steps):
        if not steps:
            self._saved()
            return
        log = os.path.join(self.tmp, "final.log")

        def done(ok, status):
            if not ok:
                self.app.show_error("Falha ao salvar a gravação",
                                    utils.tail_file(log) or f"código {status}")
                self._keep_failed()
                return
            self._run_steps(steps[1:])

        try:
            utils.run_async(steps[0], done, stderr_path=log)
        except GLib.Error as e:
            self.app.show_error("Falha ao salvar a gravação", e.message)
            self._keep_failed()

    def _saved(self):
        path, duration, gif = self.output, self.elapsed_before, self.gif
        w, h = (self.rect[2], self.rect[3]) if self.rect else (0, 0)
        if gif and self.rect:
            maxw = int(self.cfg["gif_max_width"] or 0)
            if maxw and w > maxw:
                w, h = maxw, int(h * maxw / w)
        self._cleanup()
        self.app.on_recording_saved(path, "gif" if gif else "video", w, h, duration)

    def _keep_failed(self):
        """Em caso de erro na finalização, preserva os segmentos brutos."""
        output = getattr(self, "output", None) or os.path.join(
            os.path.expanduser(self.cfg["videos_dir"]), utils.safe_strftime(self.cfg["filename_pattern"]))
        if self.segments:
            dest = os.path.splitext(output)[0] + "_bruto.mkv"
            try:
                shutil.move(self.segments[0], dest)
                self.app.notifier.show("Gravação bruta preservada", dest)
            except OSError:
                pass
        self._cleanup()

    def _hide_ui(self):
        if self.frame:
            self.frame.destroy()
            self.frame = None
        if self.toolbar:
            self.toolbar.destroy()
            self.toolbar = None
        if self.countdown:
            self.countdown.cancel()
            self.countdown = None

    def _cleanup(self):
        self._hide_ui()
        if self.tick_id:
            GLib.source_remove(self.tick_id)
            self.tick_id = 0
        if self.cast:
            self.cast.close()
        self._close_wl_fd()
        if self.tmp:
            shutil.rmtree(self.tmp, ignore_errors=True)
        self._reset()
        self._set_state("idle")

    # ------------------------------------------------------------ Wayland
    def _start_wayland(self):
        try:
            import gi
            gi.require_version("Gst", "1.0")
            from gi.repository import Gst
            Gst.init(None)
            self._Gst = Gst
        except (ValueError, ImportError):
            self.app.show_error("GStreamer indisponível",
                                "Instale gstreamer1.0-pipewire para gravar no Wayland.")
            self._cleanup()
            return
        if not utils.which("ffmpeg"):
            self.app.show_error("ffmpeg não encontrado", "Instale o pacote ffmpeg.")
            self._cleanup()
            return
        from . import portal
        try:
            cast = portal.ScreenCast(cursor=self.cfg["record_cursor"])
        except GLib.Error as e:
            self.app.show_error("Portal indisponível", e.message)
            self._cleanup()
            return
        self.cast = cast
        self._set_state("countdown")
        cast.start(lambda fd, node: self._wayland_ready(cast, fd, node),
                   lambda msg: self._wayland_error(cast, msg))

    def _wayland_error(self, cast, msg):
        if cast is not self.cast:  # resposta atrasada de uma sessão já encerrada
            return
        self.app.notifier.show("Gravação não iniciada", msg)
        self._cleanup()

    def _close_wl_fd(self):
        fd = getattr(self, "_wl_fd", None)
        self._wl_fd = None
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass

    def _wayland_ready(self, cast, fd, node_id):
        if cast is not self.cast:  # cancelado enquanto o diálogo estava aberto
            os.close(fd)
            return
        self._wl_fd = fd
        Gst = self._Gst
        out = os.path.join(self.tmp, "seg000.mkv")
        self.cur_seg = (out, "")
        fps = int(self.cfg["gif_fps"] if self.gif else self.cfg["video_fps"])
        crf = QUALITY_X264.get(self.cfg["video_quality"], 23)
        desc = (f"pipewiresrc fd={fd} path={node_id} do-timestamp=true keepalive-time=1000 "
                f"resend-last=true ! videorate ! video/x-raw,framerate={fps}/1 ! videoconvert ! "
                f"video/x-raw,format=I420 ! queue ! x264enc speed-preset=veryfast tune=zerolatency quantizer={crf} pass=quant ! "
                "h264parse ! queue ! matroskamux name=mux ! filesink location=" + _gst_quote(out))
        audio = [] if self.gif else self._audio_inputs()
        if audio:
            desc += " audiomixer name=amix ! audioconvert ! queue ! opusenc ! mux."
            for src in audio:
                dev = "" if src == "default" else f"device={_gst_quote(src)} "
                desc += f" pulsesrc {dev}! audioconvert ! audioresample ! queue ! amix."
        try:
            self.gst = Gst.parse_launch(desc)
        except GLib.Error as e:
            self.gst = None
            self.app.show_error("Falha no GStreamer", e.message)
            self._cleanup()
            return
        bus = self.gst.get_bus()
        bus.add_signal_watch()
        bus.connect("message", self._gst_message)
        self.gst.set_state(Gst.State.PLAYING)
        self.seg_started = time.monotonic()
        self.toolbar = None
        self._set_state("recording")
        self.app.notifier.show("Gravando", "Use o atalho ou o ícone da bandeja para parar.")

    def _gst_stop(self):
        if self.gst:
            self.gst.send_event(self._Gst.Event.new_eos())
            pipeline = self.gst
            GLib.timeout_add(5000, lambda: self.gst is pipeline and self._gst_finish())

    def _gst_message(self, _bus, msg):
        Gst = self._Gst
        if msg.type == Gst.MessageType.EOS:
            self._gst_finish()
        elif msg.type == Gst.MessageType.ERROR:
            err, _dbg = msg.parse_error()
            if self.pending != "cancel":
                self.pending = None
            self._gst_finish(error=err.message)

    def _gst_finish(self, error=None):
        if not self.gst or self._gst_done:
            return False
        self._gst_done = True
        self.gst.set_state(self._Gst.State.NULL)
        self.gst.get_bus().remove_signal_watch()
        self._close_wl_fd()
        duration = time.monotonic() - self.seg_started
        out = self.cur_seg[0]
        pending, self.pending = self.pending, None
        if self.cast:
            self.cast.close()
            self.cast = None
        if pending == "cancel":
            self.gst = None
            self._cleanup()
            return False
        valid = os.path.exists(out) and os.path.getsize(out) > 2048
        if error and not valid:
            self.gst = None
            self.app.show_error("A gravação falhou", error)
            self._cleanup()
            return False
        if valid:
            self.segments.append(out)
            self.elapsed_before += duration
        self._finalize()
        return False


def _default_sink():
    if not utils.which("pactl"):
        return None
    try:
        out = subprocess.run(["pactl", "get-default-sink"], capture_output=True, text=True,
                             timeout=3, check=False).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    return out or None


def _gst_quote(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'
