"""Todoist, Notion, Spotify."""
import os
import requests

# ================= Todoist (API v1) =================
TODOIST = os.getenv("TODOIST_TOKEN", "").strip()
_T = "https://api.todoist.com/api/v1"


def _td(method, path, **kw):
    r = requests.request(method, _T + path, headers={"Authorization": f"Bearer {TODOIST}"}, timeout=20, **kw)
    if r.status_code >= 400:
        raise RuntimeError(f"{r.status_code} {r.text[:200]}")
    return r.json() if r.content else {}


def todoist_list(filter: str = "") -> list:
    """Liste les tâches Todoist actives. 'filter' = filtre Todoist optionnel (ex: 'today', 'overdue', '@perso')."""
    try:
        d = _td("GET", "/tasks/filter", params={"query": filter}) if filter else _td("GET", "/tasks")
        items = d.get("results", d) if isinstance(d, dict) else d
        return [{"id": t["id"], "titre": t["content"], "echeance": (t.get("due") or {}).get("string"), "priorite": t.get("priority")}
                for t in items][:50] or ["Aucune tâche."]
    except Exception as e:
        return [f"Erreur Todoist : {e}"]


def todoist_add(content: str, due: str = "", priority: int = 1) -> str:
    """Ajoute une tâche Todoist. due = langage naturel (ex: 'demain 14h'). priority de 1 (normal) à 4 (urgent)."""
    try:
        body = {"content": content, "priority": priority}
        if due:
            body["due_string"] = due
            body["due_lang"] = "fr"
        _td("POST", "/tasks", json=body)
        return f"Tâche Todoist ajoutée : {content}"
    except Exception as e:
        return f"Erreur Todoist : {e}"


def todoist_complete(task_id: str) -> str:
    """Termine une tâche Todoist via son id."""
    try:
        _td("POST", f"/tasks/{task_id}/close")
        return "Tâche terminée."
    except Exception as e:
        return f"Erreur Todoist : {e}"


TODOIST_TOOLS = [todoist_list, todoist_add, todoist_complete]


# ================= Notion =================
NOTION = os.getenv("NOTION_TOKEN", "").strip()
NOTION_PARENT = os.getenv("NOTION_PARENT_PAGE_ID", "").strip()
_N = "https://api.notion.com/v1"


def _nt(method, path, **kw):
    r = requests.request(method, _N + path, timeout=30, **kw,
                         headers={"Authorization": f"Bearer {NOTION}", "Notion-Version": "2025-09-03", "Content-Type": "application/json"})
    if r.status_code >= 400:
        raise RuntimeError(f"{r.status_code} {r.text[:300]}")
    return r.json()


def _title(obj) -> str:
    props = obj.get("properties", {})
    for p in props.values():
        if p.get("type") == "title":
            return "".join(t["plain_text"] for t in p["title"])
    t = obj.get("title")
    return "".join(x["plain_text"] for x in t) if isinstance(t, list) else "(sans titre)"


def notion_search(query: str = "") -> list:
    """Cherche des pages Notion par titre (uniquement celles partagées avec l'intégration Ziggy)."""
    try:
        d = _nt("POST", "/search", json={"query": query, "page_size": 10})
        return [{"id": r["id"], "type": r["object"], "titre": _title(r), "url": r.get("url")} for r in d["results"]] or ["Rien trouvé."]
    except Exception as e:
        return [f"Erreur Notion : {e}"]


def notion_read_page(page_id: str) -> str:
    """Lit le contenu texte d'une page Notion."""
    try:
        d = _nt("GET", f"/blocks/{page_id}/children?page_size=100")
        lines = []
        for b in d["results"]:
            rich = b.get(b["type"], {}).get("rich_text", [])
            txt = "".join(t["plain_text"] for t in rich)
            if txt:
                lines.append(txt)
        return "\n".join(lines)[:15000] or "(page vide ou sans texte)"
    except Exception as e:
        return f"Erreur Notion : {e}"


def _blocks(text: str):
    return [{"object": "block", "type": "paragraph",
             "paragraph": {"rich_text": [{"type": "text", "text": {"content": line[:1900]}}]}}
            for line in text.split("\n") if line.strip()][:90]


