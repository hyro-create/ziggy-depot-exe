"""Outlook, Calendrier, OneDrive, To Do et Contacts via Microsoft Graph. Les envois exigent une confirmation."""
import os, datetime
from pathlib import Path
import requests
from actions import sensitive

from paths import DATA_DIR
CACHE = DATA_DIR / "ms_token.json"
CLIENT_ID = os.getenv("MS_CLIENT_ID", "").strip()
TZ = os.getenv("TIMEZONE", "Europe/Paris")
SCOPES = ["Mail.ReadWrite", "Mail.Send", "Calendars.ReadWrite", "Files.ReadWrite",
          "Tasks.ReadWrite", "Contacts.Read", "User.Read"]
GRAPH = "https://graph.microsoft.com/v1.0"
NOT_READY = "Microsoft n'est pas connecté : il manque MS_CLIENT_ID dans .env (voir LISEZMOI.md)."
_drafts = {}   # brouillons créés par Ziggy : id -> {to, subject}
_app = {}
SAFE_PATH = None   # injecté par ziggy.py (restriction aux dossiers autorisés)


def get_token(interactive=False):
    if not CLIENT_ID:
        return None
    import msal
    if "app" not in _app:
        cache = msal.SerializableTokenCache()
        if CACHE.exists():
            cache.deserialize(CACHE.read_text())
        _app["cache"] = cache
        _app["app"] = msal.PublicClientApplication(CLIENT_ID, authority="https://login.microsoftonline.com/common", token_cache=cache)
    app = _app["app"]
    accounts = app.get_accounts()
    res = app.acquire_token_silent(SCOPES, account=accounts[0]) if accounts else None
    if not res and interactive:
        res = app.acquire_token_interactive(SCOPES)
    if _app["cache"].has_state_changed:
        CACHE.write_text(_app["cache"].serialize())
    return res.get("access_token") if res else None


def _g(method, path, **kw):
    t = get_token()
    if not t:
        raise RuntimeError(NOT_READY)
    headers = {"Authorization": f"Bearer {t}", **kw.pop("headers", {})}
    r = requests.request(method, GRAPH + path, headers=headers, timeout=30, **kw)
    if r.status_code >= 400:
        raise RuntimeError(f"{r.status_code} {r.text[:300]}")
    return r.json() if r.content and "json" in r.headers.get("content-type", "") else r


def _err(e):
    return str(e) if str(e) == NOT_READY else f"Erreur Microsoft : {e}"


# ---------------- Outlook ----------------
def outlook_search(query: str = "", max_results: int = 10) -> list:
    """Cherche dans les mails Outlook. Query vide = mails non lus de la boîte de réception. Renvoie id, expéditeur, sujet, date, extrait."""
    try:
        sel = "id,subject,from,receivedDateTime,bodyPreview"
        if query:
            d = _g("GET", "/me/messages", params={"$search": f'"{query}"', "$top": min(max_results, 20), "$select": sel})
        else:
            d = _g("GET", "/me/mailFolders/inbox/messages", params={"$filter": "isRead eq false", "$top": min(max_results, 20), "$select": sel})
        return [{"id": m["id"], "de": m["from"]["emailAddress"]["address"] if m.get("from") else "", "sujet": m["subject"],
                 "date": m["receivedDateTime"], "extrait": m["bodyPreview"][:200]} for m in d["value"]] or ["Aucun mail trouvé."]
    except Exception as e:
        return [_err(e)]


def outlook_read(message_id: str) -> str:
    """Lit un mail Outlook complet via son id."""
    try:
        m = _g("GET", f"/me/messages/{message_id}", params={"$select": "subject,from,receivedDateTime,body"},
               headers={"Prefer": 'outlook.body-content-type="text"'})
        return f"De: {m['from']['emailAddress']['address']}\nSujet: {m['subject']}\nDate: {m['receivedDateTime']}\n\n{m['body']['content'][:8000]}"
    except Exception as e:
        return _err(e)


def outlook_draft(to: str, subject: str, body: str) -> str:
    """Prépare un mail Outlook SANS l'envoyer. Montre ensuite le brouillon à l'utilisateur et attends son accord."""
    try:
        d = _g("POST", "/me/messages", json={"subject": subject, "body": {"contentType": "Text", "content": body},
                                              "toRecipients": [{"emailAddress": {"address": a.strip()}} for a in to.split(",")]})
        _drafts[d["id"]] = {"to": to, "subject": subject}
        return f"Brouillon Outlook créé (id {d['id']}). Montre-le à l'utilisateur puis appelle outlook_send_draft : il devra confirmer dans l'interface."
    except Exception as e:
        return _err(e)


@sensitive(lambda a: f"Envoyer le mail « {_drafts.get(a['draft_id'], {}).get('subject', '?')} » à {_drafts.get(a['draft_id'], {}).get('to', '?')} (Outlook)")
def outlook_send_draft(draft_id: str) -> str:
    """Envoie un brouillon Outlook créé par Ziggy. Demande une confirmation de l'utilisateur dans l'interface."""
    try:
        if draft_id not in _drafts:
            return "Brouillon inconnu : crée d'abord un brouillon avec outlook_draft."
        _g("POST", f"/me/messages/{draft_id}/send")
        _drafts.pop(draft_id, None)
        return "Mail envoyé."
    except Exception as e:
        return _err(e)


