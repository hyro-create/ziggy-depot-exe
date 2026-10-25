"""Mémoire SQLite de Ziggy : connexion sûre, migrations versionnées, sauvegardes.

Principes :
- La version du schéma est stockée dans la base (PRAGMA user_version).
- Avant toute migration d'une base qui contient des données, une sauvegarde est créée dans backups/.
- La migration est une transaction : en cas d'erreur, rien n'est modifié.
- Une base créée par une version PLUS RÉCENTE de Ziggy n'est jamais modifiée (pas de retour en arrière destructeur).
- Aucune fonction ne réinitialise la base automatiquement.
"""
import contextlib, datetime, sqlite3
from paths import DATA_DIR, BACKUP_DIR
from logsetup import get_logger

log = get_logger("database")
DB_PATH = DATA_DIR / "memoire.db"
SCHEMA_VERSION = 2
KEEP_BACKUPS = 15


class DatabaseError(Exception):
    pass


@contextlib.contextmanager
def connect():
    """Connexion qui valide (commit) puis se FERME toujours (important sous Windows : pas de fichier verrouillé)."""
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


MIGRATIONS = {
    1: [  # version d'origine (Ziggy avant l'installateur) : conversations, souvenirs, tâches
        "CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY, role TEXT, content TEXT, ts TEXT)",
        "CREATE TABLE IF NOT EXISTS facts(id INTEGER PRIMARY KEY, fact TEXT UNIQUE, ts TEXT)",
        "CREATE TABLE IF NOT EXISTS tasks(id INTEGER PRIMARY KEY, title TEXT, due TEXT, done INTEGER DEFAULT 0, ts TEXT)",
    ],
    2: [  # rappels persistants (survivent à la fermeture de Ziggy)
        "CREATE TABLE IF NOT EXISTS reminders(id INTEGER PRIMARY KEY, text TEXT NOT NULL, due_ts REAL NOT NULL, "
        "fired INTEGER NOT NULL DEFAULT 0, created TEXT)",
        "CREATE INDEX IF NOT EXISTS idx_reminders_due ON reminders(fired, due_ts)",
    ],
}


def backup_db(label: str = "manuelle"):
    """Copie cohérente de la base (API de sauvegarde SQLite). Renvoie le chemin, ou None s'il n'y a pas de base."""
    if not DB_PATH.exists():
        return None
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    dest = BACKUP_DIR / f"memoire-{label}-{stamp}.db"
    src, dst = sqlite3.connect(DB_PATH), sqlite3.connect(dest)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    for old in sorted(BACKUP_DIR.glob("memoire-*.db"), key=lambda p: p.stat().st_mtime)[:-KEEP_BACKUPS]:
        try:
            old.unlink()
        except OSError:
            pass
    return dest


def _user_version() -> int:
    with connect() as c:
        return c.execute("PRAGMA user_version").fetchone()[0]


def _has_user_data() -> bool:
    with connect() as c:
        return c.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchone()[0] > 0


def init() -> dict:
    """Crée ou met à jour la base. À appeler au démarrage. Renvoie un résumé."""
    existed = DB_PATH.exists() and DB_PATH.stat().st_size > 0
    current = _user_version()
    if current > SCHEMA_VERSION:
        raise DatabaseError(f"La mémoire a été créée par une version plus récente de Ziggy (schéma {current}, "
                            f"cette version gère jusqu'à {SCHEMA_VERSION}). Installe la dernière version de Ziggy ; "
                            f"ta mémoire n'a pas été modifiée.")
    if current == SCHEMA_VERSION:
        return {"migrated": False, "from": current, "to": current, "backup": None}
    backup = None
    if existed and _has_user_data():
        backup = backup_db(f"avant-migration-v{current}-vers-v{SCHEMA_VERSION}")
        log.info("Sauvegarde avant migration : %s", backup.name if backup else "aucune")
    conn = sqlite3.connect(DB_PATH, timeout=15, isolation_level=None)       # transactions gérées à la main
    try:
        conn.execute("BEGIN IMMEDIATE")
        for v in range(current + 1, SCHEMA_VERSION + 1):
            for stmt in MIGRATIONS[v]:
                conn.execute(stmt)
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        conn.execute("COMMIT")
    except Exception as e:
        try:
            conn.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise DatabaseError(f"La mise à jour de la mémoire a échoué ({type(e).__name__}) ; rien n'a été modifié."
                            + (f" Sauvegarde : {backup}" if backup else ""))
    finally:
        conn.close()
    log.info("Mémoire migrée : schéma %s -> %s", current, SCHEMA_VERSION)
    return {"migrated": True, "from": current, "to": SCHEMA_VERSION, "backup": str(backup) if backup else None}


# ---- Opérations de mémoire utilisées par l'interface ----
def history(limit: int = 60, offset: int = 0) -> list:
    with connect() as c:
        rows = c.execute("SELECT id, role, content, ts FROM messages ORDER BY id DESC LIMIT ? OFFSET ?", (limit, offset)).fetchall()
    return [dict(r) for r in rows][::-1]


def stats() -> dict:
    with connect() as c:
        g = lambda q: c.execute(q).fetchone()[0]
        return {"messages": g("SELECT count(*) FROM messages"), "souvenirs": g("SELECT count(*) FROM facts"),
                "taches": g("SELECT count(*) FROM tasks"), "rappels": g("SELECT count(*) FROM reminders WHERE fired=0")}


def clear_history():
    """Efface UNIQUEMENT les conversations (les souvenirs, tâches et rappels sont conservés). Sauvegarde automatique avant."""
    b = backup_db("avant-effacement-historique")
    with connect() as c:
        n = c.execute("DELETE FROM messages").rowcount
    return {"deleted": n, "backup": str(b) if b else None}


def wipe_memory():
    """Efface conversations ET souvenirs. Les tâches, rappels, paramètres et la clé API sont conservés. Sauvegarde avant."""
    b = backup_db("avant-suppression-memoire")
    with connect() as c:
        n1 = c.execute("DELETE FROM messages").rowcount
        n2 = c.execute("DELETE FROM facts").rowcount
    return {"messages": n1, "souvenirs": n2, "backup": str(b) if b else None}
