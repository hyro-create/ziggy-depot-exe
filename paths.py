"""Chemins de Ziggy — identiques en mode script et en application compilée (PyInstaller).

  resource_path()  fichiers EMBARQUÉS dans l'application (interface, icônes) : lecture seule.
  DATA_DIR         tes DONNÉES personnelles : un dossier PERMANENT, séparé du programme.
                     Windows : %LOCALAPPDATA%\\Ziggy      (autre : ~/.local/share/Ziggy)
                   Il n'est jamais le dossier temporaire de PyInstaller ni le dossier d'installation :
                   mises à jour et désinstallation ne le touchent pas.
  ZIGGY_HOME       variable d'environnement pour choisir un autre dossier de données (tests, déplacement).
"""
import os, shutil, sys
from pathlib import Path

FROZEN = getattr(sys, "frozen", False)
PROGRAM_DIR = Path(sys.executable).resolve().parent if FROZEN else Path(__file__).resolve().parent


def resource_path(rel: str) -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)) / rel


def compute_data_dir(is_windows: bool, env, home: Path) -> Path:
    """Emplacement des données (fonction pure, testable)."""
    override = (env.get("ZIGGY_HOME") or "").strip()
    if override:
        return Path(override).expanduser().resolve()
    if is_windows:
        return Path(env.get("LOCALAPPDATA") or (home / "AppData" / "Local")) / "Ziggy"
    return Path(env.get("XDG_DATA_HOME") or (home / ".local" / "share")) / "Ziggy"


def _data_dir() -> Path:
    p = compute_data_dir(os.name == "nt", os.environ, Path.home())
    p.mkdir(parents=True, exist_ok=True)
    return p


DATA_DIR = _data_dir()
BACKUP_DIR = DATA_DIR / "backups"
LOG_DIR = DATA_DIR / "logs"

# Données des anciennes versions (placées à côté du programme / du projet) : copiées, jamais déplacées
LEGACY_FILES = ("memoire.db", ".env", "credentials.json", "token.json", "ms_token.json", "spotify_token.json")


def import_legacy_data() -> list:
    """Copie, une seule fois, les données d'une ancienne version trouvées à côté du programme."""
    imported = []
    if PROGRAM_DIR == DATA_DIR:
        return imported
    for name in LEGACY_FILES:
        src, dst = PROGRAM_DIR / name, DATA_DIR / name
        if src.is_file() and not dst.exists():
            try:
                shutil.copy2(src, dst)
                imported.append(name)
            except OSError:
                pass
    return imported
