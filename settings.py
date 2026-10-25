"""Préférences de l'utilisateur (settings.json, dans le dossier de données). Aucun secret ici."""
import copy, json, os, re, threading, time
from paths import DATA_DIR
from logsetup import get_logger

log = get_logger("settings")
FILE = DATA_DIR / "settings.json"
# Modèle de secours (stable, appels d'outils pris en charge). Ziggy choisit en réalité lui-même le meilleur modèle
# disponible sur le compte (gemini.pick_best) : les noms changent vite et Google arrête régulièrement d'anciens modèles
# (gemini-2.5-* : arrêtés le 16 octobre 2026).
DEFAULT_MODEL = "gemini-3.5-flash"
RETIRED = re.compile(r"^(models/)?gemini-(pro|1\.|2\.0|2\.5)")


def is_retired(name: str) -> bool:
    return bool(name and RETIRED.match(name))
_lock = threading.RLock()

DEFAULTS = {
    "model": "",                       # vide = GEMINI_MODEL (variable d'environnement) puis DEFAULT_MODEL
    "autostart": False,                # lancer Ziggy à l'ouverture de session Windows
    "tray": True,                      # icône dans la barre des tâches
    "startup_behavior": "open",        # "open" = ouvrir l'interface ; "background" = rester dans la barre des tâches
    "voice": {"stt_enabled": True, "tts_enabled": False, "voice_name": "", "rate": 1.0, "volume": 1.0},
    "custom_apps": {},                 # {"nom": "C:\\chemin\\vers\\app.exe"} : applications que Ziggy peut ouvrir
}
# Ce que « Réinitialiser les préférences » remet à zéro (le modèle, la clé et la mémoire sont conservés)
RESETTABLE = ("autostart", "tray", "startup_behavior", "voice")


def _merge(base, over):
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if k in out and isinstance(out[k], dict) and k != "custom_apps" and isinstance(v, dict):
            out[k] = {**out[k], **{kk: vv for kk, vv in v.items() if kk in out[k]}}
        elif k in out:
            out[k] = v
    return out


def load() -> dict:
    with _lock:
        if not FILE.exists():
            return copy.deepcopy(DEFAULTS)
        try:
            cur = _merge(DEFAULTS, json.loads(FILE.read_text(encoding="utf-8")))
            if is_retired(cur.get("model", "")):                       # modèle arrêté par Google : on l'oublie
                log.info("Modèle %s arrêté par Google : abandonné.", cur["model"])
                cur["model"] = ""
            return cur
        except Exception as e:
            bad = FILE.with_name(f"settings.corrompu-{int(time.time())}.json")
            try:
                FILE.rename(bad)
            except OSError:
                pass
            log.warning("settings.json illisible (%s) : sauvegardé sous %s, valeurs par défaut utilisées.", type(e).__name__, bad.name)
            return copy.deepcopy(DEFAULTS)


def _save(data: dict) -> None:
    tmp = FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, FILE)


def effective_model(s=None) -> str:
    s = s or load()
    env = os.getenv("GEMINI_MODEL", "").strip()
    return s.get("model") or (env if env and not is_retired(env) else "") or DEFAULT_MODEL


def _bool(v, name):
    if not isinstance(v, bool):
        raise ValueError(f"« {name} » doit être vrai ou faux.")
    return v


def validate_patch(patch: dict) -> dict:
    """Valide une modification partielle. Lève ValueError (message en français) si invalide."""
    if not isinstance(patch, dict):
        raise ValueError("Format de paramètres invalide.")
    clean = {}
    for k, v in patch.items():
        if k == "model":
            if not isinstance(v, str) or not re.fullmatch(r"[A-Za-z0-9._\-/]{3,80}", v):
                raise ValueError("Nom de modèle invalide.")
            if is_retired(v):
                raise ValueError("Ce modèle a été arrêté par Google : choisis-en un autre dans la liste.")
            clean[k] = v.removeprefix("models/")
        elif k in ("autostart", "tray"):
            clean[k] = _bool(v, k)
        elif k == "startup_behavior":
            if v not in ("open", "background"):
                raise ValueError("Comportement au démarrage invalide.")
            clean[k] = v
        elif k == "voice":
            if not isinstance(v, dict):
                raise ValueError("Paramètres de voix invalides.")
            vc = {}
            for kk, vv in v.items():
                if kk in ("stt_enabled", "tts_enabled"):
                    vc[kk] = _bool(vv, kk)
                elif kk == "voice_name":
                    if not isinstance(vv, str) or len(vv) > 150:
                        raise ValueError("Nom de voix invalide.")
                    vc[kk] = vv
                elif kk == "rate":
                    if isinstance(vv, bool) or not isinstance(vv, (int, float)) or not 0.5 <= vv <= 2.0:
                        raise ValueError("Le débit doit être entre 0,5 et 2.")
                    vc[kk] = float(vv)
                elif kk == "volume":
                    if isinstance(vv, bool) or not isinstance(vv, (int, float)) or not 0.0 <= vv <= 1.0:
                        raise ValueError("Le volume doit être entre 0 et 1.")
                    vc[kk] = float(vv)
                else:
                    raise ValueError(f"Paramètre de voix inconnu : {kk}")
            clean[k] = vc
        else:
            raise ValueError(f"Paramètre inconnu : {k}")
    return clean


def update(patch: dict) -> dict:
    clean = validate_patch(patch)
    with _lock:
        cur = load()
        for k, v in clean.items():
            cur[k] = {**cur[k], **v} if k == "voice" else v
        _save(cur)
        return cur


def reset_preferences() -> dict:
    with _lock:
        cur = load()
        for k in RESETTABLE:
            cur[k] = copy.deepcopy(DEFAULTS[k])
        _save(cur)
        return cur
