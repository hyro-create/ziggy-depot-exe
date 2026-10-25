"""Rappels persistants : enregistrés dans la base, ils survivent à la fermeture de Ziggy."""
import collections, datetime, threading, time
import database
from logsetup import get_logger

log = get_logger("rappels")
_due = collections.deque()
_handlers = []
_started = False


def on_fire(handler) -> None:
    _handlers.append(handler)


def add(text: str, minutes: float = 0, at: str = ""):
    text = (text or "").strip()
    if not text or len(text) > 300:
        return False, "Le texte du rappel doit faire entre 1 et 300 caractères.", None
    now = time.time()
    if at:
        try:
            due = datetime.datetime.fromisoformat(at).timestamp()
        except ValueError:
            return False, "Date invalide : utilise le format 2026-10-25T14:30:00.", None
    elif minutes and 0 < minutes <= 525_600:
        due = now + minutes * 60
    else:
        return False, "Indique soit 'minutes' (entre 0 et 525600), soit 'at' (date ISO).", None
    if due < now - 1 or due > now + 366 * 86400:
        return False, "L'échéance doit être dans le futur (moins d'un an).", None
    with database.connect() as c:
        rid = c.execute("INSERT INTO reminders(text, due_ts, created) VALUES(?,?,?)",
                        (text, due, datetime.datetime.now().isoformat(timespec="seconds"))).lastrowid
    when = datetime.datetime.fromtimestamp(due).strftime("%d/%m/%Y à %H:%M")
    return True, f"Rappel n°{rid} programmé pour le {when} : {text}", rid


def list_active() -> list:
    with database.connect() as c:
        rows = c.execute("SELECT id, text, due_ts FROM reminders WHERE fired=0 ORDER BY due_ts").fetchall()
    return [{"id": r["id"], "texte": r["text"], "quand": datetime.datetime.fromtimestamp(r["due_ts"]).isoformat(timespec="minutes")} for r in rows]


def cancel(rid: int) -> bool:
    with database.connect() as c:
        return c.execute("DELETE FROM reminders WHERE id=? AND fired=0", (rid,)).rowcount > 0


def fire_due() -> int:
    now = time.time()
    with database.connect() as c:
        rows = c.execute("SELECT id, text, due_ts FROM reminders WHERE fired=0 AND due_ts<=?", (now,)).fetchall()
        for r in rows:
            c.execute("UPDATE reminders SET fired=1 WHERE id=?", (r["id"],))
    for r in rows:
        item = {"id": r["id"], "text": r["text"], "missed": now - r["due_ts"] > 120}
        _due.append(item)
        for h in list(_handlers):
            try:
                h(item)
            except Exception as e:
                log.warning("Gestionnaire de rappel en échec : %s", type(e).__name__)
    return len(rows)


def pop_due() -> list:
    out = []
    while _due:
        out.append(_due.popleft())
    return out


def start_scheduler(interval: float = 3.0) -> None:
    global _started
    if _started:
        return
    _started = True

    def loop():
        while True:
            try:
                fire_due()
            except Exception as e:
                log.warning("Planificateur de rappels : %s", type(e).__name__)
            time.sleep(interval)
    threading.Thread(target=loop, daemon=True, name="rappels").start()
