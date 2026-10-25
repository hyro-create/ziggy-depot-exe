"""Sécurité des actions Windows/fichiers/web, journaux, rappels, redémarrage et mise à jour sans perte."""
import inspect, json, logging, os, sqlite3, time
from pathlib import Path
import pytest
from conftest import Client, FAKE_KEY, FAKE_KEY2, load_app


# ---------------- aucune exécution libre ----------------
def test_aucun_outil_d_execution_de_commande(app):
    names = {t.__name__ for t in app.TOOLS}
    assert not names & {"run_command", "execute", "shell", "powershell", "cmd", "exec"}
    assert "Aucune autre commande" in app.system_action.__doc__ or "FIXE" in app.system_action.__doc__
    assert "non autorisée" in app.system_action("rm -rf /")
    assert "non autorisée" in app.system_action("powershell -c calc")


def test_open_target_ne_lance_rien_de_dangereux(app, tmp_path, monkeypatch):
    launched = []
    monkeypatch.setattr(app.subprocess, "Popen", lambda *a, **k: launched.append((a, k)))
    monkeypatch.setattr(app.webbrowser, "open", lambda u: launched.append(("web", u)))
    monkeypatch.setattr(app, "ROOTS", [tmp_path])
    for f in ("evil.sh", "evil.bat", "evil.ps1", "evil.exe", "evil.py", "evil.lnk"):
        (tmp_path / f).write_text("x")
        assert "Refusé" in app.open_target(str(tmp_path / f)), f
    for t in ("file:///etc/passwd", "javascript:alert(1)", "ms-settings:", "shell:startup", "rm -rf /", "notepad & calc", "../../etc/passwd", "calc.exe /c dir"):
        assert launched == [] and ("Refusé" in app.open_target(t) or "Introuvable" in app.open_target(t) or "Erreur" in app.open_target(t)), t
    assert launched == []
    assert app.open_target("https://exemple.fr").startswith("Ouvert") and launched == [("web", "https://exemple.fr")]


def test_applications_personnalisees_uniquement_exe_absolu_existant(app, tmp_path, monkeypatch):
    launched = []
    monkeypatch.setattr(app.subprocess, "Popen", lambda a, **k: launched.append(a))
    exe = tmp_path / "monapp.exe"; exe.write_text("x")
    app.settings._save({**app.settings.load(), "custom_apps": {"monapp": str(exe), "relatif": "monapp.exe", "script": str(tmp_path / "x.bat"), "absent": str(tmp_path / "nope.exe")}})
    assert app.open_target("monapp").startswith("Ouvert") and launched == [[str(exe)]]
    for bad in ("relatif", "script", "absent"):
        assert not app.open_target(bad).startswith("Ouvert")
    assert len(launched) == 1


def test_fichiers_executables_jamais_crees_ni_deplaces(app, tmp_path, monkeypatch):
    monkeypatch.setattr(app, "ROOTS", [tmp_path])
    for name in ("a.bat", "a.ps1", "Démarrage.cmd", "x.EXE", "z.vbs"):
        assert "Refusé" in app.write_file(str(tmp_path / name), "calc")
        assert "Refusé" in app.overwrite_file.__wrapped__(str(tmp_path / name), "calc")
        assert not (tmp_path / name).exists()
    (tmp_path / "ok.txt").write_text("x")
    assert "Refusé" in app.move_file.__wrapped__(str(tmp_path / "ok.txt"), str(tmp_path / "ok.bat"))
    assert app.write_file(str(tmp_path / "nouveau.txt"), "ok").startswith("Fichier écrit")
    assert "existe déjà" in app.write_file(str(tmp_path / "nouveau.txt"), "autre")


def test_les_donnees_de_ziggy_et_les_secrets_systeme_sont_illisibles_par_l_ia(app, monkeypatch):
    home = app.HOME
    monkeypatch.setattr(app, "ROOTS", [app.DATA_DIR.parent, home])
    app.secrets_store.save_key(FAKE_KEY)
    for p in (app.DATA_DIR / ".env", app.secrets_store.FILE, app.database.DB_PATH, app.DATA_DIR / "token.json", app.DATA_DIR):
        assert "Erreur" in str(app.read_file(str(p))) or "Erreur" in str(app.list_files(str(p))[0]), p
    assert FAKE_KEY not in str(app.read_file(str(app.secrets_store.FILE)))
    with pytest.raises(PermissionError):
        app._safe(str(home / ".ssh" / "id_rsa"))


