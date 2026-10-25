"""Journaux : fichier rotatif dans le dossier de données. Les secrets (clés API, jetons) sont masqués."""
import logging, logging.handlers, re, sys
from paths import LOG_DIR

_secrets = set()
_PATTERNS = [
    re.compile(r"AIza[0-9A-Za-z_\-]{20,}"),                                        # clés Google
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-~+/]{12,}=*"),                       # en-têtes Authorization
    re.compile(r"(?i)((?:api[_-]?key|token|secret|password|authorization|x-goog-api-key)[\"'\s:=]+)[^\s\"',;}]{6,}"),
]


def register_secret(value) -> None:
    """Toute valeur enregistrée ici sera remplacée par [SECRET] dans les journaux."""
    if value and len(value) >= 8:
        _secrets.add(value)


def redact(text: str) -> str:
    for s in sorted(_secrets, key=len, reverse=True):
        text = text.replace(s, "[SECRET]")
    for p in _PATTERNS:
        text = p.sub(lambda m: (m.group(1) if m.groups() else "") + "[SECRET]", text)
    return text


class RedactingFormatter(logging.Formatter):
    def format(self, record):                      # inclut aussi les traces d'erreur (exc_info)
        return redact(super().format(record))


_configured = False


def get_logger(name: str = "ziggy") -> logging.Logger:
    global _configured
    if not _configured:
        _configured = True
        root = logging.getLogger("ziggy")
        root.setLevel(logging.INFO)
        root.propagate = False
        fmt = RedactingFormatter("%(asctime)s %(levelname)s %(name)s : %(message)s")
        try:
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            fh = logging.handlers.RotatingFileHandler(LOG_DIR / "ziggy.log", maxBytes=512_000, backupCount=3, encoding="utf-8")
            fh.setFormatter(fmt)
            root.addHandler(fh)
        except OSError:
            pass
        if sys.stderr is not None:
            sh = logging.StreamHandler(sys.stderr)
            sh.setFormatter(fmt)
            root.addHandler(sh)
        for noisy in ("httpx", "httpcore", "urllib3", "werkzeug", "waitress", "googleapiclient", "msal"):
            logging.getLogger(noisy).setLevel(logging.WARNING)
    return logging.getLogger(name if name.startswith("ziggy") else f"ziggy.{name}")
