"""Fenêtre Ziggy autonome — pywebview (WebView2 sous Windows 11, WebKit sur macOS/Linux).

La fenêtre s'ouvre sans aucun navigateur visible : barre d'adresse, onglets et menus navigateur
sont totalement absents. Sur Windows 11, WebView2 Runtime est préinstallé et rien n'est téléchargé.

Lancement :
    window.open(url, data_dir)          ouvre la fenêtre et bloque jusqu'à fermeture
    window.open_in_thread(url, data_dir) idem dans un thread (le serveur Flask tourne en parallèle)
"""
import os, sys, threading, time
from pathlib import Path
from logsetup import get_logger

log = get_logger("fenetre")

# Taille préférée de la fenêtre (réduite à l'écran si nécessaire)
W, H = 1280, 860
TITLE = "Ziggy"
APP_ID = "solar.ziggy"                              # identifiant unique Windows (pour la barre des tâches)

# CSS injecté dans la page : on cache les éléments inutiles en contexte application
APP_CSS = """
  /* En mode application, on n'a pas besoin de l'aide « ouvrir dans un navigateur »,
     ni de liens vers des URL externes dans la barre de statut */
  [data-browser-only] { display: none !important; }
"""


class ZiggyWindow:
    def __init__(self):
        self._win = None
        self._ready = threading.Event()

    def _on_loaded(self):
        """Appelé par pywebview quand la page est prête."""
        self._ready.set()

    def open(self, url: str, icon_path: str = None) -> None:
        """Ouvre la fenêtre et bloque jusqu'à fermeture (à appeler depuis le thread principal)."""
        import webview

        # Réduit la fenêtre si l'écran est plus petit
        try:
            scr = webview.screens()[0]
            w = min(W, int(scr.width * 0.95))
            h = min(H, int(scr.height * 0.95))
        except Exception:
            w, h = W, H

        self._win = webview.create_window(
            TITLE, url,
            width=w, height=h,
            min_size=(860, 580),
            resizable=True,
            text_select=True,
            confirm_close=False,
        )
        self._win.events.loaded += self._on_loaded

        start_kw = dict(
            func=None,
            gui="edgechromium" if sys.platform == "win32" else None,     # WebView2 sur Windows
        )
        if icon_path and Path(icon_path).is_file():
            start_kw["icon"] = icon_path
        if APP_ID and sys.platform == "win32":
            start_kw["user_agent"] = f"Ziggy/{APP_ID}"

        log.info("Fenêtre Ziggy (%dx%d) → %s", w, h, url)
        try:
            webview.start(**{k: v for k, v in start_kw.items() if v is not None})
        except Exception as e:
            log.error("Fenêtre Ziggy impossible : %s — %s", type(e).__name__, e)
            raise

    def navigate(self, url: str) -> None:
        if self._win:
            try:
                self._win.load_url(url)
            except Exception as e:
                log.warning("Navigation impossible : %s", e)

    def bring_to_front(self) -> None:
        if self._win:
            try:
                self._win.restore()
            except Exception:
                pass

    def close(self) -> None:
        if self._win:
            try:
                self._win.destroy()
            except Exception:
                pass


_instance = ZiggyWindow()


def open_window(url: str, icon_path: str = None) -> None:
    """Lance la fenêtre Ziggy (bloque le thread courant jusqu'à fermeture)."""
    _instance.open(url, icon_path)


def open_in_thread(url: str, icon_path: str = None, ready_cb=None) -> threading.Thread:
    """Lance la fenêtre dans un thread séparé. ready_cb() est appelé quand la page est chargée."""
    def _run():
        if ready_cb:
            _instance._ready.clear()
            _instance._win = None
        try:
            _instance.open(url, icon_path)
        except Exception as e:
            log.error("Fenêtre : %s", e)
    t = threading.Thread(target=_run, daemon=False, name="ziggy-window")
    t.start()
    if ready_cb:
        threading.Thread(target=lambda: (_instance._ready.wait(30), ready_cb()), daemon=True).start()
    return t


def navigate(url: str) -> None:
    _instance.navigate(url)


def bring_to_front() -> None:
    _instance.bring_to_front()


def close() -> None:
    _instance.close()