def test_ssrf_les_adresses_locales_sont_refusees(app):
    for url in ("http://127.0.0.1:5005/", "http://localhost:5005/", "http://169.254.169.254/latest/meta-data/", "http://10.0.0.1/",
                "http://192.168.1.1/", "http://[::1]/", "file:///etc/passwd", "ftp://exemple.fr/x", "http://0.0.0.0/"):
        assert app.ex.check_public_url(url), f"{url} aurait dû être refusée"
        assert app.ex.read_webpage(url), url
    assert app.ex.check_public_url("http://8.8.8.8/") is None


def test_chaque_outil_est_declarable_pour_gemini(app):
    from google import genai
    from google.genai import types
    c = genai.Client(api_key=FAKE_KEY)
    for f in app.TOOLS:
        decl = types.FunctionDeclaration.from_callable(client=c._api_client, callable=f)
        assert decl.name == f.__name__ and decl.description, f.__name__
    assert list(inspect.signature(app.move_file).parameters) == ["source", "destination"]      # la signature survit au décorateur


# ---------------- journaux ----------------
def test_journaux_sans_secret(app, api):
    api.post("/api/gemini/key", {"key": FAKE_KEY})
    log = app.log
    log.info("Appel avec la clé %s et Authorization: Bearer abcdefghijklmnop1234", FAKE_KEY)
    log.info("api_key=%s token: supersecret123456", FAKE_KEY2)
    try:
        raise ValueError(f"échec avec {FAKE_KEY}")
    except ValueError:
        log.exception("erreur testée")
    api.post("/api/chat", {"message": "test"})
    for h in logging.getLogger("ziggy").handlers: h.flush()
    txt = (app.DATA_DIR / "logs" / "ziggy.log").read_text(encoding="utf-8")
    assert "erreur testée" in txt and "Appel avec la clé" in txt, "le journal fonctionne"
    for secret in (FAKE_KEY, FAKE_KEY2, "abcdefghijklmnop1234", "supersecret123456"):
        assert secret not in txt, f"secret dans le journal : {secret[:8]}…"
    assert "[SECRET]" in txt


# ---------------- rappels persistants ----------------
def test_rappels_persistants_et_validation(app, restart):
    r = app.ex.set_reminder("Appeler Paul", minutes=30)
    assert "programmé" in r and len(app.ex.list_reminders()) == 1
    for bad in (dict(text="", minutes=5), dict(text="x" * 400, minutes=5), dict(text="x", minutes=0), dict(text="x", minutes=-3),
                dict(text="x", at="pas une date"), dict(text="x", at="2001-01-01T10:00:00")):
        assert not app.reminders.add(**bad)[0], bad
    z2 = restart()
    assert z2.ex.list_reminders()[0]["texte"] == "Appeler Paul", "le rappel survit au redémarrage"
    assert "annulé" in z2.ex.cancel_reminder(z2.ex.list_reminders()[0]["id"]) and z2.ex.list_reminders() == ["Aucun rappel programmé."]


def test_rappel_echu_est_declenche_une_seule_fois_meme_apres_fermeture(app, restart):
    ok, _, rid = app.reminders.add("Médicament", minutes=60)
    with app.database.connect() as c:                                        # l'échéance passe pendant que Ziggy est fermé
        c.execute("UPDATE reminders SET due_ts=? WHERE id=?", (time.time() - 3600, rid))
    z2 = restart()
    got = []; z2.reminders.on_fire(got.append)
    assert z2.reminders.fire_due() == 1 and got[0]["missed"] is True
    assert z2.reminders.pop_due()[0]["text"] == "Médicament"
    assert z2.reminders.fire_due() == 0 and z2.reminders.pop_due() == []


# ---------------- fermeture/réouverture et mise à jour ----------------
def test_ensemble_des_donnees_apres_redemarrage(app, restart, monkeypatch):
    api = Client(app)
    api.post("/api/gemini/key", {"key": FAKE_KEY}); api.post("/api/settings", {"model": "gemini-3.7-flash", "voice": {"rate": 1.3}})
    app.remember("fait 1"); app.add_task("tâche 1"); app.reminders.add("r1", minutes=90)
    app.save_messages(("user", "u1"), ("model", "m1"))
    z = restart()
    assert z.gemini.resolve_key() == (FAKE_KEY, "stockage")
    assert z.settings.load()["model"] == "gemini-3.7-flash" and z.settings.load()["voice"]["rate"] == 1.3
    assert z.database.stats() == {"messages": 2, "souvenirs": 1, "taches": 1, "rappels": 1}


