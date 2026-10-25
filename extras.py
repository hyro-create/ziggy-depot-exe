"""Outils supplémentaires : météo (Open-Meteo), pages web, rappels persistants, presse-papiers."""
import ipaddress, re, socket
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse
import requests
import reminders as rem


def weather(city: str) -> str:
    """Météo actuelle et prévisions du jour pour une ville."""
    city = (city or "").strip()
    if not city or len(city) > 80:
        return "Indique un nom de ville valide."
    try:
        g = requests.get("https://geocoding-api.open-meteo.com/v1/search", params={"name": city, "count": 1, "language": "fr"}, timeout=15).json()["results"][0]
        w = requests.get("https://api.open-meteo.com/v1/forecast", timeout=15, params={
            "latitude": g["latitude"], "longitude": g["longitude"], "current": "temperature_2m,wind_speed_10m,weather_code",
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum", "timezone": "auto", "forecast_days": 1}).json()
        c, d = w["current"], w["daily"]
        return (f"{g['name']} : {c['temperature_2m']}°C, vent {c['wind_speed_10m']} km/h (code météo {c['weather_code']}). "
                f"Aujourd'hui : {d['temperature_2m_min'][0]}° à {d['temperature_2m_max'][0]}°, pluie {d['precipitation_sum'][0]} mm.")
    except (KeyError, IndexError):
        return f"Ville introuvable : {city}."
    except Exception as e:
        return f"Erreur météo : {type(e).__name__}"


class _Text(HTMLParser):
    skip = False
    def __init__(self): super().__init__(); self.out = []
    def handle_starttag(self, t, a): self.skip = t in ("script", "style", "noscript")
    def handle_endtag(self, t): self.skip = False
    def handle_data(self, d):
        if not self.skip and d.strip(): self.out.append(d.strip())


def check_public_url(url: str):
    """None si l'URL est publique et sûre ; sinon un message d'erreur. Bloque localhost, réseau privé, métadonnées cloud (SSRF)."""
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        return "Seuls les liens http(s) sont autorisés."
    try:
        infos = socket.getaddrinfo(p.hostname, p.port or (443 if p.scheme == "https" else 80), proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        return "Adresse introuvable."
    for info in infos:
        if not ipaddress.ip_address(info[4][0].split("%")[0]).is_global:
            return "Refusé : cette adresse n'est pas un site public (réseau local ou interne)."
    return None


def read_webpage(url: str) -> str:
    """Récupère le texte d'une page web publique (pour résumer un article, lire une doc…)."""
    try:
        for _ in range(5):                                   # redirections suivies à la main, chacune revérifiée
            err = check_public_url(url)
            if err:
                return err
            r = requests.get(url, timeout=20, allow_redirects=False, stream=True, headers={"User-Agent": "Mozilla/5.0 Ziggy"})
            if r.is_redirect and r.headers.get("Location"):
                url = urljoin(url, r.headers["Location"])
                continue
            raw = r.raw.read(2_000_000, decode_content=True)
            p = _Text(); p.feed(raw.decode(r.encoding or "utf-8", errors="replace"))
            return re.sub(r"\s+", " ", " ".join(p.out))[:15000]
        return "Trop de redirections."
    except Exception as e:
        return f"Erreur : {type(e).__name__}"


def set_reminder(text: str, minutes: float = 0, at: str = "") -> str:
    """Programme un rappel persistant : dans N minutes (minutes) OU à une date précise (at, ISO local ex 2026-10-25T14:30:00)."""
    return rem.add(text, minutes, at)[1]


def list_reminders() -> list:
    """Liste les rappels à venir (id, texte, date)."""
    return rem.list_active() or ["Aucun rappel programmé."]


def cancel_reminder(reminder_id: int) -> str:
    """Annule un rappel via son id."""
    return "Rappel annulé." if rem.cancel(reminder_id) else "Rappel introuvable."


def clipboard_read() -> str:
    """Lit le contenu du presse-papiers."""
    try:
        import pyperclip; return pyperclip.paste()[:10000]
    except Exception as e:
        return f"Erreur : {type(e).__name__}"


def clipboard_write(text: str) -> str:
    """Copie du texte dans le presse-papiers."""
    try:
        import pyperclip; pyperclip.copy(text[:100000]); return "Copié."
    except Exception as e:
        return f"Erreur : {type(e).__name__}"


def pop_due() -> list:
    return rem.pop_due()


EXTRA_TOOLS = [weather, read_webpage, set_reminder, list_reminders, cancel_reminder, clipboard_read, clipboard_write]
