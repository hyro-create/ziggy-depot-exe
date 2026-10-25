"""Intégration Windows : démarrage automatique, instance unique, icône de la barre des tâches, boîtes de message."""
import os, subprocess, sys, threading, webbrowser
from paths import FROZEN, resource_path
from logsetup import get_logger

log = get_logger("systeme")
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "Ziggy"
MUTEX_NAME = "ZiggyAppMutex"          # utilisé aussi par l'installateur pour détecter une instance en cours
_mutex_handle = None


def autostart_supported() -> bool:
    return os.name == "nt" and FROZEN


def autostart_get() -> bool:
    if os.name != "nt":
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, RUN_NAME)
            return True
    except OSError:
        return False


def autostart_set(enabled: bool):
    """(ok, message). Écrit dans HKEY_CURRENT_USER : aucun droit administrateur nécessaire."""
    if not autostart_supported():
        return False, "Le démarrage automatique n'est disponible que dans Ziggy installé sous Windows."
    try:
        import winreg
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            if enabled:
                winreg.SetValueEx(k, RUN_NAME, 0, winreg.REG_SZ, f'"{sys.executable}" --autostart')
            else:
                try:
                    winreg.DeleteValue(k, RUN_NAME)
                except FileNotFoundError:
                    pass
        return True, "Démarrage automatique " + ("activé." if enabled else "désactivé.")
    except OSError as e:
        return False, f"Impossible de modifier le démarrage automatique : {e}"


def acquire_instance_mutex() -> bool:
    """Windows : crée le mutex nommé. False si une autre instance de Ziggy tourne déjà."""
    global _mutex_handle
    if os.name != "nt":
        return True
    import ctypes
    _mutex_handle = ctypes.windll.kernel32.CreateMutexW(None, False, MUTEX_NAME)
    return ctypes.windll.kernel32.GetLastError() != 183     # ERROR_ALREADY_EXISTS


def message_box(title: str, text: str) -> None:
    """Message visible même sans console (application compilée en mode fenêtre)."""
    log.error("%s : %s", title, text)
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, text, title, 0x10)
            return
        except Exception:
            pass
    try:
        print(f"\n[{title}] {text}")
    except Exception:
        pass


def open_folder(path) -> bool:
    try:
        if os.name == "nt":
            os.startfile(str(path))                             # ouvre l'Explorateur
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
        return True
    except Exception:
        return False


def tray_supported() -> bool:
    if os.name != "nt":
        return False
    try:
        import pystray, PIL  # noqa
        return True
    except Exception:
        return False


class Tray:
    """Icône dans la zone de notification Windows (menu : Ouvrir / Paramètres / Quitter)."""
    def __init__(self, on_open, on_settings, on_quit):
        self.on_open, self.on_settings, self.on_quit, self.icon = on_open, on_settings, on_quit, None

    def start(self) -> bool:
        try:
            import pystray
            from PIL import Image
            image = Image.open(resource_path("assets/ziggy_icon.png"))
            menu = pystray.Menu(
                pystray.MenuItem("Ouvrir Ziggy", lambda icon, item: self.on_open(), default=True),
                pystray.MenuItem("Paramètres", lambda icon, item: self.on_settings()),
                pystray.MenuItem("Quitter Ziggy", lambda icon, item: self.on_quit()))
            self.icon = pystray.Icon("Ziggy", image, "Ziggy", menu)
            threading.Thread(target=self.icon.run, daemon=True, name="barre-des-taches").start()
            return True
        except Exception as e:
            log.warning("Icône de la barre des tâches indisponible : %s", type(e).__name__)
            return False

    def notify(self, message: str, title: str = "Ziggy") -> None:
        try:
            if self.icon:
                self.icon.notify(message, title)
        except Exception:
            pass

    def stop(self) -> None:
        try:
            if self.icon:
                self.icon.stop()
        except Exception:
            pass

