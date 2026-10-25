"""Accès à l'API officielle Google Gemini : client, test de connexion, liste des modèles, classement des erreurs.

La clé est lue (dans l'ordre) : 1) stockage sécurisé de Ziggy (Paramètres), 2) variable d'environnement GEMINI_API_KEY.
Elle n'est jamais écrite dans les journaux ni renvoyée à l'interface.
"""
import os, re, threading, time
import httpx
from google import genai
from google.genai import types, errors
import secrets_store, settings
from logsetup import get_logger, register_secret

log = get_logger("gemini")
NO_KEY_MSG = ("Aucune clé Gemini configurée. Ouvre Paramètres (⚙) → « Intelligence artificielle — Gemini », "
              "colle ta clé (gratuite sur https://aistudio.google.com/apikey), puis clique sur Enregistrer.")
PLACEHOLDERS = {"", "colle_ta_cle_ici", "colle_ta_clé_ici", "ta_clé", "ta_cle", "votre_clé", "your_api_key"}
# Modèles qui ne servent pas à discuter/appeler des outils : exclus de la liste
EXCLUDE = ("embedding", "tts", "image", "live", "audio", "robotics", "computer-use", "imagen", "veo", "aqa", "learnlm")
STATUS_LABELS = {"connected": "Connecté", "missing": "Clé manquante", "invalid": "Clé invalide", "quota": "Quota atteint",
                 "network": "Erreur réseau", "model": "Modèle introuvable", "denied": "Accès refusé",
                 "service": "Service indisponible", "error": "Erreur", "unknown": "Non testé"}

_lock = threading.Lock()
_state = {"client": None, "key": None, "source": None, "last_test": None}


# ---------- clé et client ----------
def resolve_key():
    """(clé, source) ; source = 'stockage' | 'environnement' | None."""
    try:
        k = secrets_store.load_key()
        if k and k.strip().lower() not in PLACEHOLDERS:
            return k.strip(), "stockage"
    except secrets_store.SecretError as e:
        log.warning("Clé stockée illisible : %s", e)
    env = os.getenv("GEMINI_API_KEY", "").strip()
    if env.lower() not in PLACEHOLDERS:
        return env, "environnement"
    return None, None


def _new_client(key: str, timeout_ms: int = 60_000):
    register_secret(key)
    return genai.Client(api_key=key, http_options=types.HttpOptions(timeout=timeout_ms))


def get_client():
    key, src = resolve_key()
    with _lock:
        if not key:
            _state.update(client=None, key=None, source=None)
            return None
        if _state["client"] is None or _state["key"] != key:
            _state.update(client=_new_client(key), key=key, source=src)
        return _state["client"]


def reset():
    """À appeler après modification/suppression de la clé : la nouvelle config est utilisée tout de suite."""
    with _lock:
        _state.update(client=None, key=None, source=None, last_test=None)


# ---------- classement des erreurs ----------
def _chain(e):
    seen = set()
    while e is not None and id(e) not in seen:
        seen.add(id(e))
        yield e
        e = e.__cause__ or e.__context__


def classify_error(e: Exception):
    """(statut, message en français). Statuts : invalid, quota, network, model, denied, service, error."""
    if str(e) == NO_KEY_MSG:
        return "missing", NO_KEY_MSG
    for x in _chain(e):
        if isinstance(x, errors.APIError):
            code = getattr(x, "code", None)
            text = f"{getattr(x, 'status', '')} {getattr(x, 'message', '')} {x}"
            if code in (401,) or "API_KEY_INVALID" in text or "API key not valid" in text or "UNAUTHENTICATED" in text:
                return "invalid", "Clé Gemini refusée : elle est incorrecte, expirée ou révoquée. Vérifie-la sur https://aistudio.google.com/apikey."
            if code == 429 or "RESOURCE_EXHAUSTED" in text:
                return "quota", ("Quota Gemini atteint pour ce modèle et ce compte. La clé est valide : attends un peu, choisis un autre "
                                 "modèle dans Paramètres, ou vérifie ton offre sur https://aistudio.google.com.")
            if code == 403 or "PERMISSION_DENIED" in text:
                return "denied", "Accès refusé par Gemini : la clé n'a pas le droit d'utiliser ce modèle, ou ton pays/projet n'est pas autorisé."
            if code == 404 or "NOT_FOUND" in text:
                return "model", "Modèle introuvable ou indisponible pour ton compte : choisis-en un autre dans Paramètres."
            if isinstance(code, int) and code >= 500:
                return "service", f"Le service Gemini est temporairement indisponible (erreur {code}). Réessaie dans un moment."
            return "error", f"Gemini a refusé la requête (erreur {code}) : {str(getattr(x, 'message', '') or x)[:200]}"
    for x in _chain(e):
        if isinstance(x, (httpx.TransportError, ConnectionError, TimeoutError, OSError)):
            return "network", "Impossible de joindre Gemini : vérifie ta connexion Internet, ton pare-feu ou ton proxy."
    return "error", f"Erreur inattendue ({type(e).__name__}) : {str(e)[:200]}"


