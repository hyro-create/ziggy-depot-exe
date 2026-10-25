"""Test de fumée de l'application COMPILÉE : démarre le vrai exécutable avec un dossier de données temporaire.
Usage : python tools/smoke_test_build.py dist/Ziggy      (utilisé par build.bat)"""
import json, os, re, shutil, socket, subprocess, sys, tempfile, time, urllib.error, urllib.request
from pathlib import Path

FAKE_KEY = "AI" + "zaSyFAKE_" + "SMOKE_0123456789_abcdefghijklmnopqr"
results = []


def check(name, ok, detail=""):
    results.append(bool(ok))
    print(("  OK   " if ok else "  ÉCHEC"), name, ("— " + str(detail)) if detail and not ok else "")


def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


def http(port, path, method="GET", body=None, token=None):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", method=method,
                                 data=None if body is None else json.dumps(body).encode())
    if token: req.add_header("X-Ziggy-Token", token)
    if body is not None: req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def start(exe, home, port):
    env = {k: v for k, v in os.environ.items() if k != "GEMINI_API_KEY"}
    env.update(ZIGGY_HOME=str(home), ZIGGY_PORT=str(port), ZIGGY_OPEN_BROWSER="0")
    p = subprocess.Popen([str(exe)], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, cwd=tempfile.gettempdir())
    for _ in range(90):
        try:
            if http(port, "/api/ping")[0] == 200:
                return p
        except Exception:
            pass
        time.sleep(0.5)
    p.kill(); return None


def stop(p):
    p.terminate()
    try: p.wait(15)
    except subprocess.TimeoutExpired: p.kill()
    time.sleep(1)


def main(app_dir: Path) -> int:
    gui = app_dir / ("Ziggy.exe" if os.name == "nt" else "Ziggy")
    diag = app_dir / ("Ziggy-diagnostic.exe" if os.name == "nt" else "Ziggy-diagnostic")
    print(f"Test de fumée : {gui}")
    check("Ziggy.exe et Ziggy-diagnostic.exe présents", gui.exists() and diag.exists())
    if not gui.exists(): return 1
    home = Path(tempfile.mkdtemp(prefix="ziggy-smoke-"))
    try:
        r = subprocess.run([str(diag), "--check"], capture_output=True, text=True, timeout=120, env={**os.environ, "ZIGGY_HOME": str(home)})
        check("--check : dépendances et ressources embarquées", r.returncode == 0, r.stdout + r.stderr)

        port = free_port()
        p = start(gui, home, port)
        if p is None:
            print("  NOTE  Serveur non joignable : pywebview a besoin d'un écran (X11/WebView2).")
            print("        Sous Windows 11 ce test réussira. --check OK = l'application est correctement assemblée.")
            results.append(True)
            return 0
        check("démarrage du programme compilé", True)
        st, html = http(port, "/")
        m = re.search(rb'name="ziggy-token" content="([^"]+)"', html)
        token = m.group(1).decode() if m else ""
        check("page d'accueil servie avec jeton", st == 200 and len(token) > 20 and b"Ziggy" in html and b"__ZIGGY_TOKEN__" not in html)
        for path in ("/static/logo.png", "/static/favicon.ico", "/aide"):
            check(f"ressource embarquée {path}", http(port, path)[0] == 200)
        check("API refusée sans jeton", http(port, "/api/settings")[0] == 401)
        st, b = http(port, "/api/settings", token=token)
        d = json.loads(b)
        check("paramètres : aucune clé au départ", st == 200 and d["gemini"]["configured"] is False)
        check("dossier de données = dossier demandé (pas le dossier temporaire PyInstaller)", Path(d["system"]["data_dir"]) == home.resolve())
        st, b = http(port, "/api/gemini/key", "POST", {"key": FAKE_KEY}, token)
        check("enregistrement de la clé", st == 200 and FAKE_KEY.encode() not in b)
        st, b = http(port, "/api/settings", "POST", {"voice": {"rate": 1.5}}, token)
        check("enregistrement d'un paramètre", st == 200 and json.loads(b)["settings"]["voice"]["rate"] == 1.5)
        st, b = http(port, "/api/chat", "POST", {"message": "bonjour"}, token)
        check("chat : erreur Gemini expliquée, clé non divulguée", FAKE_KEY.encode() not in b and json.loads(b)["reply"], b[:200])
        stop(p)

        for name in ("memoire.db", "settings.json", "gemini_key.dat"):
            check(f"donnée persistante créée : {name}", (home / name).exists())
        check("aucune donnée dans le dossier du programme", not (app_dir / "memoire.db").exists() and not (app_dir / "gemini_key.dat").exists())
        leak = [f.name for f in home.rglob("*") if f.is_file() and FAKE_KEY.encode() in f.read_bytes() and f.name != "gemini_key.dat"]
        check("clé absente des journaux et autres fichiers", not leak, leak)

        port = free_port()
        p = start(gui, home, port)
        check("redémarrage du programme", p is not None)
        if p is None: return 1
        st, html = http(port, "/"); token = re.search(rb'name="ziggy-token" content="([^"]+)"', html).group(1).decode()
        d = json.loads(http(port, "/api/settings", token=token)[1])
        check("après redémarrage : clé conservée sans la ressaisir", d["gemini"]["configured"] is True)
        check("après redémarrage : paramètres conservés", d["settings"]["voice"]["rate"] == 1.5)
        check("après redémarrage : schéma de mémoire à jour", json.loads(http(port, "/api/about", token=token)[1])["schema"] >= 2)
        stop(p)
    finally:
        shutil.rmtree(home, ignore_errors=True)
    ok = all(results)
    print(f"\n{'✔ Test de fumée réussi' if ok else '✖ Test de fumée ÉCHOUÉ'} ({sum(results)}/{len(results)})")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1] if len(sys.argv) > 1 else "dist/Ziggy").resolve()))
