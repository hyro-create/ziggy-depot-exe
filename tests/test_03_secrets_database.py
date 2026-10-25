"""Stockage de la clé, base SQLite, migrations, sauvegardes."""
import os, sqlite3, pytest
from conftest import FAKE_KEY, FAKE_KEY2


# ---------------- clé API ----------------
def test_cle_enregistrement_lecture_suppression(app):
    ss = app.secrets_store
    assert ss.load_key() is None and not ss.has_key()
    ss.save_key(FAKE_KEY)
    assert ss.load_key() == FAKE_KEY and ss.has_key() and ss.last4() == FAKE_KEY[-4:]
    ss.save_key(FAKE_KEY2)                                         # modification
    assert ss.load_key() == FAKE_KEY2
    assert ss.delete_key() is True and ss.load_key() is None       # suppression


def test_la_cle_n_est_dans_aucun_autre_fichier(app, api):
    api.post("/api/gemini/key", {"key": FAKE_KEY})
    app.remember("je m'appelle Test")
    app.save_messages(("user", "bonjour"), ("model", "salut"))
    key_file = app.secrets_store.FILE
    for f in app.DATA_DIR.rglob("*"):
        if f.is_file() and f != key_file:
            assert FAKE_KEY.encode() not in f.read_bytes(), f"clé en clair dans {f.name}"
    assert FAKE_KEY.encode() not in key_file.read_bytes(), "la clé ne doit pas être lisible telle quelle dans son fichier"


@pytest.mark.skipif(os.name == "nt", reason="permissions POSIX")
def test_fichier_de_cle_a_acces_restreint_posix(app):
    app.secrets_store.save_key(FAKE_KEY)
    assert oct(app.secrets_store.FILE.stat().st_mode & 0o777) == "0o600"


def test_fichier_de_cle_illisible_donne_une_erreur_claire(app):
    app.secrets_store.FILE.write_text("n'importe quoi", encoding="utf-8")
    with pytest.raises(app.secrets_store.SecretError):
        app.secrets_store.load_key()
    assert app.gemini.resolve_key() == (None, None)                # l'application continue sans planter


@pytest.mark.windows_only
@pytest.mark.skipif(os.name != "nt", reason="DPAPI : Windows uniquement (à exécuter sur Windows 11)")
def test_dpapi_chiffre_vraiment(app):
    import base64, json
    app.secrets_store.save_key(FAKE_KEY)
    d = json.loads(app.secrets_store.FILE.read_text())
    assert d["backend"] == "dpapi" and FAKE_KEY.encode() not in base64.b64decode(d["data"])
    assert app.secrets_store.load_key() == FAKE_KEY


# ---------------- base de données ----------------
def test_creation_puis_reouverture_sans_migration(app, restart):
    assert app.database.DB_PATH.exists()
    app.remember("souvenir A")
    z2 = restart()
    assert z2.database.init()["migrated"] is False
    with z2.database.connect() as c:
        assert c.execute("SELECT fact FROM facts").fetchone()[0] == "souvenir A"


def _old_db(path, user_version):
    c = sqlite3.connect(path)
    c.executescript("""CREATE TABLE messages(id INTEGER PRIMARY KEY, role TEXT, content TEXT, ts TEXT);
        CREATE TABLE facts(id INTEGER PRIMARY KEY, fact TEXT UNIQUE, ts TEXT);
        CREATE TABLE tasks(id INTEGER PRIMARY KEY, title TEXT, due TEXT, done INTEGER DEFAULT 0, ts TEXT);
        INSERT INTO messages(role,content,ts) VALUES('user','ancienne question','t'),('model','ancienne réponse','t');
        INSERT INTO facts(fact,ts) VALUES('aime le café','t'); INSERT INTO tasks(title,ts) VALUES('ancienne tâche','t');""")
    c.execute(f"PRAGMA user_version={user_version}"); c.commit(); c.close()


