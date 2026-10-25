# Tests à effectuer sur Windows 11 (non réalisables dans l'environnement de développement Linux)

Cocher chaque ligne après essai. Ne distribue pas Ziggy tant que ces tests ne sont pas faits.
Astuce : le workflow GitHub `windows-build.yml` exécute déjà les tests automatiques sous Windows (dont DPAPI) et le test de fumée.

## Compilation
- [ ] `install_dev.bat` puis `test.bat` : « Tous les tests sont passés » (le test DPAPI doit s'exécuter, pas « skipped »).
- [ ] `build.bat` : arrive à « Termine : dist\Ziggy\Ziggy.exe » (test de fumée 22/22).
- [ ] `installer.bat` : crée `installer_output\Ziggy-Setup.exe`.
- [ ] Propriétés de `Ziggy.exe` : icône lotus, version 1.0.0.

## Installation
- [ ] Setup.exe ne demande PAS de droits administrateur ; installe dans `%LOCALAPPDATA%\Programs\Ziggy`.
- [ ] Raccourcis créés : Bureau et menu Démarrer (avec l'icône lotus). « Désinstaller Ziggy » dans le menu Démarrer.
- [ ] Case « Lancer Ziggy » à la fin : Ziggy démarre, aucune fenêtre noire, le navigateur s'ouvre.
- [ ] Windows Defender / SmartScreen : noter les alertes éventuelles.

## Fonctionnement
- [ ] Paramètres : enregistrer une VRAIE clé → « Tester la connexion » = Connecté ; liste des modèles chargée ; un message de chat reçoit une réponse.
- [ ] Clé fausse → « Clé invalide » ; débrancher Internet → « Erreur réseau ».
- [ ] `%LOCALAPPDATA%\Ziggy\gemini_key.dat` : ouvert dans le Bloc-notes, la clé n'est pas lisible.
- [ ] Fermer/relancer Ziggy : clé, paramètres, historique, tâches, rappels toujours là, sans ressaisie.
- [ ] Lancer Ziggy deux fois : la 2e ouvre l'interface existante, pas de doublon.
- [ ] Rappel à 1 min : notification dans Ziggy ; fermer Ziggy avant l'échéance et le rouvrir après : rappel « manqué » affiché.
- [ ] Démarrage Windows : activer, se déconnecter/reconnecter → Ziggy démarre ; désactiver → n'est plus lancé (clé `HKCU\...\Run\Ziggy`).
- [ ] Barre des tâches : icône lotus, menu Ouvrir / Paramètres / Quitter ; mode « discret » au démarrage automatique.
- [ ] Micro : Chrome/Edge, autoriser le micro, dicter une phrase (nécessite Internet). Lecture vocale avec une voix française, débit et volume.
- [ ] Demander à Ziggy d'écraser un fichier / d'en déplacer un : carte de confirmation, rien ne se passe avant le clic.
- [ ] « Verrouiller la session » : confirmation puis verrouillage.
- [ ] « Ouvre le bloc-notes », « ouvre la calculatrice » fonctionnent ; « ouvre C:\Windows\System32\cmd.exe » est refusé.

## Mise à jour et désinstallation
- [ ] Installer 1.0.0, créer des données, puis installer une version 1.0.1 (changer `version.py`) par-dessus : mise à jour sans perte (mémoire, clé, paramètres), message « Ziggy 1.0.0 est installé… ».
- [ ] Ziggy ouvert pendant la mise à jour : l'installateur propose de le fermer.
- [ ] Réinstaller une version plus ancienne : avertissement de « rétrogradation ».
- [ ] Désinstaller en répondant **Non** : `%LOCALAPPDATA%\Ziggy` est conservé ; réinstaller : tout est retrouvé.
- [ ] Désinstaller en répondant **Oui** : le dossier de données disparaît. Raccourcis et entrée de démarrage supprimés.