def friendly_error(e: Exception) -> str:
    return classify_error(e)[1]


# ---------- test de connexion réel ----------
def _try(client, model):
    t0 = time.time()
    try:
        client.models.get(model=model)
        client.models.generate_content(model=model, contents="Réponds uniquement : OK",
                                       config=types.GenerateContentConfig(max_output_tokens=16))
    except Exception as e:
        status, msg = classify_error(e)
        log.warning("Test de connexion Gemini : %s (%s)", status, type(e).__name__)
        return _result(status, msg, model)
    return _result("connected", f"Connexion réussie : le modèle {model} répond.", model, int((time.time() - t0) * 1000))


def test_connection(key=None, model=None) -> dict:
    """Appelle réellement l'API : 1) lecture du modèle (valide la clé), 2) petite génération (valide quota et modèle).
    Ne renvoie 'connected' que si les deux appels ont réussi. Si le modèle n'existe plus, Ziggy en choisit un autre
    et le re-teste."""
    model = model or settings.effective_model()
    if key is not None and key.strip().lower() in PLACEHOLDERS:
        return _result("missing", NO_KEY_MSG, model)
    client = _new_client(key.strip(), 20_000) if key else get_client()
    if client is None:
        return _result("missing", NO_KEY_MSG, model)
    res = _try(client, model)
    if res["status"] == "model":
        best = auto_fix_model(client, model)
        if best:
            res2 = _try(client, best)
            if res2["status"] == "connected":
                res2["message"] = f"Le modèle {model} n'est plus disponible : Ziggy est passé automatiquement à {best}. " + res2["message"]
            return res2
    return res


def _result(status, message, model, latency_ms=None) -> dict:
    r = {"status": status, "label": STATUS_LABELS.get(status, status), "message": message, "model": model, "latency_ms": latency_ms,
         "checked_at": time.strftime("%Y-%m-%d %H:%M:%S")}
    if _state is not None:
        _state["last_test"] = r
    return r


def _list_models(client) -> list:
    out = []
    for m in client.models.list():
        name = (m.name or "").removeprefix("models/")
        if "generateContent" not in (getattr(m, "supported_actions", None) or []):
            continue
        if not name.startswith("gemini") or any(x in name for x in EXCLUDE) or settings.is_retired(name):
            continue
        out.append({"name": name, "display_name": getattr(m, "display_name", None) or name})
    out.sort(key=lambda m: m["name"])
    return out


_RX = {k: re.compile(rf"^gemini-(\d+(?:\.\d+)?)-{k}$") for k in ("flash", "flash-lite", "pro")}


def pick_best(models):
    """Meilleur modèle pour Ziggy parmi ceux du compte : le Flash STABLE le plus récent (rapide, appels d'outils,
    offre gratuite), puis Flash-Lite, puis Pro, puis un Flash en préversion. Renvoie un nom, ou None."""
    names = [m["name"] if isinstance(m, dict) else m for m in models]
    names = [n for n in names if not settings.is_retired(n)]
    for kind in ("flash", "flash-lite", "pro"):
        cands = [(tuple(int(x) for x in m.group(1).split(".")), n) for n in names if (m := _RX[kind].match(n))]
        if cands:
            return max(cands)[1]
    pre = sorted(n for n in names if "flash" in n)
    return pre[-1] if pre else (names[0] if names else None)


def auto_fix_model(client, failed: str):
    """Le modèle configuré n'existe plus (404) : choisit et enregistre le meilleur modèle disponible. Renvoie son nom ou None."""
    try:
        best = pick_best([m for m in _list_models(client) if m["name"] != failed])
    except Exception as e:
        log.warning("Choix automatique du modèle impossible : %s", type(e).__name__)
        return None
    if best:
        settings.update({"model": best})
        log.info("Modèle %s indisponible : remplacé automatiquement par %s.", failed, best)
    return best


def list_models(key=None) -> dict:
    """Modèles réellement proposés par l'API pour CE compte, compatibles génération de texte."""
    client = _new_client(key.strip(), 20_000) if key else get_client()
    if client is None:
        return {"status": "missing", "message": NO_KEY_MSG, "models": []}
    try:
        out = _list_models(client)
        return {"status": "connected", "message": f"{len(out)} modèle(s) disponible(s) pour ton compte.", "models": out,
                "suggested": pick_best(out)}
    except Exception as e:
        status, msg = classify_error(e)
        return {"status": status, "message": msg, "models": []}


def summary() -> dict:
    """État résumé, sans aucun secret."""
    key, src = resolve_key()
    return {"configured": bool(key), "source": src, "last4": secrets_store.last4() if src == "stockage" else None,
            "protection": secrets_store.protection_label(), "model": settings.effective_model(), "last_test": _state["last_test"]}