def test_mise_a_jour_du_logiciel_sans_perte_de_donnees(home, monkeypatch):
    """Données écrites par une version antérieure (base v1, anciens réglages sans les nouvelles clés, clé stockée)."""
    home.mkdir(parents=True)
    c = sqlite3.connect(home / "memoire.db")
    c.executescript("""CREATE TABLE messages(id INTEGER PRIMARY KEY, role TEXT, content TEXT, ts TEXT);
        CREATE TABLE facts(id INTEGER PRIMARY KEY, fact TEXT UNIQUE, ts TEXT);
        CREATE TABLE tasks(id INTEGER PRIMARY KEY, title TEXT, due TEXT, done INTEGER DEFAULT 0, ts TEXT);
        INSERT INTO messages(role,content,ts) VALUES('user','hier','t'),('model','réponse d''hier','t');
        INSERT INTO facts(fact,ts) VALUES('travaille chez Solar','t'); INSERT INTO tasks(title,ts) VALUES('tâche d''hier','t');
        PRAGMA user_version=1;"""); c.commit(); c.close()
    (home / "settings.json").write_text(json.dumps({"model": "gemini-3.7-flash", "voice": {"rate": 1.2}}), encoding="utf-8")
    import secrets_store  # noqa  (écrit la clé comme l'ancienne version l'aurait fait)
    monkeypatch.setenv("ZIGGY_HOME", str(home))
    import importlib, sys
    for m in ("paths", "logsetup", "secrets_store"): sys.modules.pop(m, None)
    importlib.import_module("secrets_store").save_key(FAKE_KEY)
    z = load_app(home, monkeypatch)                                          # première ouverture de la NOUVELLE version
    api = Client(z)
    st = api.get("/api/settings").json
    assert st["settings"]["model"] == "gemini-3.7-flash" and st["settings"]["voice"]["rate"] == 1.2, "réglages conservés"
    assert st["settings"]["voice"]["stt_enabled"] is True and "tray" in st["settings"], "nouvelles options ajoutées avec valeurs par défaut"
    assert st["gemini"]["configured"] and st["gemini"]["last4"] == FAKE_KEY[-4:], "clé conservée"
    assert [m["content"] for m in z.database.history()] == ["hier", "réponse d'hier"]
    assert "travaille chez Solar" in z.system_prompt() and z.list_tasks()[0]["title"] == "tâche d'hier"
    assert list((home / "backups").glob("memoire-avant-migration-*.db")), "sauvegarde avant migration"


def test_cle_dans_l_ancien_env_est_migree_vers_le_stockage_securise(home, monkeypatch):
    home.mkdir(parents=True)
    (home / ".env").write_text(f"TIMEZONE=Europe/Paris\nGEMINI_API_KEY={FAKE_KEY}\nTODOIST_TOKEN=\n", encoding="utf-8")
    z = load_app(home, monkeypatch)
    assert z.secrets_store.load_key() == FAKE_KEY
    env = (home / ".env").read_text(encoding="utf-8")
    assert FAKE_KEY not in env and "GEMINI_API_KEY=" in env and "TIMEZONE=Europe/Paris" in env, "la clé n'est plus en clair, le reste est intact"


def test_donnees_d_une_ancienne_version_a_cote_du_programme_sont_importees(home, tmp_path, monkeypatch):
    legacy = tmp_path / "ancien-dossier"; legacy.mkdir()
    (legacy / "memoire.db").write_bytes(b"SQLite format 3\x00" + b"\x00" * 100)
    (legacy / "token.json").write_text("{}")
    monkeypatch.setenv("ZIGGY_HOME", str(home))
    import importlib, sys
    sys.modules.pop("paths", None)
    paths = importlib.import_module("paths")
    monkeypatch.setattr(paths, "PROGRAM_DIR", legacy)
    assert set(paths.import_legacy_data()) == {"memoire.db", "token.json"}
    (legacy / "memoire.db").write_bytes(b"autre")
    assert paths.import_legacy_data() == [], "jamais d'écrasement"
    assert (legacy / "memoire.db").exists(), "copie, pas déplacement"


def test_donnees_hors_dossier_du_programme_et_hors_temporaire(app):
    import tempfile
    assert app.DATA_DIR != app.PROGRAM_DIR and not str(app.DATA_DIR).startswith(str(app.PROGRAM_DIR))
    from paths import DATA_DIR  # noqa
    d = Path(os.environ["ZIGGY_HOME"]).resolve()
    assert app.DATA_DIR == d


def test_dossier_par_defaut_windows_est_localappdata(app, tmp_path):
    import paths
    home = tmp_path / "Users" / "Jean"
    assert paths.compute_data_dir(True, {"LOCALAPPDATA": str(tmp_path / "Local")}, home) == tmp_path / "Local" / "Ziggy"
    assert paths.compute_data_dir(True, {}, home) == home / "AppData" / "Local" / "Ziggy"
    assert paths.compute_data_dir(True, {"ZIGGY_HOME": str(tmp_path / "ailleurs")}, home) == (tmp_path / "ailleurs").resolve()
    assert paths.compute_data_dir(False, {}, home) == home / ".local" / "share" / "Ziggy"
