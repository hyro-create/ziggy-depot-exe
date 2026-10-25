"""Gmail, Agenda et Drive pour Ziggy (OAuth Google). Les envois de mails exigent une confirmation."""
import os, base64, datetime
from email.message import EmailMessage
from pathlib import Path
from actions import sensitive

from paths import DATA_DIR
CREDS, TOKEN = DATA_DIR / "credentials.json", DATA_DIR / "token.json"
TZ = os.getenv("TIMEZONE", "Europe/Paris")
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/drive.readonly",
]
NOT_READY = "Google n'est pas connecté : il manque credentials.json (voir LISEZMOI.md)."
_drafts = {}          # brouillons créés par Ziggy : id -> {to, subject} (seuls ceux-là peuvent être envoyés)


def get_creds():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from google_auth_oauthlib.flow import InstalledAppFlow
    creds = Credentials.from_authorized_user_file(TOKEN, SCOPES) if TOKEN.exists() else None
    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    else:
        if not CREDS.exists():
            return None
        creds = InstalledAppFlow.from_client_secrets_file(str(CREDS), SCOPES).run_local_server(port=0)
    TOKEN.write_text(creds.to_json())
    return creds


def _svc(name, version):
    from googleapiclient.discovery import build
    c = get_creds()
    return build(name, version, credentials=c) if c else None


def _body(payload) -> str:
    if payload.get("mimeType") == "text/plain" and payload.get("body", {}).get("data"):
        return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", "replace")
    for part in payload.get("parts", []) or []:
        t = _body(part)
        if t:
            return t
    return ""


# ---------------- Gmail ----------------
def gmail_search(query: str = "is:unread", max_results: int = 10) -> list:
    """Cherche des mails avec la syntaxe Gmail (ex: 'is:unread', 'from:paul', 'subject:facture newer_than:7d'). Renvoie id, expéditeur, sujet, date, extrait."""
    try:
        s = _svc("gmail", "v1")
        if not s: return [NOT_READY]
        ids = s.users().messages().list(userId="me", q=query, maxResults=min(max_results, 20)).execute().get("messages", [])
        out = []
        for m in ids:
            d = s.users().messages().get(userId="me", id=m["id"], format="metadata",
                                         metadataHeaders=["From", "Subject", "Date"]).execute()
            h = {x["name"]: x["value"] for x in d["payload"]["headers"]}
            out.append({"id": m["id"], "de": h.get("From"), "sujet": h.get("Subject"), "date": h.get("Date"), "extrait": d.get("snippet")})
        return out or ["Aucun mail trouvé."]
    except Exception as e:
        return [f"Erreur Gmail : {e}"]


def gmail_read(message_id: str) -> str:
    """Lit le contenu complet d'un mail via son id."""
    try:
        s = _svc("gmail", "v1")
        if not s: return NOT_READY
        d = s.users().messages().get(userId="me", id=message_id, format="full").execute()
        h = {x["name"]: x["value"] for x in d["payload"]["headers"]}
        return f"De: {h.get('From')}\nSujet: {h.get('Subject')}\nDate: {h.get('Date')}\n\n{_body(d['payload'])[:8000]}"
    except Exception as e:
        return f"Erreur Gmail : {e}"


def gmail_draft(to: str, subject: str, body: str) -> str:
    """Prépare un mail SANS l'envoyer. Montre ensuite le brouillon à l'utilisateur et attends son accord."""
    try:
        s = _svc("gmail", "v1")
        if not s: return NOT_READY
        msg = EmailMessage(); msg["To"], msg["Subject"] = to, subject; msg.set_content(body)
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        d = s.users().drafts().create(userId="me", body={"message": {"raw": raw}}).execute()
        _drafts[d["id"]] = {"to": to, "subject": subject}
        return f"Brouillon créé (id {d['id']}). Montre-le à l'utilisateur puis appelle gmail_send_draft : l'utilisateur devra confirmer dans l'interface."
    except Exception as e:
        return f"Erreur Gmail : {e}"


