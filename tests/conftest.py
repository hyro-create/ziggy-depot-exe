"""Outils de test : chaque test travaille dans un dossier de données temporaire (jamais dans tes vraies données)."""
import importlib, logging, os, sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
MODULES = ["ziggy", "paths", "logsetup", "secrets_store", "settings", "database", "gemini", "security", "actions", "reminders",
           "system_integration", "extras", "google_services", "microsoft_services", "apps", "telegram_bot", "readers", "version", "selfcheck"]
ENV_VARS = ("GEMINI_API_KEY", "GEMINI_MODEL", "TODOIST_TOKEN", "NOTION_TOKEN", "SPOTIFY_CLIENT_ID", "TELEGRAM_BOT_TOKEN",
            "MS_CLIENT_ID", "ZIGGY_EXTRA_DIRS", "ZIGGY_PORT")
FAKE_KEY = "AI" + "zaSyFAKE_" + "0123456789_abcdefghijklmnopqrstu"      # fausse clé (construite pour ne pas ressembler à une vraie dans le dépôt)
FAKE_KEY2 = "AI" + "zaSyOTHER_" + "9876543210_zyxwvutsrqponmlkjihgfed"


def load_app(home: Path, monkeypatch, scheduler=False):
    """(Re)démarre Ziggy comme à l'ouverture du programme, avec ce dossier de données."""
    monkeypatch.setenv("ZIGGY_HOME", str(home))
    for v in ENV_VARS:
        monkeypatch.delenv(v, raising=False)
    lg = logging.getLogger("ziggy")
    for h in list(lg.handlers):
        lg.removeHandler(h); h.close()
    for m in MODULES:
        sys.modules.pop(m, None)
    z = importlib.import_module("ziggy")
    z.bootstrap(scheduler=scheduler)
    return z


class Client:
    """Client de test de l'API locale, avec Host et jeton valides."""
    def __init__(self, z, token=True):
        self.z, self.c = z, z.app.test_client()
        self.h = {"X-Ziggy-Token": z.security.TOKEN} if token else {}

    def _kw(self, kw):
        kw.setdefault("base_url", "http://127.0.0.1:5005")
        kw["headers"] = {**self.h, **kw.get("headers", {})}
        return kw

    def get(self, p, **kw): return self.c.get(p, **self._kw(kw))
    def post(self, p, body=None, **kw): return self.c.post(p, json=body or {}, **self._kw(kw))
    def delete(self, p, **kw): return self.c.delete(p, json={}, **self._kw(kw))


@pytest.fixture
def home(tmp_path):
    return tmp_path / "ziggy-data"


@pytest.fixture
def app(home, monkeypatch):
    return load_app(home, monkeypatch)


@pytest.fixture
def api(app):
    return Client(app)


@pytest.fixture
def restart(home, monkeypatch):
    """Simule fermeture + réouverture de Ziggy sur le MÊME dossier de données."""
    return lambda: load_app(home, monkeypatch)


class FakeResp:
    def __init__(self, text): self.text = text


class FakeModels:
    def __init__(self, text="Bonjour, je suis un faux Gemini.", fail=None):
        self.text, self.fail, self.calls = text, fail, []
    def get(self, model): 
        if self.fail: raise self.fail
        return object()
    def generate_content(self, **kw):
        self.calls.append(kw)
        if self.fail: raise self.fail
        return FakeResp(self.text)


class FakeClient:
    def __init__(self, **kw): self.models = FakeModels(**kw)
