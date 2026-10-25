# Ziggy — assistant personnel (Windows 11)

Ziggy tourne sur ton PC, parle avec l'API officielle **Google Gemini**, se souvient de tes conversations,
organise tes tâches et agit sur tes fichiers et applications — toujours avec ta confirmation pour les actions sensibles.

---

## 1. Utiliser Ziggy (utilisateur final)

1. Lance **Ziggy-Setup.exe** (aucun droit administrateur, aucune installation de Python).
2. Ouvre Ziggy (raccourci Bureau ou menu Démarrer). Clique sur l'engrenage **⚙**.
3. « Intelligence artificielle — Gemini » : colle ta clé (gratuite : <https://aistudio.google.com/apikey>) → **Enregistrer** → **Tester la connexion**.
   Le voyant doit passer à *Connecté*. Tu ne ressaisis plus jamais la clé.

**Mettre à jour** : relance simplement le nouveau `Ziggy-Setup.exe`. Mémoire, historique, paramètres et clé sont conservés.
**Désinstaller** : Paramètres Windows → Applications. Ziggy te demande si tu veux AUSSI supprimer tes données (réponse par défaut : non).

### Où sont mes données ?
`%LOCALAPPDATA%\Ziggy` — jamais dans le dossier du programme, jamais dans un dossier temporaire.

| Fichier | Contenu |
|---|---|
| `memoire.db` | conversations, souvenirs, tâches, rappels (SQLite, avec numéro de version) |
| `settings.json` | préférences (modèle, voix, démarrage…) — aucun secret |
| `gemini_key.dat` | clé API **chiffrée par Windows (DPAPI)**, liée à ton compte |
| `backups\` | sauvegardes (automatiques avant migration/effacement, ou à la demande) |
| `logs\ziggy.log` | journal (clés et jetons masqués) |
| `.env` | intégrations optionnelles (Microsoft, Todoist, Notion, Spotify, Telegram) |

Ancien Ziggy (données à côté du programme) : au premier lancement, `memoire.db`, `.env` et les jetons trouvés à côté du
programme sont **copiés** (jamais déplacés) dans le dossier ci-dessus. Une clé Gemini restée dans `.env` est transférée
dans le stockage chiffré et effacée du `.env`.

### Sécurité (ce qui est garanti, et ses limites)
- Ziggy **ne peut pas exécuter de commande libre** (pas de PowerShell/CMD). Il dispose d'actions fixes et validées.
- **Confirmation par clic** (carte « Confirmation requise ») pour : envoyer un mail, écraser/déplacer un fichier,
  supprimer un événement, verrouiller la session, envoyer un fichier sur OneDrive. Telegram : `/oui id` ou `/non id`.
- Ziggy ne crée, ne déplace et n'ouvre jamais de fichier exécutable ou script (`.exe .bat .ps1 .vbs .sh .py …`).
- Ziggy ne peut pas lire ses propres données, ni `.ssh`, `.aws`… ; il ne peut pas ouvrir de pages web locales ou du réseau privé.
- L'interface web n'écoute que sur `127.0.0.1`, vérifie Host/Origin et exige un jeton aléatoire : un site web ne peut pas
  utiliser l'API de Ziggy ni lire ta clé (aucune route ne renvoie la clé).
- **Limite honnête** : une personne ou un logiciel qui contrôle ta session Windows peut toujours obtenir ta clé.
  Les mots de passe/jetons des intégrations optionnelles du `.env` ne sont, eux, **pas chiffrés**.
- Applications supplémentaires ouvrables : ajoute-les dans `settings.json` → `"custom_apps": {"chrome": "C:\\...\\chrome.exe"}`
  (chemin absolu d'un `.exe` existant).

### Paramètres (⚙)
Gemini (clé, test réel, modèle parmi ceux de ton compte) · Général (démarrage Windows, barre des tâches, comportement) ·
Voix (micro, lecture, voix française, débit, volume) · Mémoire (dossier, historique, sauvegarde, effacements) · À propos (versions, état, aide).
La dictée vocale utilise le service en ligne du navigateur (Chrome/Edge) et **nécessite Internet**.

---

## 2. Obtenir Ziggy-Setup.exe (compilation)

**Prérequis, à faire UNE fois sur le PC qui compile :**
1. **Python 3.12 (64 bits)** — <https://www.python.org/downloads/> — cocher « Add Python to PATH ».
2. **Inno Setup 6.3 ou plus récent** (gratuit) — <https://jrsoftware.org/isdl.php> — c'est la seule étape à faire à la main pour l'installateur.

**Puis, dans le dossier du projet, double-clique dans l'ordre :**

| Script | Rôle |
|---|---|
| `install_dev.bat` | crée l'environnement et installe les dépendances (une fois) |
| `test.bat` | lance les vérifications (facultatif : `build.bat` les relance) |
| `build.bat` | dépendances → tests → PyInstaller → vérification de l'exe → test de fumée → `dist\Ziggy\Ziggy.exe` |
| `installer.bat` | Inno Setup → `installer_output\Ziggy-Setup.exe` |

Chaque script s'arrête au premier échec avec un message en français et ne touche jamais à `%LOCALAPPDATA%\Ziggy`.

**Sans rien installer** : mets le projet sur GitHub et lance « Actions → *Construire Ziggy-Setup.exe* → Run workflow » :
un Windows gratuit de GitHub compile, teste (y compris les tests Windows) et te donne `Ziggy-Setup.exe` à télécharger.

L'icône (lotus) vient de `assets\lotus_source.png` ; `python tools\make_icon.py` la régénère.
Changer de version : modifie `version.py`, puis `build.bat` et `installer.bat`.

### Structure
`ziggy.py` (routes, outils, démarrage) · `gemini.py` (API, test, modèles, erreurs) · `secrets_store.py` (clé DPAPI) ·
`settings.py` · `database.py` (migrations/sauvegardes) · `security.py` · `actions.py` (confirmations) · `reminders.py` ·
`system_integration.py` (démarrage Windows, barre des tâches, instance unique) · `extras.py` · `google_services.py` ·
`microsoft_services.py` · `apps.py` · `telegram_bot.py` · `static\` (interface, aide) · `installer\ziggy.iss` · `ziggy.spec` · `tests\`.

### Intégrations optionnelles
Gmail/Agenda/Drive (`credentials.json` dans le dossier de données), Outlook/OneDrive/To Do (`MS_CLIENT_ID` dans `.env`),
Todoist, Notion, Spotify (Premium), Telegram : variables dans `%LOCALAPPDATA%\Ziggy\.env`. Étapes détaillées :
Google Cloud Console (API Gmail, Calendar, Drive, écran de consentement « Externe », client « Application de bureau ») ;
Microsoft Entra (inscription d'application, client public, redirection `http://localhost`, autorisations Graph
Mail.ReadWrite, Mail.Send, Calendars.ReadWrite, Files.ReadWrite, Tasks.ReadWrite, Contacts.Read, User.Read) ;
Spotify (redirection `http://127.0.0.1:8888/callback`) ; Telegram (@BotFather puis `/start` pour obtenir ton identifiant).

### Dépannage
Journal : `%LOCALAPPDATA%\Ziggy\logs\ziggy.log`. Diagnostic : `Ziggy-diagnostic.exe --check` (dans le dossier d'installation).
« Port 5005 utilisé » : variable d'environnement `ZIGGY_PORT`. SmartScreen/antivirus peuvent signaler un programme non signé :
c'est normal pour un exécutable PyInstaller sans certificat de signature de code.
