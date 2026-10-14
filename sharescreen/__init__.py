"""ShareScreen — captura de tela e gravação para Linux."""
import os

# SHARESCREEN_APP_ID permite rodar uma cópia de desenvolvimento ao lado da instalada
APP_ID = os.environ.get("SHARESCREEN_APP_ID", "io.github.sharescreen")
APP_NAME = "ShareScreen"
VERSION = "1.0.1"
