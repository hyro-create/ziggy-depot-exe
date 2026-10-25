"""Protection de l'interface web locale.

- Écoute uniquement sur 127.0.0.1 (jamais sur le réseau).
- Contrôle de l'en-tête Host (contre le « DNS rebinding »), de Origin et de Sec-Fetch-Site (contre les sites tiers).
- Toutes les routes /api/* exigent un jeton secret aléatoire, régénéré à chaque démarrage et fourni uniquement à
  la page de Ziggy : un autre site web ne peut ni le lire (pas de CORS) ni deviner.
- Les routes qui modifient quelque chose exigent du JSON (un site tiers ne peut pas l'envoyer sans autorisation CORS).
- Aucune route ne renvoie la clé API.
Limite : un programme local qui lit la page d'accueil obtient le jeton ; la protection vise les sites web, pas les logiciels déjà installés sur ton PC.
"""
import hmac, secrets
from flask import request, jsonify

TOKEN = secrets.token_urlsafe(32)
PUBLIC_API = {"/api/ping"}
CSP = ("default-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
       "font-src https://fonts.gstatic.com; img-src 'self' data:; script-src 'self' 'unsafe-inline'; "
       "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")


def install(app, port: int) -> None:
    hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
    origins = {f"http://{h}" for h in hosts}

    @app.before_request
    def _guard():
        if request.host not in hosts:
            return jsonify(error="Hôte refusé."), 403
        origin = request.headers.get("Origin")
        if origin and origin not in origins:
            return jsonify(error="Origine refusée."), 403
        site = request.headers.get("Sec-Fetch-Site")
        if site and site not in ("same-origin", "none"):
            return jsonify(error="Requête inter-sites refusée."), 403
        if request.path.startswith("/api/") and request.path not in PUBLIC_API:
            if not hmac.compare_digest(request.headers.get("X-Ziggy-Token", ""), TOKEN):
                return jsonify(error="Non autorisé : recharge la page de Ziggy."), 401
            if request.method in ("POST", "PUT", "PATCH", "DELETE") and not request.is_json:
                return jsonify(error="Le contenu doit être du JSON."), 415

    @app.after_request
    def _headers(resp):
        resp.headers["Content-Security-Policy"] = CSP
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "no-referrer"
        if request.path.startswith("/api/") or request.path in ("/", "/aide"):
            resp.headers["Cache-Control"] = "no-store"
        return resp
