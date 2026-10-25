"""Actions sensibles : l'IA ne peut jamais les exécuter seule.

Quand Gemini appelle un outil marqué @sensitive, RIEN n'est exécuté : une demande est mise en attente et
l'utilisateur doit cliquer sur « Confirmer » dans l'interface (ou répondre /oui <id> sur Telegram).
Le texte généré par l'IA n'est jamais passé à un shell : il n'existe aucun outil « exécuter une commande ».
"""
import functools, inspect, threading, time, uuid
from logsetup import get_logger

log = get_logger("actions")
TTL_SECONDS = 600
_pending = {}
_lock = threading.Lock()


class _Short(dict):
    def __missing__(self, k):
        return "?"


def sensitive(description):
    """description : texte avec {paramètres} ou fonction(arguments)->texte. Décorateur d'outil Gemini."""
    def deco(fn):
        sig = inspect.signature(fn)

        @functools.wraps(fn)                       # conserve nom, docstring et signature pour Gemini
        def wrapper(*args, **kwargs):
            try:
                bound = sig.bind(*args, **kwargs)
            except TypeError as e:
                return f"Paramètres invalides : {e}"
            bound.apply_defaults()
            def _show(v):
                s = str(v)
                if len(s) <= 80:
                    return s
                # Pour les chemins : garder toujours le nom de fichier (dernier segment)
                from pathlib import PurePath
                try:
                    name = PurePath(s).name
                    if name and len(name) < 60:
                        return "…/" + name
                except Exception:
                    pass
                return "…" + s[-77:]
            shown = _Short({k: _show(v) for k, v in bound.arguments.items()})
            try:
                desc = description(shown) if callable(description) else description.format_map(shown)
            except Exception:
                desc = fn.__name__
            pid = uuid.uuid4().hex[:8]
            with _lock:
                _pending[pid] = {"id": pid, "tool": fn.__name__, "description": desc, "fn": fn,
                                 "args": bound.args, "kwargs": bound.kwargs, "ts": time.time()}
            log.info("Action en attente de confirmation : %s (%s)", fn.__name__, pid)
            return (f"EN ATTENTE DE CONFIRMATION (id {pid}) : « {desc} ». L'utilisateur doit cliquer sur Confirmer dans "
                    f"l'interface de Ziggy (ou répondre /oui {pid} sur Telegram). L'action N'A PAS été exécutée : dis-le simplement.")
        return wrapper
    return deco


def _purge():
    now = time.time()
    for k in [k for k, v in _pending.items() if now - v["ts"] > TTL_SECONDS]:
        _pending.pop(k, None)


def list_pending() -> list:
    with _lock:
        _purge()
        return [{"id": v["id"], "tool": v["tool"], "description": v["description"]} for v in _pending.values()]


def resolve(pid: str, approve: bool) -> str:
    """Exécute (approve=True) ou annule une action en attente. Appelée uniquement par l'interface ou Telegram."""
    with _lock:
        _purge()
        item = _pending.pop(pid, None)
    if item is None:
        return "Demande introuvable ou expirée."
    if not approve:
        log.info("Action annulée par l'utilisateur : %s", item["tool"])
        return f"Action annulée : {item['description']}"
    log.info("Action confirmée par l'utilisateur : %s", item["tool"])
    try:
        return str(item["fn"](*item["args"], **item["kwargs"]))
    except Exception as e:
        log.error("Échec de l'action %s : %s", item["tool"], type(e).__name__)
        return f"Erreur pendant l'action : {e}"
