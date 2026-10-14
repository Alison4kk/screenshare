"""Histórico: grade de miniaturas com busca, filtros e painel de detalhes."""
import os

from gi.repository import Gdk, GdkPixbuf, GLib, Gtk

from .. import utils
from .capture_page import cover
from .widgets import dialog_message, label

PAGE_SIZE = 120
KIND_LABEL = {"image": "Imagem", "video": "Vídeo", "gif": "GIF"}


class HistoryCard(Gtk.FlowBoxChild):
    W, H = 200, 125

    def __init__(self, app, entry):
        super().__init__()
        self.entry = entry
        self.get_style_context().add_class("history-card")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.set_border_width(6)
        overlay = Gtk.Overlay()
        self.image = Gtk.Image.new_from_icon_name(
            "video-x-generic-symbolic" if entry["kind"] == "video" else "image-x-generic-symbolic",
            Gtk.IconSize.DIALOG)
        self.image.set_size_request(self.W, self.H)
        self.image.get_style_context().add_class("thumb")
        overlay.add(self.image)
        badge_text = KIND_LABEL.get(entry["kind"], "")
        if entry["kind"] in ("video", "gif") and entry.get("duration"):
            badge_text += "  " + utils.human_duration(entry["duration"])
        elif entry["kind"] == "image":
            badge_text = os.path.splitext(entry["path"])[1].lstrip(".").upper() or badge_text
        badge = label(badge_text, f"badge badge-{entry['kind']}")
        badge.set_halign(Gtk.Align.START)
        badge.set_valign(Gtk.Align.END)
        badge.set_margin_start(6)
        badge.set_margin_bottom(6)
        overlay.add_overlay(badge)
        box.pack_start(overlay, False, False, 0)
        name = label(os.path.basename(entry["path"]), "card-name", ellipsize=True)
        name.set_max_width_chars(24)
        box.pack_start(name, False, False, 0)
        box.pack_start(label(utils.human_date(entry.get("created")), "dim-label card-meta"),
                       False, False, 0)
        self.add(box)
        self.set_tooltip_text(entry["path"])
        app.thumbs.request(entry, self._set_thumb, (self.W * 2, self.H * 2))

    def _set_thumb(self, pixbuf):
        if pixbuf:
            self.image.set_from_pixbuf(cover(pixbuf, self.W, self.H))