@sensitive(lambda a: f"Envoyer le mail « {_drafts.get(a['draft_id'], {}).get('subject', '?')} » à {_drafts.get(a['draft_id'], {}).get('to', '?')} (Gmail)")
def gmail_send_draft(draft_id: str) -> str:
    """Envoie un brouillon Gmail créé par Ziggy. Demande une confirmation de l'utilisateur dans l'interface."""
    try:
        if draft_id not in _drafts:
            return "Brouillon inconnu : crée d'abord un brouillon avec gmail_draft."
        s = _svc("gmail", "v1")
        if not s: return NOT_READY
        s.users().drafts().send(userId="me", body={"id": draft_id}).execute()
        _drafts.pop(draft_id, None)
        return "Mail envoyé."
    except Exception as e:
        return f"Erreur Gmail : {e}"


# ---------------- Agenda ----------------
def calendar_list(days: int = 7) -> list:
    """Liste les événements des prochains jours (défaut 7)."""
    try:
        s = _svc("calendar", "v3")
        if not s: return [NOT_READY]
        now = datetime.datetime.utcnow()
        ev = s.events().list(calendarId="primary", timeMin=now.isoformat() + "Z",
                             timeMax=(now + datetime.timedelta(days=days)).isoformat() + "Z",
                             singleEvents=True, orderBy="startTime", maxResults=50).execute().get("items", [])
        return [{"id": e["id"], "titre": e.get("summary"), "debut": e["start"].get("dateTime", e["start"].get("date")),
                 "fin": e["end"].get("dateTime", e["end"].get("date"))} for e in ev] or ["Aucun événement."]
    except Exception as e:
        return [f"Erreur Agenda : {e}"]


def calendar_add(title: str, start: str, end: str, description: str = "") -> str:
    """Crée un événement. start et end au format ISO local, ex: 2026-10-25T14:00:00."""
    try:
        s = _svc("calendar", "v3")
        if not s: return NOT_READY
        body = {"summary": title, "description": description,
                "start": {"dateTime": start, "timeZone": TZ}, "end": {"dateTime": end, "timeZone": TZ}}
        e = s.events().insert(calendarId="primary", body=body).execute()
        return f"Événement créé : {e.get('summary')} ({start})"
    except Exception as e:
        return f"Erreur Agenda : {e}"


@sensitive("Supprimer l'événement Google Agenda {event_id}")
def calendar_delete(event_id: str) -> str:
    """Supprime un événement via son id. Demande une confirmation de l'utilisateur dans l'interface."""
    try:
        s = _svc("calendar", "v3")
        if not s: return NOT_READY
        s.events().delete(calendarId="primary", eventId=event_id).execute()
        return "Événement supprimé."
    except Exception as e:
        return f"Erreur Agenda : {e}"


# ---------------- Drive ----------------
def drive_search(query: str, max_results: int = 10) -> list:
    """Cherche des fichiers dans Google Drive par mot-clé dans le nom ou le contenu."""
    try:
        s = _svc("drive", "v3")
        if not s: return [NOT_READY]
        q = query.replace("'", "\\'")
        r = s.files().list(q=f"fullText contains '{q}' and trashed=false", pageSize=min(max_results, 20),
                           fields="files(id,name,mimeType,modifiedTime)").execute()
        return r.get("files", []) or ["Aucun fichier trouvé."]
    except Exception as e:
        return [f"Erreur Drive : {e}"]


def drive_read(file_id: str) -> str:
    """Lit le texte d'un fichier Drive : Docs, Sheets, Word, Excel, PowerPoint, PDF, fichiers texte."""
    try:
        s = _svc("drive", "v3")
        if not s: return NOT_READY
        meta = s.files().get(fileId=file_id, fields="mimeType,name").execute()
        mt = meta["mimeType"]
        if mt.startswith("application/vnd.google-apps."):
            export = "text/csv" if "spreadsheet" in mt else "text/plain"
            data = s.files().export(fileId=file_id, mimeType=export).execute()
        else:
            from readers import extract_text
            data = s.files().get_media(fileId=file_id).execute()
            return extract_text(meta["name"], data)
        return (data.decode("utf-8", "replace") if isinstance(data, bytes) else str(data))[:20000]
    except Exception as e:
        return f"Erreur Drive : {e}"


GOOGLE_TOOLS = [gmail_search, gmail_read, gmail_draft, gmail_send_draft,
                calendar_list, calendar_add, calendar_delete, drive_search, drive_read]