@pytest.mark.parametrize("version", [0, 1])
def test_mise_a_jour_d_une_ancienne_base_garde_les_donnees_et_sauvegarde(home, monkeypatch, version):
    from conftest import load_app
    home.mkdir(parents=True)
    _old_db(home / "memoire.db", version)                          # base créée par la version précédente (sans l'installateur)
    z = load_app(home, monkeypatch)                                # = première ouverture de la nouvelle version
    with z.database.connect() as c:
        assert c.execute("PRAGMA user_version").fetchone()[0] == z.database.SCHEMA_VERSION
        assert c.execute("SELECT count(*) FROM messages").fetchone()[0] == 2
        assert c.execute("SELECT fact FROM facts").fetchone()[0] == "aime le café"
        assert c.execute("SELECT title FROM tasks").fetchone()[0] == "ancienne tâche"
        c.execute("SELECT count(*) FROM reminders")                # la nouvelle table existe
    backups = list(z.BACKUP_DIR.glob("memoire-avant-migration-*.db")) if hasattr(z, "BACKUP_DIR") else list((home / "backups").glob("memoire-avant-migration-*.db"))
    assert len(backups) == 1, "une sauvegarde doit précéder la migration"
    b = sqlite3.connect(backups[0]); assert b.execute("SELECT count(*) FROM messages").fetchone()[0] == 2; b.close()


def test_une_base_plus_recente_n_est_jamais_modifiee(home, monkeypatch):
    from conftest import load_app
    home.mkdir(parents=True)
    _old_db(home / "memoire.db", 99)
    before = (home / "memoire.db").read_bytes()
    z = load_app.__wrapped__ if False else None
    import importlib, sys, logging
    monkeypatch.setenv("ZIGGY_HOME", str(home))
    for m in list(sys.modules):
        if m in ("database", "paths", "logsetup"): sys.modules.pop(m)
    db = importlib.import_module("database")
    with pytest.raises(db.DatabaseError, match="plus récente"):
        db.init()
    assert (home / "memoire.db").read_bytes() == before


def test_migration_en_echec_ne_modifie_rien(home, monkeypatch):
    import importlib, sys
    home.mkdir(parents=True)
    _old_db(home / "memoire.db", 1)
    monkeypatch.setenv("ZIGGY_HOME", str(home))
    for m in ("database", "paths", "logsetup"): sys.modules.pop(m, None)
    db = importlib.import_module("database")
    monkeypatch.setitem(db.MIGRATIONS, 2, ["CREATE TABLE ok_avant(id INTEGER)", "INSTRUCTION SQL INVALIDE"])
    with pytest.raises(db.DatabaseError, match="rien n'a été modifié"):
        db.init()
    c = sqlite3.connect(home / "memoire.db")
    assert c.execute("PRAGMA user_version").fetchone()[0] == 1
    assert c.execute("SELECT count(*) FROM sqlite_master WHERE name='ok_avant'").fetchone()[0] == 0
    assert c.execute("SELECT count(*) FROM messages").fetchone()[0] == 2
    c.close()
    assert list((home / "backups").glob("memoire-avant-migration-*.db")), "la sauvegarde reste disponible"


def test_effacer_historique_garde_souvenirs_et_sauvegarde(app):
    app.remember("souvenir"); app.add_task("tâche")
    app.save_messages(("user", "a"), ("model", "b"))
    r = app.database.clear_history()
    assert r["deleted"] == 2 and r["backup"]
    st = app.database.stats()
    assert st["messages"] == 0 and st["souvenirs"] == 1 and st["taches"] == 1


def test_supprimer_toute_la_memoire_garde_taches_et_reglages(app):
    app.remember("souvenir"); app.add_task("tâche"); app.settings.update({"voice": {"rate": 1.4}})
    app.save_messages(("user", "a"), ("model", "b"))
    r = app.database.wipe_memory()
    assert r["messages"] == 2 and r["souvenirs"] == 1 and r["backup"]
    st = app.database.stats()
    assert st["messages"] == 0 and st["souvenirs"] == 0 and st["taches"] == 1
    assert app.settings.load()["voice"]["rate"] == 1.4


def test_les_connexions_sont_fermees(app):
    """Sous Windows, une connexion non fermée verrouille memoire.db (mise à jour/désinstallation impossibles)."""
    for _ in range(50):
        app.remember(f"x{_}")
    os.rename(app.database.DB_PATH, str(app.database.DB_PATH) + ".moved")      # échouerait sous Windows si un verrou subsistait
    os.rename(str(app.database.DB_PATH) + ".moved", app.database.DB_PATH)


def test_sauvegardes_limitees(app):
    for _ in range(app.database.KEEP_BACKUPS + 5):
        app.database.backup_db("test")
    assert len(list(app.database.BACKUP_DIR.glob("memoire-*.db"))) == app.database.KEEP_BACKUPS
