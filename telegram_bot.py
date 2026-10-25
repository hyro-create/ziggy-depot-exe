"""Telegram : parle à Ziggy depuis ton téléphone, et Ziggy peut t'écrire."""
import os, threading, time
import requests

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
ALLOWED = os.getenv("TELEGRAM_ALLOWED_ID", "").strip()
API = f"https://api.telegram.org/bot{TOKEN}"


def _send(chat_id, text):
    for i in range(0, len(text) or 1, 4000):
        requests.post(f"{API}/sendMessage", json={"chat_id": chat_id, "text": text[i:i + 4000]}, timeout=20)


def telegram_send(text: str) -> str:
    """Envoie un message Telegram à l'utilisateur (sur son téléphone)."""
    if not ALLOWED:
        return "TELEGRAM_ALLOWED_ID manquant dans .env."
    try:
        _send(ALLOWED, text); return "Message Telegram envoyé."
    except Exception as e:
        return f"Erreur Telegram : {e}"


def start(handle):
    """Lance l'écoute en arrière-plan. handle(texte) -> réponse."""
    def loop():
        offset = 0
        while True:
            try:
                r = requests.get(f"{API}/getUpdates", params={"timeout": 30, "offset": offset}, timeout=40).json()
                for u in r.get("result", []):
                    offset = u["update_id"] + 1
                    m = u.get("message") or {}
                    text, uid = m.get("text"), str(m.get("from", {}).get("id", ""))
                    if not text:
                        continue
                    if not ALLOWED or uid != ALLOWED:
                        if not ALLOWED:
                            _send(m["chat"]["id"], f"Ziggy ici. Ton identifiant Telegram est {uid}. Mets TELEGRAM_ALLOWED_ID={uid} dans .env puis relance Ziggy.")
                        continue   # on ignore tous les inconnus
                    requests.post(f"{API}/sendChatAction", json={"chat_id": uid, "action": "typing"}, timeout=10)
                    _send(uid, handle(text))
            except Exception:
                time.sleep(5)
    threading.Thread(target=loop, daemon=True).start()
