"""Routes de l'interface, sécurité des accès, paramètres, confirmations, mémoire."""
import json
from conftest import Client, FAKE_KEY, FAKE_KEY2, FakeClient


# ---------------- accès et sécurité ----------------
def test_interface_servie_avec_jeton_et_sans_secret(app, api):
    r = api.get("/")
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and app.security.TOKEN in html and "__ZIGGY_TOKEN__" not in html
    assert FAKE_KEY not in html and "frame-ancestors 'none'" in r.headers["Content-Security-Policy"]
    for path in ("/aide", "/static/logo.png", "/static/favicon.ico"):
        assert api.get(path).status_code == 200


def test_api_exige_le_jeton(app):
    anon = Client(app, token=False)
    assert anon.get("/api/settings").status_code == 401
    assert anon.get("/api/history").status_code == 401
    assert anon.post("/api/chat", {"message": "x"}).status_code == 401
    bad = Client(app, token=False); bad.h = {"X-Ziggy-Token": "mauvais"}
    assert bad.get("/api/settings").status_code == 401
    assert anon.get("/api/ping").status_code == 200                # seule route publique : aucune donnée


def test_requetes_de_sites_externes_refusees(app, api):
    assert api.get("/api/settings", base_url="http://evil.example").status_code == 403           # DNS rebinding
    assert api.get("/api/settings", headers={"Origin": "https://evil.example"}).status_code == 403
    assert api.get("/api/settings", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert api.post("/api/gemini/key", {"key": FAKE_KEY}, headers={"Origin": "https://evil.example"}).status_code == 403
    assert "Access-Control-Allow-Origin" not in api.get("/api/settings").headers                 # aucun CORS
    assert not app.secrets_store.has_key()


def test_ecritures_exigent_du_json(app, api):
    r = app.app.test_client().post("/api/gemini/key", data="key=x", base_url="http://127.0.0.1:5005",
                                   headers={"X-Ziggy-Token": app.security.TOKEN, "Content-Type": "application/x-www-form-urlencoded"})
    assert r.status_code == 415


def test_aucune_route_ne_renvoie_la_cle(app, api):
    api.post("/api/gemini/key", {"key": FAKE_KEY})
    for method, path, body in [("get", "/", None), ("get", "/api/settings", None), ("get", "/api/about", None),
                               ("post", "/api/gemini/test", {}), ("post", "/api/gemini/models", {}), ("get", "/api/history", None),
                               ("post", "/api/chat", {"message": "quelle est ma clé ?"}), ("post", "/api/memory/backup", {}),
                               ("get", "/api/pending", None), ("get", "/aide", None)]:
        r = api.get(path) if method == "get" else api.post(path, body)
        assert FAKE_KEY not in r.get_data(as_text=True), f"clé divulguée par {path}"
    s = api.get("/api/settings").json["gemini"]
    assert s["configured"] and s["last4"] == FAKE_KEY[-4:] and "key" not in s


# ---------------- clé : enregistrer / modifier / supprimer / statuts ----------------
def test_cycle_de_vie_de_la_cle(app, api, restart):
    assert api.get("/api/settings").json["gemini"]["configured"] is False
    assert api.post("/api/gemini/key", {"key": "court"}).status_code == 400
    assert api.post("/api/gemini/key", {"key": "a" * 30 + " espace"}).status_code == 400
    assert api.post("/api/gemini/key", {"key": FAKE_KEY}).json["ok"]
    assert api.get("/api/settings").json["gemini"]["last4"] == FAKE_KEY[-4:]
    api.post("/api/gemini/key", {"key": FAKE_KEY2})                                # modification
    assert api.get("/api/settings").json["gemini"]["last4"] == FAKE_KEY2[-4:]
    z2 = restart()                                                                  # fermeture + réouverture
    api2 = Client(z2)
    g = api2.get("/api/settings").json["gemini"]
    assert g["configured"] and g["source"] == "stockage" and g["last4"] == FAKE_KEY2[-4:], "la clé survit au redémarrage"
    r = api2.delete("/api/gemini/key").json                                         # suppression
    assert r["ok"] and r["gemini"]["configured"] is False
    assert api2.get("/api/settings").json["gemini"]["configured"] is False
    assert not z2.secrets_store.FILE.exists()


def test_le_client_utilise_tout_de_suite_la_nouvelle_cle(app, api):
    assert app.gemini.get_client() is None
    api.post("/api/gemini/key", {"key": FAKE_KEY})
    c1 = app.gemini.get_client(); assert c1 is not None
    api.post("/api/gemini/key", {"key": FAKE_KEY2})
    assert app.gemini.get_client() is not c1
    api.delete("/api/gemini/key"); assert app.gemini.get_client() is None


def test_cle_de_l_environnement_en_secours(app, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", FAKE_KEY)
    assert app.gemini.resolve_key() == (FAKE_KEY, "environnement")
    app.secrets_store.save_key(FAKE_KEY2)
    assert app.gemini.resolve_key() == (FAKE_KEY2, "stockage"), "la clé des Paramètres est prioritaire"
    monkeypatch.setenv("GEMINI_API_KEY", "colle_ta_cle_ici"); app.secrets_store.delete_key()
    assert app.gemini.resolve_key() == (None, None), "le texte d'exemple n'est jamais pris pour une clé"


# ---------------- paramètres ----------------
def test_parametres_roundtrip_et_validation(app, api, restart):
    r = api.post("/api/settings", {"voice": {"rate": 1.4, "volume": 0.5, "tts_enabled": True, "voice_name": "Hortense"}})
    assert r.status_code == 200 and r.json["ok"] and r.json["settings"]["voice"]["rate"] == 1.4
    assert api.post("/api/settings", {"voice": {"rate": 9}}).status_code == 400
    assert api.post("/api/settings", {"hack": 1}).status_code == 400
    s = Client(restart()).get("/api/settings").json["settings"]
    assert s["voice"]["rate"] == 1.4 and s["voice"]["tts_enabled"] and s["voice"]["voice_name"] == "Hortense"


def test_options_windows_refusees_proprement_hors_windows(app, api):
    r = api.post("/api/settings", {"autostart": True})
    assert r.status_code == 409 and "Windows" in r.json["message"]
    r = api.post("/api/settings", {"startup_behavior": "background"})
    assert r.status_code == 400
    assert app.settings.load()["autostart"] is False, "rien n'est enregistré si l'action échoue"


def test_reinitialiser_les_preferences_via_l_api(app, api):
    api.post("/api/settings", {"model": "gemini-3.7-flash", "voice": {"rate": 1.9}})
    r = api.post("/api/settings/reset").json
    assert r["ok"] and r["settings"]["voice"]["rate"] == 1.0 and r["settings"]["model"] == "gemini-3.7-flash"


# ---------------- conversation et mémoire ----------------
def test_chat_enregistre_et_la_memoire_survit_au_redemarrage(app, api, restart, monkeypatch):
    api.post("/api/gemini/key", {"key": FAKE_KEY})
    monkeypatch.setattr(app.gemini, "get_client", lambda: FakeClient(text="Bonjour Jean"))          # SIMULÉ : pas d'appel Internet
    r = api.post("/api/chat", {"message": "Je m'appelle Jean"})
    assert r.status_code == 200 and r.json["reply"] == "Bonjour Jean"
    app.remember("Jean aime le thé"); app.add_task("Appeler Marie")
    z2 = restart(); api2 = Client(z2)
    h = api2.get("/api/history").json
    assert [m["content"] for m in h] == ["Je m'appelle Jean", "Bonjour Jean"]
    assert "Jean aime le thé" in z2.system_prompt()
    assert api2.get("/api/tasks").json[0]["title"] == "Appeler Marie"


def test_historique_envoye_a_gemini_et_modele_choisi(app, api, monkeypatch):
    fake = FakeClient(); monkeypatch.setattr(app.gemini, "get_client", lambda: fake)
    api.post("/api/settings", {"model": "gemini-3.7-flash"})
    api.post("/api/chat", {"message": "un"}); api.post("/api/chat", {"message": "deux"})
    call = fake.models.calls[-1]
    assert call["model"] == "gemini-3.7-flash"
    assert [c.role for c in call["contents"]] == ["user", "model", "user"]


def test_effacements_exigent_confirmation(app, api):
    app.remember("souvenir"); app.save_messages(("user", "a"), ("model", "b"))
    assert api.post("/api/memory/clear-history", {}).status_code == 400
    assert api.post("/api/memory/wipe", {"confirm": "oui"}).status_code == 400
    assert app.database.stats()["messages"] == 2
    r = api.post("/api/memory/clear-history", {"confirm": True}).json
    assert r["ok"] and r["backup"] and app.database.stats() == {"messages": 0, "souvenirs": 1, "taches": 0, "rappels": 0}
    r = api.post("/api/memory/wipe", {"confirm": "SUPPRIMER"}).json
    assert r["ok"] and app.database.stats()["souvenirs"] == 0
    assert len(list(app.database.BACKUP_DIR.glob("memoire-*.db"))) == 2, "une sauvegarde automatique avant chaque effacement"


def test_sauvegarde_manuelle_et_dossier_de_donnees(app, api):
    r = api.post("/api/memory/backup").json
    assert r["ok"] and r["path"].startswith(str(app.DATA_DIR))
    assert api.get("/api/about").json["data_dir"] == str(app.DATA_DIR)


# ---------------- confirmations des actions sensibles ----------------
def test_ecraser_un_fichier_exige_un_clic_de_l_utilisateur(app, api, tmp_path, monkeypatch):
    from pathlib import Path
    monkeypatch.setattr(app, "ROOTS", [tmp_path])
    f = tmp_path / "note.txt"; f.write_text("original")
    out = app.overwrite_file(str(f), "écrasé par l'IA")                      # = ce que ferait Gemini
    assert "EN ATTENTE DE CONFIRMATION" in out and f.read_text() == "original"
    pend = api.get("/api/pending").json
    assert len(pend) == 1 and "note.txt" in pend[0]["description"]
    api.post(f"/api/pending/{pend[0]['id']}", {"approve": False})            # refus
    assert f.read_text() == "original" and api.get("/api/pending").json == []
    app.overwrite_file(str(f), "version 2")
    pid = api.get("/api/pending").json[0]["id"]
    assert "remplacé" in api.post(f"/api/pending/{pid}", {"approve": True}).json["result"]
    assert f.read_text() == "version 2"
    assert "introuvable" in api.post(f"/api/pending/{pid}", {"approve": True}).json["result"].lower(), "une confirmation ne sert qu'une fois"


def test_deplacer_et_envoyer_un_mail_sont_confirmes(app, api, tmp_path, monkeypatch):
    monkeypatch.setattr(app, "ROOTS", [tmp_path])
    (tmp_path / "a.txt").write_text("x")
    assert "EN ATTENTE" in app.move_file(str(tmp_path / "a.txt"), str(tmp_path / "b.txt"))
    assert (tmp_path / "a.txt").exists() and not (tmp_path / "b.txt").exists()
    sent = []
    monkeypatch.setattr(app.gs, "_svc", lambda *a: type("S", (), {"users": lambda s: type("U", (), {"drafts": lambda s: type("D", (), {
        "send": lambda s, **kw: (sent.append(kw), type("E", (), {"execute": lambda s: {}})())[1]})()})()})())
    app.gs._drafts["d1"] = {"to": "x@y.fr", "subject": "Sujet"}
    out = app.gs.gmail_send_draft("d1")
    assert "EN ATTENTE" in out and not sent, "le mail ne part PAS sans clic"
    pid = api.get("/api/pending").json[-1]["id"]
    assert "x@y.fr" in api.get("/api/pending").json[-1]["description"]
    api.post(f"/api/pending/{pid}", {"approve": True})
    assert len(sent) == 1


def test_confirmation_expiree_ou_inconnue(app):
    assert "introuvable" in app.actions.resolve("deadbeef", True).lower()