# ---------------- Calendrier Outlook ----------------
def outlook_calendar_list(days: int = 7) -> list:
    """Liste les événements du calendrier Outlook des prochains jours."""
    try:
        now = datetime.datetime.utcnow()
        d = _g("GET", "/me/calendarView", params={"startDateTime": now.isoformat(), "endDateTime": (now + datetime.timedelta(days=days)).isoformat(),
                                                   "$orderby": "start/dateTime", "$top": 50, "$select": "id,subject,start,end"},
               headers={"Prefer": f'outlook.timezone="{TZ}"'})
        return [{"id": e["id"], "titre": e["subject"], "debut": e["start"]["dateTime"], "fin": e["end"]["dateTime"]} for e in d["value"]] or ["Aucun événement."]
    except Exception as e:
        return [_err(e)]


def outlook_calendar_add(title: str, start: str, end: str, description: str = "") -> str:
    """Crée un événement Outlook. start et end au format ISO local, ex: 2026-10-25T14:00:00."""
    try:
        _g("POST", "/me/events", json={"subject": title, "body": {"contentType": "Text", "content": description},
                                       "start": {"dateTime": start, "timeZone": TZ}, "end": {"dateTime": end, "timeZone": TZ}})
        return f"Événement Outlook créé : {title} ({start})"
    except Exception as e:
        return _err(e)


# ---------------- OneDrive ----------------
def onedrive_search(query: str, max_results: int = 10) -> list:
    """Cherche des fichiers dans OneDrive."""
    try:
        q = query.replace("'", "''")
        d = _g("GET", f"/me/drive/root/search(q='{q}')", params={"$top": min(max_results, 20), "$select": "id,name,size,lastModifiedDateTime"})
        return d["value"] or ["Aucun fichier trouvé."]
    except Exception as e:
        return [_err(e)]


def onedrive_read(item_id: str) -> str:
    """Lit le contenu d'un fichier OneDrive : texte, Word, Excel, PowerPoint ou PDF."""
    try:
        from readers import extract_text
        name = _g("GET", f"/me/drive/items/{item_id}", params={"$select": "name"})["name"]
        r = _g("GET", f"/me/drive/items/{item_id}/content")
        return extract_text(name, r.content)
    except Exception as e:
        return _err(e)


@sensitive("Envoyer le fichier {local_path} sur OneDrive")
def onedrive_upload(local_path: str, remote_name: str = "") -> str:
    """Envoie un fichier local (dossier autorisé, max 4 Mo) vers OneDrive. Demande une confirmation dans l'interface."""
    try:
        p = SAFE_PATH(local_path)
        if p.stat().st_size > 4_000_000:
            return "Fichier trop gros (max 4 Mo)."
        _g("PUT", f"/me/drive/root:/{remote_name or p.name}:/content", data=p.read_bytes())
        return f"Envoyé sur OneDrive : {remote_name or p.name}"
    except Exception as e:
        return _err(e)


# ---------------- Microsoft To Do ----------------
def _default_list():
    lists = _g("GET", "/me/todo/lists")["value"]
    for l in lists:
        if l.get("wellknownListName") == "defaultList":
            return l["id"]
    return lists[0]["id"]


def todo_list() -> list:
    """Liste les tâches non terminées de Microsoft To Do."""
    try:
        d = _g("GET", f"/me/todo/lists/{_default_list()}/tasks", params={"$filter": "status ne 'completed'", "$top": 50})
        return [{"id": t["id"], "titre": t["title"]} for t in d["value"]] or ["Aucune tâche."]
    except Exception as e:
        return [_err(e)]


def todo_add(title: str) -> str:
    """Ajoute une tâche dans Microsoft To Do."""
    try:
        _g("POST", f"/me/todo/lists/{_default_list()}/tasks", json={"title": title})
        return f"Tâche To Do ajoutée : {title}"
    except Exception as e:
        return _err(e)


def todo_complete(task_id: str) -> str:
    """Termine une tâche Microsoft To Do via son id."""
    try:
        _g("PATCH", f"/me/todo/lists/{_default_list()}/tasks/{task_id}", json={"status": "completed"})
        return "Tâche terminée."
    except Exception as e:
        return _err(e)


# ---------------- Contacts ----------------
def contacts_search(name: str) -> list:
    """Cherche un contact Outlook par nom (renvoie nom, e-mails, téléphones)."""
    try:
        d = _g("GET", "/me/contacts", params={"$search": f'"{name}"', "$top": 10, "$select": "displayName,emailAddresses,mobilePhone,businessPhones"})
        return [{"nom": c["displayName"], "emails": [e["address"] for e in c["emailAddresses"]],
                 "tel": c.get("mobilePhone") or c.get("businessPhones")} for c in d["value"]] or ["Aucun contact."]
    except Exception as e:
        return [_err(e)]


MS_TOOLS = [outlook_search, outlook_read, outlook_draft, outlook_send_draft, outlook_calendar_list,
            outlook_calendar_add, onedrive_search, onedrive_read, onedrive_upload,
            todo_list, todo_add, todo_complete, contacts_search]