class HistoryPage(Gtk.Box):
    def __init__(self, app, window):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.app = app
        self.window = window
        self.selected = None
        self.shown = PAGE_SIZE
        self._refresh_id = 0

        bar = Gtk.Box(spacing=8)
        bar.set_border_width(10)
        self.search = Gtk.SearchEntry()
        self.search.set_placeholder_text("Buscar pelo nome…")
        self.search.set_width_chars(28)
        self.search.connect("search-changed", lambda *_: self.refresh(reset=True))
        bar.pack_start(self.search, False, False, 0)
        self.filter = Gtk.ComboBoxText()
        for value, text in (("", "Todos"), ("image", "Imagens"), ("video", "Vídeos"), ("gif", "GIFs")):
            self.filter.append(value, text)
        self.filter.set_active_id("")
        self.filter.connect("changed", lambda *_: self.refresh(reset=True))
        bar.pack_start(self.filter, False, False, 0)
        self.count_label = label("", "dim-label")
        bar.pack_start(self.count_label, False, False, 6)
        for icon, tip, cb in (
                ("folder-videos-symbolic", "Abrir pasta de vídeos",
                 lambda: utils.open_folder(app.config["videos_dir"])),
                ("folder-pictures-symbolic", "Abrir pasta de capturas",
                 lambda: utils.open_folder(app.config["screenshots_dir"]))):
            btn = Gtk.Button.new_from_icon_name(icon, Gtk.IconSize.BUTTON)
            btn.set_tooltip_text(tip)
            btn.connect("clicked", lambda _b, c=cb: c())
            bar.pack_end(btn, False, False, 0)
        self.pack_start(bar, False, False, 0)
        self.pack_start(Gtk.Separator(), False, False, 0)

        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        self.pack_start(paned, True, True, 0)

        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.scroller = Gtk.ScrolledWindow()
        self.scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.flow = Gtk.FlowBox()
        self.flow.set_valign(Gtk.Align.START)
        self.flow.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.flow.set_activate_on_single_click(False)
        self.flow.set_homogeneous(True)
        self.flow.set_max_children_per_line(10)
        self.flow.set_column_spacing(6)
        self.flow.set_row_spacing(6)
        self.flow.set_border_width(10)
        self.flow.connect("selected-children-changed", self._on_selection)
        self.flow.connect("child-activated", lambda _f, c: app.open_entry(c.entry, prefer_open=True))
        self.flow.connect("button-press-event", self._on_button)
        self.flow.connect("key-press-event", self._on_key)
        inner.pack_start(self.flow, False, False, 0)
        self.more_btn = Gtk.Button(label="Carregar mais")
        self.more_btn.set_halign(Gtk.Align.CENTER)
        self.more_btn.set_margin_bottom(12)
        self.more_btn.set_no_show_all(True)
        self.more_btn.connect("clicked", self._load_more)
        inner.pack_start(self.more_btn, False, False, 0)
        self.empty = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.empty.set_valign(Gtk.Align.CENTER)
        self.empty.set_margin_top(80)
        img = Gtk.Image.new_from_icon_name("image-x-generic-symbolic", Gtk.IconSize.DIALOG)
        img.set_pixel_size(64)
        img.get_style_context().add_class("dim-label")
        self.empty.pack_start(img, False, False, 0)
        self.empty_label = label("Nenhuma captura ainda", "empty-title", xalign=0.5)
        self.empty.pack_start(self.empty_label, False, False, 0)
        self.empty.pack_start(label("Use os atalhos ou a página Capturar para começar.",
                                    "dim-label", xalign=0.5), False, False, 0)
        self.empty.set_no_show_all(True)
        for child in self.empty.get_children():
            child.show()
        inner.pack_start(self.empty, False, False, 0)
        self.scroller.add(inner)
        left.pack_start(self.scroller, True, True, 0)
        paned.pack1(left, True, False)

        self.details = self._build_details()
        paned.pack2(self.details, False, False)
        paned.set_position(700)

        app.history.connect(self._schedule_refresh)
        self.refresh(reset=True)

    # -------------------------------------------------------------- detalhes
    def _build_details(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_size_request(300, -1)
        box.set_border_width(14)
        box.get_style_context().add_class("details-pane")
        self.d_image = Gtk.Image()
        self.d_image.set_size_request(272, 180)
        self.d_image.get_style_context().add_class("thumb")
        box.pack_start(self.d_image, False, False, 0)
        self.d_name = label("", "details-name", wrap=True)
        box.pack_start(self.d_name, False, False, 0)
        self.d_grid = Gtk.Grid(column_spacing=12, row_spacing=4)
        box.pack_start(self.d_grid, False, False, 0)

        actions = Gtk.Grid(column_spacing=6, row_spacing=6, column_homogeneous=True)
        self.d_buttons = {}
        specs = [
            ("open", "Abrir", "document-open-symbolic", self._act_open),
            ("edit", "Editar", "document-edit-symbolic", self._act_edit),
            ("copy", "Copiar", "edit-copy-symbolic", self._act_copy),
            ("copy_path", "Copiar caminho", "insert-link-symbolic", self._act_copy_path),
            ("folder", "Mostrar na pasta", "folder-open-symbolic", self._act_folder),
            ("rename", "Renomear", "document-edit-symbolic", self._act_rename),
            ("delete", "Excluir", "user-trash-symbolic", self._act_delete),
            ("forget", "Remover do histórico", "list-remove-symbolic", self._act_forget),
        ]
        for i, (key, text, icon, cb) in enumerate(specs):
            btn = Gtk.Button()
            inner = Gtk.Box(spacing=6)
            inner.set_halign(Gtk.Align.CENTER)
            inner.pack_start(Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.BUTTON), False, False, 0)
            inner.pack_start(Gtk.Label(label=text), False, False, 0)
            btn.add(inner)
            btn.connect("clicked", lambda _b, c=cb: c())
            if key == "delete":
                btn.get_style_context().add_class("destructive-action")
            actions.attach(btn, i % 2, i // 2, 1, 1)
            self.d_buttons[key] = btn
        box.pack_start(actions, False, False, 6)

        self.d_placeholder = label("Selecione um item para ver os detalhes.", "dim-label",
                                   xalign=0.5, wrap=True)
        self.d_placeholder.set_margin_top(40)
        outer = Gtk.Stack()
        outer.add_named(self.d_placeholder, "empty")
        sc = Gtk.ScrolledWindow()
        sc.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sc.add(box)
        outer.add_named(sc, "item")
        self.d_stack = outer
        return outer

    def _fill_details(self, entry):
        if not entry:
            self.d_stack.set_visible_child_name("empty")
            return
        self.d_stack.set_visible_child_name("item")
        path = entry["path"]
        self.d_name.set_text(os.path.basename(path))
        for child in self.d_grid.get_children():
            child.destroy()
        rows = [("Tipo", KIND_LABEL.get(entry["kind"], entry["kind"]))]
        if entry.get("width"):
            rows.append(("Dimensões", f"{entry['width']} × {entry['height']} px"))
        if entry.get("duration"):
            rows.append(("Duração", utils.human_duration(entry["duration"])))
        try:
            rows.append(("Tamanho", utils.human_size(os.path.getsize(path))))
        except OSError:
            rows.append(("Arquivo", "não encontrado"))
        rows.append(("Data", utils.human_date(entry.get("created"))))
        rows.append(("Pasta", os.path.dirname(path).replace(os.path.expanduser("~"), "~")))
        for i, (k, v) in enumerate(rows):
            self.d_grid.attach(label(k, "dim-label"), 0, i, 1, 1)
            val = label(v, wrap=True)
            val.set_selectable(True)
            self.d_grid.attach(val, 1, i, 1, 1)
        self.d_grid.show_all()
        self.d_buttons["edit"].set_sensitive(entry["kind"] == "image")
        self.d_image.set_from_icon_name("image-x-generic-symbolic", Gtk.IconSize.DIALOG)
        self.app.thumbs.request(entry, lambda pb: self._set_preview(entry, pb), (272, 180))

    def _set_preview(self, entry, pixbuf):
        if pixbuf and self.selected is entry:
            self.d_image.set_from_pixbuf(pixbuf)

    # ------------------------------------------------------------- listagem
    def _schedule_refresh(self):
        if not self._refresh_id:
            self._refresh_id = GLib.timeout_add(150, self._do_scheduled)

    def _do_scheduled(self):
        self._refresh_id = 0
        self.refresh()
        return False

    def _entries(self):
        return self.app.history.entries(self.filter.get_active_id() or None, self.search.get_text())

    def refresh(self, reset=False):
        if reset:
            self.shown = PAGE_SIZE
        keep = self.selected["id"] if self.selected else None
        for child in self.flow.get_children():
            child.destroy()
        entries = self._entries()
        total = len(entries)
        self.count_label.set_text(f"{total} {'item' if total == 1 else 'itens'}")
        reselect = None
        for entry in entries[:self.shown]:
            card = HistoryCard(self.app, entry)
            self.flow.add(card)
            if entry["id"] == keep:
                reselect = card
        self.flow.show_all()
        self.more_btn.set_visible(total > self.shown)
        has_any = bool(self.app.history.items)
        self.empty.set_visible(total == 0)
        self.empty_label.set_text("Nenhuma captura ainda" if not has_any else "Nada encontrado")
        if reselect:
            self.flow.select_child(reselect)
        else:
            self.selected = None
            self._fill_details(None)

    def _load_more(self, *_):
        self.shown += PAGE_SIZE
        self.refresh()

    def _on_selection(self, flow):
        sel = flow.get_selected_children()
        self.selected = sel[0].entry if sel else None
        self._fill_details(self.selected)

    def _on_button(self, flow, event):
        if event.button != 3:
            return False
        child = flow.get_child_at_pos(int(event.x), int(event.y))
        if not child:
            return False
        flow.select_child(child)
        menu = Gtk.Menu()
        items = [("Abrir", self._act_open), ("Editar", self._act_edit), None,
                 ("Copiar", self._act_copy), ("Copiar caminho", self._act_copy_path),
                 ("Mostrar na pasta", self._act_folder), None,
                 ("Renomear…", self._act_rename), ("Remover do histórico", self._act_forget),
                 ("Excluir (lixeira)", self._act_delete)]
        for it in items:
            if it is None:
                menu.append(Gtk.SeparatorMenuItem())
                continue
            mi = Gtk.MenuItem(label=it[0])
            mi.connect("activate", lambda _m, cb=it[1]: cb())
            if it[0] == "Editar":
                mi.set_sensitive(child.entry["kind"] == "image")
            menu.append(mi)
        menu.show_all()
        menu.attach_to_widget(flow, None)
        menu.popup_at_pointer(event)
        return True

    def _on_key(self, _w, event):
        if event.keyval == Gdk.KEY_Delete and self.selected:
            self._act_delete()
            return True
        if event.keyval == Gdk.KEY_F2 and self.selected:
            self._act_rename()
            return True
        if (event.state & Gdk.ModifierType.CONTROL_MASK and event.keyval in (Gdk.KEY_c, Gdk.KEY_C)
                and self.selected):
            self._act_copy()
            return True
        return False

    # ---------------------------------------------------------------- ações
    def _exists(self):
        e = self.selected
        if not e:
            return None
        if not os.path.exists(e["path"]):
            resp = dialog_message(self.window, "Arquivo não encontrado",
                                  "O arquivo foi movido ou apagado. Remover do histórico?",
                                  Gtk.MessageType.WARNING,
                                  [("Manter", Gtk.ResponseType.CANCEL),
                                   ("Remover", Gtk.ResponseType.OK)])
            if resp == Gtk.ResponseType.OK:
                self.app.history.remove(e)
            return None
        return e

    def _act_open(self):
        e = self._exists()
        if e:
            utils.open_file(e["path"])

    def _act_edit(self):
        e = self._exists()
        if e and e["kind"] == "image":
            self.app.edit_entry(e)

    def _act_copy(self):
        e = self._exists()
        if not e:
            return
        if e["kind"] == "image":
            try:
                utils.copy_image(GdkPixbuf.Pixbuf.new_from_file(e["path"]))
                self.window.toast("Imagem copiada")
            except GLib.Error as err:
                self.app.show_error("Não foi possível copiar", err.message)
        else:
            utils.copy_text(e["path"])
            self.window.toast("Caminho do arquivo copiado")

    def _act_copy_path(self):
        if self.selected:
            utils.copy_text(self.selected["path"])
            self.window.toast("Caminho copiado")

    def _act_folder(self):
        e = self._exists()
        if e:
            utils.show_in_folder(e["path"])

    def _act_rename(self):
        e = self._exists()
        if not e:
            return
        base, ext = os.path.splitext(os.path.basename(e["path"]))
        dialog = Gtk.Dialog(title="Renomear", transient_for=self.window, modal=True)
        dialog.add_buttons("Cancelar", Gtk.ResponseType.CANCEL, "Renomear", Gtk.ResponseType.OK)
        dialog.set_default_response(Gtk.ResponseType.OK)
        entry = Gtk.Entry(text=base, activates_default=True, width_chars=40)
        area = dialog.get_content_area()
        area.set_border_width(12)
        area.set_spacing(8)
        area.pack_start(label("Novo nome (sem extensão):"), False, False, 0)
        area.pack_start(entry, False, False, 0)
        dialog.show_all()
        resp = dialog.run()
        new = entry.get_text().strip()
        dialog.destroy()
        if resp != Gtk.ResponseType.OK or not new or new == base:
            return
        new = utils.safe_strftime(new.replace("%", "%%"))
        target = os.path.join(os.path.dirname(e["path"]), new + ext)
        if os.path.exists(target):
            self.app.show_error("Já existe um arquivo com esse nome", target)
            return
        try:
            os.rename(e["path"], target)
        except OSError as err:
            self.app.show_error("Não foi possível renomear", str(err))
            return
        self.app.history.update(e, path=target)

    def _act_delete(self):
        e = self.selected
        if not e:
            return
        resp = dialog_message(self.window, "Mover para a lixeira?", os.path.basename(e["path"]),
                              Gtk.MessageType.QUESTION,
                              [("Cancelar", Gtk.ResponseType.CANCEL),
                               ("Mover para a lixeira", Gtk.ResponseType.OK)])
        if resp != Gtk.ResponseType.OK:
            return
        if os.path.exists(e["path"]) and not utils.trash(e["path"]):
            self.app.show_error("Não foi possível mover para a lixeira", e["path"])
            return
        self.app.history.remove(e)

    def _act_forget(self):
        if self.selected:
            self.app.history.remove(self.selected)
