"""Dépendances, ressources, configuration (préférences)."""
import json, pytest
from conftest import ROOT


def test_dependances_et_ressources_presentes(app):
    import selfcheck
    assert selfcheck.check() == []


def test_requirements_borne_toutes_les_versions():
    for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines():
        line = line.split("#")[0].strip()
        if line:
            assert ">=" in line and "<" in line, f"version non bornée : {line}"


def test_configuration_par_defaut_sure(app):
    s = app.settings.load()
    assert s["autostart"] is False and s["tray"] is True and s["startup_behavior"] == "open"
    assert s["voice"]["tts_enabled"] is False
    assert app.settings.effective_model() == "gemini-3.5-flash"


def test_modele_via_variable_d_environnement(home, monkeypatch):
    from conftest import load_app
    monkeypatch.setenv("GEMINI_MODEL", "gemini-test-env")
    z = load_app(home, monkeypatch)
    monkeypatch.setenv("GEMINI_MODEL", "gemini-test-env")      # load_app nettoie l'environnement
    assert z.settings.effective_model() == "gemini-test-env"
    z.settings.update({"model": "gemini-choisi"})
    assert z.settings.effective_model() == "gemini-choisi"     # le réglage de l'utilisateur est prioritaire


@pytest.mark.parametrize("bad", [
    {"inconnu": 1}, {"autostart": "oui"}, {"startup_behavior": "x"}, {"model": "a b"}, {"model": "x"},
    {"voice": {"rate": 5}}, {"voice": {"rate": True}}, {"voice": {"volume": -1}}, {"voice": {"zzz": 1}}, {"voice": "x"}, "pas un dict"])
def test_validation_rejette_les_valeurs_invalides(app, bad):
    with pytest.raises(ValueError):
        app.settings.validate_patch(bad)


def test_preferences_persistent_et_se_fusionnent(app, restart):
    app.settings.update({"voice": {"rate": 1.5}})
    app.settings.update({"voice": {"volume": 0.4}, "model": "gemini-3.7-flash"})
    z2 = restart()
    s = z2.settings.load()
    assert s["voice"]["rate"] == 1.5 and s["voice"]["volume"] == 0.4 and s["model"] == "gemini-3.7-flash"
    assert s["voice"]["stt_enabled"] is True                       # les autres valeurs restent


def test_fichier_de_preferences_corrompu_ne_bloque_pas(app):
    app.settings.FILE.write_text("{ pas du json", encoding="utf-8")
    assert app.settings.load()["startup_behavior"] == "open"
    assert list(app.settings.FILE.parent.glob("settings.corrompu-*.json")), "le fichier corrompu doit être conservé"


def test_reinitialiser_les_preferences_garde_modele_et_cle(app):
    from conftest import FAKE_KEY
    app.secrets_store.save_key(FAKE_KEY)
    app.settings.update({"model": "gemini-3.7-flash", "voice": {"rate": 1.8, "tts_enabled": True}, "tray": False})
    s = app.settings.reset_preferences()
    assert s["model"] == "gemini-3.7-flash" and s["voice"]["rate"] == 1.0 and s["tray"] is True
    assert app.secrets_store.load_key() == FAKE_KEY
