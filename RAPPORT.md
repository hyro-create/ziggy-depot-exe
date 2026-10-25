# Rapport final — Ziggy 1.0.0

## Ce qui n'a PAS pu être fait ici
Environnement : Linux, sans Windows, sans Wine, sans Inno Setup. **`Ziggy.exe` et `Ziggy-Setup.exe` n'ont donc pas été produits** :
un exécutable Windows ne peut être compilé que sous Windows. Tout est prêt pour que `build.bat` puis `installer.bat`
(ou le workflow GitHub) les produisent. Le script Inno Setup (`installer/ziggy.iss`) **n'a jamais été compilé** : relu et vérifié
par tests de contenu uniquement.

## Problèmes trouvés et corrigés
| # | Problème | Correction |
|---|---|---|
| 1 | Données à côté du programme/projet (perdues en « un seul fichier », écrasables à l'installation) | `%LOCALAPPDATA%\Ziggy`, séparé du programme ; import (copie) des anciennes données |
| 2 | Clé Gemini en clair dans `.env` | Stockage chiffré DPAPI ; migration automatique depuis `.env` ; jamais renvoyée à l'interface ni journalisée |
| 3 | Ziggy quittait si la clé manquait | Il démarre et guide vers Paramètres ; 8 états d'erreur expliqués en français |
| 4 | Connexions SQLite jamais fermées (verrouillent `memoire.db` sous Windows : mises à jour/désinstallation bloquées) | Connexion qui se ferme toujours |
| 5 | Aucune version de schéma, aucune sauvegarde | Migrations transactionnelles versionnées, sauvegarde avant migration/effacement, refus d'ouvrir une base plus récente |
| 6 | `run_command` (shell=True) | Supprimé : actions fixes validées, aucune commande libre |
| 7 | Confirmation d'envoi de mail contournable par le modèle (règle « un tour plus tard ») | Confirmation par **clic** utilisateur (ou `/oui id` Telegram), pour 6 types d'actions sensibles |
| 8 | L'IA pouvait créer/déplacer des scripts (ex. dossier Démarrage) | Fichiers exécutables/scripts jamais créés, déplacés, ouverts |
| 9 | L'IA pouvait lire ses propres secrets (`.env`, clé, jetons, `.ssh`) car sous le dossier utilisateur | Dossiers protégés refusés |
| 10 | `read_webpage` pouvait atteindre `localhost`/réseau privé/métadonnées cloud (SSRF) | Adresses non publiques refusées, redirections revérifiées |
| 11 | API locale utilisable par n'importe quel site web ouvert dans le navigateur | Vérification Host/Origin/Sec-Fetch-Site, jeton aléatoire, JSON obligatoire, CSP |
| 12 | Rappels en mémoire vive (perdus à la fermeture) | Rappels persistants, « manqués » signalés au redémarrage |
| 13 | Pas d'instance unique, serveur de développement Flask | Mutex Windows + détection ; serveur Waitress |
| 14 | Pas de journaux exploitables | Journal rotatif avec masquage des secrets (y compris dans les traces d'erreur) |
| 15 | Chemin des ressources/`__file__` incorrect une fois compilé | `paths.py` ; ressources embarquées vérifiées par `--check` et le test de fumée |

## Tests
**Automatiques, réussis (Linux, hors ligne) : 86 réussis, 2 ignorés** — `python -m pytest`
- Syntaxe de tous les fichiers ; JS de l'interface ; aucun secret ni `shell=True` ; scripts `.bat` ; contenu du script Inno.
- Dépendances et ressources ; configuration, validation, fichier corrompu ; **clé** : absente, enregistrement, modification, suppression, survie au redémarrage ;
  jamais renvoyée par une route, jamais dans un autre fichier ni les journaux.
- Base : création/réouverture, **migration d'une ancienne base avec sauvegarde**, base plus récente intacte, migration en échec sans modification, effacements.
- **Mise à jour sans perte** (base + réglages + clé d'une version antérieure) ; mémoire, tâches, rappels après redémarrage.
- Sécurité : routes sans jeton, mauvais Host/Origin, requêtes inter-sites, confirmations, commandes refusées, fichiers protégés, SSRF.
- Chaque outil est déclarable pour Gemini.

**Réels (vrais appels, résultat dépendant de l'environnement)** : erreur réseau vers un port fermé ; fausse clé vers la vraie API
(ici : « Erreur réseau » car pas d'accès à Google ; en ligne : « Clé invalide »). Jamais « Connecté ».

**Simulés (clairement nommés `SIMULE`)** : classement des erreurs 400/401/403/404/429/5xx, quota, liste filtrée des modèles, logique du test en deux appels.
**Aucun test n'a réussi un appel réel à Gemini** : pas de clé ni d'accès Internet à Google dans l'environnement.

**Interface** : 29 vérifications dans un navigateur simulé (jsdom) branché sur un vrai serveur Ziggy : engrenage, clé (afficher/masquer, enregistrer, tester, supprimer),
modèles, voix, sauvegarde, historique, effacements, réinitialisation, chat sans clé. Ce n'est pas un vrai navigateur.

**Application compilée (binaire Linux)** : `--check` OK ; test de fumée 22/22 (démarrage, interface, ressources embarquées, données dans le dossier prévu et pas dans
le dossier du programme, clé absente des fichiers/journaux, redémarrage avec clé et paramètres conservés).

## Reste à tester sur Windows 11
Voir `TESTS_WINDOWS.md` : compilation réelle, **Inno Setup (installation, raccourcis, mise à jour, rétrogradation, désinstallation avec/sans suppression des données)**,
**chiffrement DPAPI**, démarrage automatique (registre), icône de la barre des tâches, instance unique (mutex), micro et synthèse vocale (navigateur),
vraie clé Gemini (connexion, liste des modèles, réponses, quotas), SmartScreen/antivirus.

## Limites connues
- Intégrations Google, Microsoft, Spotify, Notion, Todoist, Telegram : conservées, **jamais testées contre les vrais services**.
- Jetons des intégrations optionnelles dans `.env` : non chiffrés.
- La qualité des appels d'outils dépend du modèle Gemini choisi ; la liste des modèles ne garantit pas leur compatibilité avec les outils.
- SSRF : la vérification DNS précède la connexion (une attaque « DNS rebinding » très ciblée n'est pas totalement exclue).
- Testé avec Python 3.12 uniquement. Exécutable non signé (alertes SmartScreen possibles).
- Quotas gratuits Gemini : dépendent du modèle et du compte.
