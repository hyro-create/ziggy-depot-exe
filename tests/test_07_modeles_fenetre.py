"""Bug « modèle introuvable » (gemini-2.5-* arrêtés par Google le 16/10/2026) et mode fenêtre dédiée."""
import json, pytest
from google.genai import errors, types
from conftest import Client, FAKE_KEY, FakeClient, FakeResp


def e404(model="gemini-2.5-flash"):
    return errors.APIError(404, {"error": {"code": 404, "status": "NOT_FOUND", "message": f"This model models/{model} is no longer available."}})


MODELS = ["gemini-3.5-flash", "gemini-3.7-flash", "gemini-3.8-flash", "gemini-3.1-flash-lite", "gemini-3.1-pro-preview",
          "gemini-3-flash-preview", "gemini-3.5-flash-lite", "gemini-2.5-flash", "gemini-2.5-pro"]


def test_choix_du_meilleur_modele(app):
    pb = app.gemini.pick_best
    assert pb(MODELS) == "gemini-3.8-flash", "le Flash stable le plus récent, jamais un modèle arrêté"
    assert pb(["gemini-3.5-flash-lite", "gemini-3.1-pro-preview", "gemini-3-flash-preview"]) == "gemini-3.5-flash-lite"
    assert pb(["gemini-3.1-pro-preview", "gemini-3-flash-preview"]) == "gemini-3-flash-preview"
    assert pb(["gemini-2.5-flash", "gemini-2.5-pro"]) is None, "uniquement des modèles arrêtés -> rien à choisir"
    assert pb([{"name": "gemini-3.6-flash"}, {"name": "gemini-3.10-flash"}]) == "gemini-3.10-flash", "comparaison numérique des versions"
    assert pb([]) is None


def test_defaut_n_est_plus_un_modele_arrete(app):
    assert app.settings.DEFAULT_MODEL == "gemini-3.5-flash" and not app.settings.is_retired(app.settings.DEFAULT_MODEL)
    for old in ("gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash", "gemini-1.5-pro", "gemini-pro", "models/gemini-2.5-flash-lite"):
        assert app.settings.is_retired(old), old
    for ok in ("gemini-3.5-flash", "gemini-3.1-flash-lite", "gemini-3-flash-preview"):
        assert not app.settings.is_retired(ok), ok


def test_ancien_reglage_arrete_est_oublie_apres_mise_a_jour(home, monkeypatch):
    """L'utilisateur avait gemini-2.5-flash enregistré : après mise à jour, ça ne doit plus bloquer Ziggy."""
    from conftest import load_app
    home.mkdir(parents=True)
    (home / "settings.json").write_text(json.dumps({"model": "gemini-2.5-flash", "voice": {"rate": 1.2}}), encoding="utf-8")
    z = load_app(home, monkeypatch)
    assert z.settings.effective_model() == "gemini-3.5-flash" and z.settings.load()["voice"]["rate"] == 1.2
    monkeypatch.setenv("GEMINI_MODEL", "gemini-2.5-pro")
    assert z.settings.effective_model() == "gemini-3.5-flash", "GEMINI_MODEL périmé ignoré"
    assert Client(z).post("/api/settings", {"model": "gemini-2.5-flash"}).status_code == 400, "impossible de re-choisir un modèle arrêté"


class Flaky:
    """SIMULÉ : l'API répond 404 pour le modèle périmé, et fonctionne pour les autres."""
    def __init__(self, dead="gemini-2.5-flash", available=MODELS):
        self.dead, self.calls = dead, []
        self.available = [types.Model(name="models/" + n, supported_actions=["generateContent"]) for n in available if n != dead]
        flaky = self
        class Models:
            def get(s, model):
                if model == flaky.dead: raise e404(model)
            def generate_content(s, model, **kw):
                flaky.calls.append(model)
                if model == flaky.dead: raise e404(model)
                return FakeResp("Réponse OK")
            def list(s): return flaky.available
        self.models = Models()


def test_SIMULE_chat_se_repare_tout_seul_quand_le_modele_n_existe_plus(app, api, monkeypatch):
    app.settings.update({"model": "gemini-3.5-flash"}); fl = Flaky(dead="gemini-3.5-flash")
    monkeypatch.setattr(app.gemini, "get_client", lambda: fl)
    r = api.post("/api/chat", {"message": "bonjour"})
    assert r.status_code == 200 and "Réponse OK" in r.json["reply"]
    assert "n'est plus disponible" in r.json["reply"] and "gemini-3.8-flash" in r.json["reply"]
    assert fl.calls == ["gemini-3.5-flash", "gemini-3.8-flash"], "un seul réessai avec le nouveau modèle"
    assert app.settings.effective_model() == "gemini-3.8-flash", "le nouveau modèle est mémorisé"
    api.post("/api/chat", {"message": "encore"})
    assert fl.calls[-1] == "gemini-3.8-flash" and len(fl.calls) == 3, "plus de réparation nécessaire ensuite"


def test_SIMULE_test_de_connexion_repare_le_modele(app, monkeypatch):
    fl = Flaky(dead="gemini-3.5-flash"); monkeypatch.setattr(app.gemini, "get_client", lambda: fl)
    r = app.gemini.test_connection()
    assert r["status"] == "connected" and r["model"] == "gemini-3.8-flash" and "automatiquement" in r["message"]


def test_SIMULE_aucun_modele_disponible_message_clair(app, api, monkeypatch):
    fl = Flaky(dead="gemini-3.5-flash", available=["gemini-2.5-pro", "gemini-3.5-flash"])
    monkeypatch.setattr(app.gemini, "get_client", lambda: fl)
    r = api.post("/api/chat", {"message": "x"})
    assert r.status_code == 500 and "Modèle introuvable" in r.json["reply"]


def test_SIMULE_liste_des_modeles_propose_un_choix(app, api, monkeypatch):
    fl = Flaky(dead="gemini-2.5-flash"); monkeypatch.setattr(app.gemini, "get_client", lambda: fl)
    r = api.post("/api/gemini/models").json
    names = [m["name"] for m in r["models"]]
    assert r["suggested"] == "gemini-3.8-flash" and "gemini-2.5-pro" not in names and "gemini-2.5-flash" not in names


def test_une_autre_erreur_que_modele_n_est_pas_reessayee(app, api, monkeypatch):
    fake = FakeClient(fail=errors.APIError(429, {"error": {"status": "RESOURCE_EXHAUSTED", "message": "quota"}}))
    monkeypatch.setattr(app.gemini, "get_client", lambda: fake)
    r = api.post("/api/chat", {"message": "x"})
    assert r.status_code == 500 and "Quota" in r.json["reply"] and len(fake.models.calls) == 1


# ---------------- fenêtre WebView2 (pywebview) ----------------
def test_ziggy_ouvre_l_interface_selon_le_reglage(app, api, monkeypatch):
    import window as win
    fronted = []
    monkeypatch.setattr(win, 'bring_to_front', lambda: fronted.append(1))
    app.open_ui('/#settings')
    assert fronted == [1], "bring_to_front doit être appelé, jamais un navigateur"


def test_bouton_quitter_exige_confirmation(app, api, monkeypatch):
    quit_calls = []
    monkeypatch.setattr(app, "quit_app", lambda: quit_calls.append(1))
    assert api.post("/api/quit", {}).status_code == 400 and not quit_calls
    r = api.post("/api/quit", {"confirm": True})
    assert r.status_code == 200 and r.json["ok"]
    import time; time.sleep(0.9)
    assert quit_calls == [1]
