"""Gemini : clé absente/invalide, quota, réseau. Chaque test indique s'il est RÉEL ou SIMULÉ."""
import os, pytest
from google import genai
from google.genai import errors, types
from conftest import FAKE_KEY, FakeClient


def api_error(code, status, msg):
    return errors.APIError(code, {"error": {"code": code, "status": status, "message": msg}})


# ---- SIMULÉ : on fabrique l'erreur que renvoie l'API, pour vérifier le classement et les messages ----
@pytest.mark.parametrize("code,status,msg,expected", [
    (400, "INVALID_ARGUMENT", "API key not valid. Please pass a valid API key.", "invalid"),
    (401, "UNAUTHENTICATED", "Request had invalid authentication credentials.", "invalid"),
    (429, "RESOURCE_EXHAUSTED", "Quota exceeded for metric", "quota"),
    (403, "PERMISSION_DENIED", "The caller does not have permission", "denied"),
    (404, "NOT_FOUND", "models/xyz is not found", "model"),
    (503, "UNAVAILABLE", "The model is overloaded", "service"),
    (400, "INVALID_ARGUMENT", "Request payload malformed", "error"),
])
def test_SIMULE_classement_des_erreurs_de_l_api(app, code, status, msg, expected):
    got, message = app.gemini.classify_error(api_error(code, status, msg))
    assert got == expected and message
    assert FAKE_KEY not in message


def test_SIMULE_message_de_quota_explique_que_la_cle_est_valide(app):
    _, m = app.gemini.classify_error(api_error(429, "RESOURCE_EXHAUSTED", "quota"))
    assert "valide" in m and "modèle" in m


def test_SIMULE_erreur_reseau_httpx(app):
    import httpx
    assert app.gemini.classify_error(httpx.ConnectError("boom"))[0] == "network"
    assert app.gemini.classify_error(httpx.ReadTimeout("slow"))[0] == "network"
    try:
        try: raise ConnectionRefusedError("x")
        except Exception as inner: raise RuntimeError("enveloppe") from inner
    except Exception as e:
        assert app.gemini.classify_error(e)[0] == "network"          # cause réseau retrouvée dans la chaîne


# ---- Clé absente ----
def test_REEL_cle_absente_message_clair_et_pas_d_appel(app, api):
    assert app.gemini.get_client() is None
    r = api.post("/api/gemini/test")
    assert r.json["status"] == "missing" and "Paramètres" in r.json["message"]
    r = api.post("/api/chat", {"message": "salut"})
    assert r.status_code == 500 and "Aucune clé Gemini" in r.json["reply"]
    assert api.post("/api/gemini/models").json["status"] == "missing"


# ---- RÉEL : erreur de connexion produite par la vraie pile HTTP (port fermé), sans rien simuler ----
def test_REEL_erreur_reseau_vers_un_port_ferme(app, monkeypatch):
    client = genai.Client(api_key=FAKE_KEY, http_options=types.HttpOptions(base_url="http://127.0.0.1:9", timeout=3000))
    monkeypatch.setattr(app.gemini, "get_client", lambda: client)
    r = app.gemini.test_connection()
    assert r["status"] == "network" and r["status"] != "connected"
    assert "connexion" in r["message"].lower()


# ---- RÉEL : appel à la vraie API avec une fausse clé. Hors ligne => network ; en ligne => invalid. ----
@pytest.mark.real_call
def test_REEL_fausse_cle_vers_la_vraie_api(app, api):
    api.post("/api/gemini/key", {"key": FAKE_KEY})
    r = api.post("/api/gemini/test").json
    assert r["status"] in ("network", "invalid"), r           # jamais « connected » avec une fausse clé
    assert r["status"] != "connected"
    print("  -> résultat réel dans cet environnement :", r["status"])


# ---- SIMULÉ : logique du test en deux appels ----
def test_SIMULE_connecte_seulement_si_les_deux_appels_reussissent(app, monkeypatch):
    ok = FakeClient()
    monkeypatch.setattr(app.gemini, "get_client", lambda: ok)
    assert app.gemini.test_connection()["status"] == "connected"
    quota = FakeClient(fail=api_error(429, "RESOURCE_EXHAUSTED", "quota"))
    monkeypatch.setattr(app.gemini, "get_client", lambda: quota)
    r = app.gemini.test_connection()
    assert r["status"] == "quota" and "connected" not in r["status"]
    bad = FakeClient(fail=api_error(400, "INVALID_ARGUMENT", "API key not valid"))
    monkeypatch.setattr(app.gemini, "get_client", lambda: bad)
    assert app.gemini.test_connection()["status"] == "invalid"


def test_SIMULE_liste_des_modeles_filtree(app, monkeypatch):
    M = lambda n, acts, d="": types.Model(name=n, display_name=d or n, supported_actions=acts)
    class L:
        class models:
            @staticmethod
            def list():
                return [M("models/gemini-3.5-flash", ["generateContent"], "Flash"), M("models/gemini-embedding-001", ["embedContent"]),
                        M("models/gemini-3.5-flash-preview-tts", ["generateContent"]), M("models/gemma-3-27b", ["generateContent"]),
                        M("models/gemini-3.7-flash", ["generateContent", "countTokens"]), M("models/imagen-4", ["predict"])]
    monkeypatch.setattr(app.gemini, "get_client", lambda: L)
    r = app.gemini.list_models()
    assert [m["name"] for m in r["models"]] == ["gemini-3.5-flash", "gemini-3.7-flash"]


@pytest.mark.real_gemini
@pytest.mark.skipif(not os.getenv("ZIGGY_TEST_GEMINI_KEY"), reason="Exige une VRAIE clé : définir ZIGGY_TEST_GEMINI_KEY (non exécuté ici)")
def test_VRAIE_CLE_connexion_et_modeles(app, api):
    key = os.environ["ZIGGY_TEST_GEMINI_KEY"]
    assert api.post("/api/gemini/key", {"key": key}).json["ok"]
    assert api.post("/api/gemini/test").json["status"] == "connected"
    assert api.post("/api/gemini/models").json["models"]