def notion_create_page(title: str, content: str = "", parent_page_id: str = "") -> str:
    """Crée une page Notion (sous la page parent configurée, ou parent_page_id)."""
    try:
        parent = parent_page_id or NOTION_PARENT
        if not parent:
            return "Il manque NOTION_PARENT_PAGE_ID dans .env (la page sous laquelle créer les pages)."
        d = _nt("POST", "/pages", json={"parent": {"page_id": parent},
                                        "properties": {"title": {"title": [{"text": {"content": title}}]}},
                                        "children": _blocks(content)})
        return f"Page créée : {d.get('url')}"
    except Exception as e:
        return f"Erreur Notion : {e}"


def notion_append(page_id: str, text: str) -> str:
    """Ajoute du texte à la fin d'une page Notion."""
    try:
        _nt("PATCH", f"/blocks/{page_id}/children", json={"children": _blocks(text)})
        return "Ajouté à la page."
    except Exception as e:
        return f"Erreur Notion : {e}"


NOTION_TOOLS = [notion_search, notion_read_page, notion_create_page, notion_append]


# ================= Spotify =================
SPOTIFY_ID = os.getenv("SPOTIFY_CLIENT_ID", "").strip()
_sp = {}
NO_DEVICE = "Aucun appareil Spotify actif : ouvre Spotify sur ton PC ou ton téléphone puis réessaie."


def spotify_client():
    if "c" not in _sp:
        import spotipy
        from spotipy.oauth2 import SpotifyPKCE
        from spotipy.cache_handler import CacheFileHandler
        from paths import DATA_DIR
        auth = SpotifyPKCE(client_id=SPOTIFY_ID, redirect_uri="http://127.0.0.1:8888/callback",
                           scope="user-read-playback-state user-modify-playback-state user-read-currently-playing",
                           cache_handler=CacheFileHandler(cache_path=str(DATA_DIR / "spotify_token.json")))
        _sp["c"] = spotipy.Spotify(auth_manager=auth)
    return _sp["c"]


def _sperr(e):
    s = str(e)
    return NO_DEVICE if "NO_ACTIVE_DEVICE" in s or "No active device" in s else f"Erreur Spotify : {s[:200]}"


def spotify_play(query: str = "", kind: str = "track") -> str:
    """Lance une musique. query vide = reprendre la lecture. kind = track, artist, album ou playlist."""
    try:
        sp = spotify_client()
        if not query:
            sp.start_playback(); return "Lecture reprise."
        r = sp.search(q=query, type=kind, limit=5)[kind + "s"]["items"]
        r = [x for x in r if x]
        if not r:
            return "Rien trouvé."
        item = r[0]
        if kind == "track":
            sp.start_playback(uris=[item["uri"]])
            return f"Lecture : {item['name']} — {item['artists'][0]['name']}"
        sp.start_playback(context_uri=item["uri"])
        return f"Lecture : {item['name']}"
    except Exception as e:
        return _sperr(e)


def spotify_pause() -> str:
    """Met la musique en pause."""
    try:
        spotify_client().pause_playback(); return "Pause."
    except Exception as e:
        return _sperr(e)


def spotify_next() -> str:
    """Passe au morceau suivant."""
    try:
        spotify_client().next_track(); return "Morceau suivant."
    except Exception as e:
        return _sperr(e)


def spotify_previous() -> str:
    """Revient au morceau précédent."""
    try:
        spotify_client().previous_track(); return "Morceau précédent."
    except Exception as e:
        return _sperr(e)


def spotify_volume(percent: int) -> str:
    """Règle le volume Spotify de 0 à 100."""
    try:
        spotify_client().volume(max(0, min(100, percent))); return f"Volume à {percent}%."
    except Exception as e:
        return _sperr(e)


def spotify_now_playing() -> str:
    """Indique le morceau en cours de lecture."""
    try:
        c = spotify_client().current_user_playing_track()
        if not c or not c.get("item"):
            return "Rien en cours de lecture."
        i = c["item"]
        return f"{i['name']} — {i['artists'][0]['name']} ({'en lecture' if c['is_playing'] else 'en pause'})"
    except Exception as e:
        return _sperr(e)


def spotify_queue(query: str) -> str:
    """Ajoute un morceau à la file d'attente Spotify."""
    try:
        sp = spotify_client()
        r = sp.search(q=query, type="track", limit=1)["tracks"]["items"]
        if not r:
            return "Rien trouvé."
        sp.add_to_queue(r[0]["uri"]); return f"Ajouté à la file : {r[0]['name']} — {r[0]['artists'][0]['name']}"
    except Exception as e:
        return _sperr(e)


SPOTIFY_TOOLS = [spotify_play, spotify_pause, spotify_next, spotify_previous, spotify_volume, spotify_now_playing, spotify_queue]
