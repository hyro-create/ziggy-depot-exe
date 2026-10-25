"""Stockage de la clé API Gemini, séparé de la base de conversations et de settings.json.

  Windows : chiffrée avec DPAPI (CryptProtectData) — seul TON compte Windows sur CE PC peut la déchiffrer.
  Autres  : fichier à accès restreint (0600), NON chiffré (utilisé pour le développement/les tests).
Limite honnête : un utilisateur (ou un logiciel) qui contrôle ta session Windows peut toujours obtenir la clé.
"""
import base64, json, os, subprocess
from paths import DATA_DIR

FILE = DATA_DIR / "gemini_key.dat"
_ENTROPY = b"Ziggy/gemini-key/v1"


class SecretError(Exception):
    pass


def backend() -> str:
    return "dpapi" if os.name == "nt" else "file"


def protection_label() -> str:
    return ("chiffrée par Windows (DPAPI), liée à ton compte" if backend() == "dpapi"
            else "fichier à accès restreint, non chiffré (hors Windows)")


def _dpapi(data: bytes, protect: bool) -> bytes:                      # Windows uniquement
    import ctypes
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    def make(b: bytes):
        buf = ctypes.create_string_buffer(b, len(b))
        return Blob(len(b), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), buf

    crypt32, kernel32 = ctypes.windll.crypt32, ctypes.windll.kernel32
    fn = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    fn.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.POINTER(Blob), ctypes.c_void_p,
                   ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    fn.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    src, k1 = make(data)
    ent, k2 = make(_ENTROPY)
    out = Blob()
    if not fn(ctypes.byref(src), None, ctypes.byref(ent), None, None, 0x1, ctypes.byref(out)):   # 0x1 = pas de fenêtre
        raise SecretError("Windows n'a pas pu chiffrer/déchiffrer la clé (compte Windows différent ?).")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        kernel32.LocalFree(ctypes.cast(out.pbData, ctypes.c_void_p))


def _restrict(path) -> None:
    try:
        if os.name == "nt":
            user = os.environ.get("USERNAME", "")
            if user:
                subprocess.run(["icacls", str(path), "/inheritance:r", "/grant:r", f"{user}:(R,W)"],
                               capture_output=True, timeout=10, creationflags=0x08000000)
        else:
            os.chmod(path, 0o600)
    except Exception:
        pass


def save_key(key: str) -> None:
    raw = key.strip().encode("utf-8")
    blob = _dpapi(raw, True) if backend() == "dpapi" else raw
    payload = json.dumps({"v": 1, "backend": backend(), "data": base64.b64encode(blob).decode("ascii")})
    tmp = FILE.with_suffix(".tmp")
    tmp.write_text(payload, encoding="utf-8")
    _restrict(tmp)
    os.replace(tmp, FILE)
    _restrict(FILE)


def load_key():
    """Renvoie la clé, ou None s'il n'y en a pas. Lève SecretError si le fichier est illisible."""
    if not FILE.exists():
        return None
    try:
        d = json.loads(FILE.read_text(encoding="utf-8"))
        blob = base64.b64decode(d["data"])
        if d.get("backend") == "dpapi":
            if os.name != "nt":
                raise SecretError("Clé chiffrée par Windows : illisible sur ce système.")
            blob = _dpapi(blob, False)
        return blob.decode("utf-8")
    except SecretError:
        raise
    except Exception as e:
        raise SecretError(f"Fichier de clé illisible ({type(e).__name__}). Supprime la clé dans Paramètres puis ressaisis-la.")


def delete_key() -> bool:
    if FILE.exists():
        FILE.unlink()
        return True
    return False


def has_key() -> bool:
    return FILE.exists()


def last4():
    try:
        k = load_key()
        return k[-4:] if k and len(k) >= 12 else None
    except SecretError:
        return None
