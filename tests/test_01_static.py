"""Audit statique : syntaxe, secrets, commandes dangereuses, scripts, installateur."""
import py_compile, re
from pathlib import Path
from conftest import ROOT

SKIP = {".venv", "build", "dist", "__pycache__", ".pytest_cache", "installer_output"}
def files(pattern):
    return [p for p in ROOT.rglob(pattern) if not (set(p.relative_to(ROOT).parts) & SKIP)]


def test_syntaxe_de_tous_les_fichiers_python():
    py = files("*.py")
    assert len(py) >= 20
    for f in py:
        py_compile.compile(str(f), doraise=True)


def test_javascript_de_l_interface_valide():
    import subprocess, shutil
    if not shutil.which("node"):
        import pytest; pytest.skip("node absent")
    html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
    js = re.search(r"<script>(.*)</script>", html, re.S).group(1)
    tmp = ROOT / "tests" / "_ui.js"
    tmp.write_text(js, encoding="utf-8")
    try:
        r = subprocess.run(["node", "--check", str(tmp)], capture_output=True, text=True)
    finally:
        tmp.unlink()
    assert r.returncode == 0, r.stderr


def test_aucune_cle_ou_secret_dans_le_projet():
    pats = [re.compile(r"AI" + r"za[0-9A-Za-z_\-]{30,}"), re.compile(r"sk-[A-Za-z0-9]{20,}"), re.compile(r"ghp_[A-Za-z0-9]{30,}")]
    bad = []
    for f in ROOT.rglob("*"):
        if not f.is_file() or (set(f.relative_to(ROOT).parts) & SKIP) or f.suffix in (".png", ".ico", ".pyc"):
            continue
        txt = f.read_text(encoding="utf-8", errors="ignore")
        bad += [f"{f.relative_to(ROOT)}" for p in pats if p.search(txt)]
    assert not bad, f"Secret détecté dans : {bad}"
    for forbidden in (".env", "gemini_key.dat", "token.json", "ms_token.json", "memoire.db", "credentials.json"):
        assert not (ROOT / forbidden).exists(), f"{forbidden} ne doit pas être dans le projet"


def test_aucun_shell_true_ni_execution_libre():
    for f in files("*.py"):
        if f.parts[-2] == "tests":
            continue
        txt = f.read_text(encoding="utf-8")
        assert "shell=True" not in txt, f"shell=True dans {f.name}"
        assert "os.system(" not in txt and "eval(" not in txt.replace("literal_eval", ""), f"exécution libre dans {f.name}"
    z = (ROOT / "ziggy.py").read_text(encoding="utf-8")
    assert "def run_command" not in z and "ZIGGY_ALLOW_COMMANDS" not in z


def test_scripts_bat_en_crlf_et_s_arretent_en_cas_d_erreur():
    bats = files("*.bat")
    assert {b.name for b in bats} >= {"install_dev.bat", "test.bat", "build.bat", "installer.bat", "lancer.bat"}
    for b in bats:
        raw = b.read_bytes()
        assert b"\r\n" in raw and b"\n" not in raw.replace(b"\r\n", b""), f"{b.name} doit être en CRLF"
        if b.name != "lancer.bat":
            assert b"errorlevel" in raw, f"{b.name} doit tester les erreurs"


def test_script_inno_setup_contient_les_garanties_demandees():
    iss = (ROOT / "installer" / "ziggy.iss").read_text(encoding="utf-8")
    for needle in ("AppId=", "PrivilegesRequired=lowest", "AppMutex=ZiggyAppMutex", "DefaultDirName={autopf}",
                   "{autodesktop}", "{autoprograms}", "[UninstallDelete]" if False else "[Icons]", "UninstallSilent", "SetupIconFile", "[InstallDelete]"):
        assert needle in iss, f"{needle} manquant dans ziggy.iss"
    # Les données personnelles ne doivent jamais être listées dans les sections de fichiers de l'installateur
    sections = re.split(r"^\[", iss, flags=re.M)
    for s in sections:
        if s.startswith(("Files]", "InstallDelete]", "UninstallDelete]", "Dirs]")):
            assert "localappdata}\\Ziggy" not in s and "LocalAppData}\\Ziggy" not in s, "l'installateur ne doit pas toucher aux données"
    # Suppression des données uniquement après question, jamais en mode silencieux
    assert iss.count("DelTree") == 1
    code = iss[iss.index("DelTree") - 900: iss.index("DelTree")]
    assert "MsgBox" in code and "UninstallSilent" in code and "IDYES" in code


def test_spec_pyinstaller_embarque_interface_et_icone():
    spec = (ROOT / "ziggy.spec").read_text(encoding="utf-8")
    for needle in ('"static"', "assets", "ziggy.ico", "googleapiclient", "docx", "pptx", "certifi", "console=False", "Ziggy-diagnostic"):
        assert needle in spec, f"{needle} manquant dans ziggy.spec"
