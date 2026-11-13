# Changelog

Toutes les évolutions notables de LinSCP sont listées ici.
All notable changes to LinSCP are documented here.

Format : [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/) · Versions : [SemVer](https://semver.org/lang/fr/)

## [1.0.5] — 2026-11-13

### 🇫🇷 Corrigé
- **FTP en mode actif derrière une box / un NAT** (constaté sur un NAS Synology DSM) : quand le serveur ne peut pas se connecter au PC, il envoie deux réponses (« 425 Can't build data connection » puis « 550 Data connection: No route to host »). LinSCP lisait la seconde comme réponse à la commande suivante, et tout se décalait. Désormais, LinSCP rouvre la connexion en mode passif et garde ce mode pour toute la session (navigation et transferts).
- Même chose pour les serveurs qui répondent d'abord « 150 » puis échouent : LinSCP abandonne le mode actif après 8 s au plus au lieu de rester bloqué 20 s.
- Listage FTP : sur les serveurs qui refusent `OPTS MLST` (Synology DSM), LinSCP n'abandonne plus MLSD au profit de LIST, ce qui donne des dates et des tailles plus fiables.

### 🇫🇷 Ajouté
- Mode diagnostic : `LINSCP_DEBUG=1 linscp` affiche dans le terminal tous les échanges FTP (mot de passe masqué).

### 🇬🇧 Fixed
- **FTP active mode behind a router / NAT** (seen on a Synology DSM NAS): when the server cannot connect to the PC, it sends two replies ("425 Can't build data connection" then "550 Data connection: No route to host"). LinSCP read the second one as the reply to the next command and everything got out of step. LinSCP now reopens the connection in passive mode and keeps that mode for the whole session (browsing and transfers).
- Same for servers that first answer "150" and then fail: LinSCP gives up active mode after at most 8 s instead of hanging for 20 s.
- FTP listing: on servers that reject `OPTS MLST` (Synology DSM), LinSCP no longer drops MLSD for LIST, which gives more reliable dates and sizes.

### 🇬🇧 Added
- Diagnostic mode: `LINSCP_DEBUG=1 linscp` prints every FTP exchange in the terminal (password masked).

## [1.0.3] — 2026-11-13

### 🇫🇷 Ajouté
- Gestionnaire de sites : champ **Notes** libre (plusieurs lignes) sur chaque fiche. Les notes s'affichent au survol d'un site et sont prises en compte par la recherche.

### 🇫🇷 Corrigé
- **FTP derrière une box / un NAT** : quand le serveur ne peut pas ouvrir la connexion de données en mode actif, LinSCP bascule maintenant tout seul en mode passif (et inversement si le mode passif échoue). Cela couvre « 425 Can't build data connection », « 550 Data connection: No route to host » et l'attente sans réponse.
- Gestionnaire de sites, **Port** : on ne pouvait pas taper de port, les chiffres s'ajoutaient après la valeur existante et étaient refusés sans rien afficher. C'est maintenant un champ texte ; vide = port par défaut du protocole, affiché en grisé.
- Gestionnaire de sites, **Enregistrer** : la fiche était bien sauvegardée, mais la liste n'était pas rafraîchie, si bien que l'enregistrement semblait avoir échoué. Le bouton affiche maintenant « Enregistré ✓ ».
- Gestionnaire de sites, **Mémoriser le mot de passe** : la case restait grisée sans trousseau système (`python3-keyring` absent ou aucun service Secret Service). Elle est maintenant toujours active. Sans trousseau, le mot de passe est rangé dans `~/.config/linscp/passwords.json` : fichier lisible par l'utilisateur seul (droits 600), mot de passe masqué mais non chiffré, comme le fait WinSCP par défaut.
- Paquet : `python3-secretstorage` et `gnome-keyring` / `kwalletmanager` ajoutés aux paquets recommandés.

### 🇬🇧 Added
- Site manager: free multi-line **Notes** field on each entry. Notes show in the site tooltip and are matched by the search box.

### 🇬🇧 Fixed
- **FTP behind a router / NAT**: when the server cannot open the data connection in active mode, LinSCP now switches to passive mode automatically (and back to active if passive fails). This covers "425 Can't build data connection", "550 Data connection: No route to host" and the case where nothing answers.
- Site manager, **Port**: a port could not be typed, digits were appended after the existing value and silently rejected. It is now a text field; empty = the protocol's default port, shown as a placeholder.
- Site manager, **Save**: the entry was stored, but the list was never refreshed, so saving looked like it had failed. The button now shows "Saved ✓".
- Site manager, **Remember password**: the box stayed greyed out without a system keyring (`python3-keyring` missing or no Secret Service running). It is now always enabled. Without a keyring, the password is kept in `~/.config/linscp/passwords.json`: file readable by the user only (mode 600), password obfuscated but not encrypted, as WinSCP does by default.
- Package: `python3-secretstorage` and `gnome-keyring` / `kwalletmanager` added to Recommends.

## [1.0.0] — 2026-10-31

Première version publique. / First public release.

### 🇫🇷 Ajouté
- **Protocoles** : SFTP, SCP, FTP, FTPS explicite et FTPS implicite.
- **SCP** compatible avec les serveurs Dropbear/BusyBox sans sous-système SFTP (box Android, routeurs).
- **Interface** double panneau (local + distant) ou panneau simple, au choix (`Ctrl+D`).
- **Sessions en onglets**, avec l'état de connexion indiqué par la couleur de l'icône.
- **Gestionnaire de sites** avec recherche, duplication et dossiers local/distant par défaut.
- Mots de passe rangés dans le **trousseau du système** (GNOME Keyring / KWallet), jamais dans les fichiers de config.
- Authentification par **mot de passe, clé SSH** (avec ou sans phrase de passe) ou **agent SSH**, plus le repli keyboard-interactive.
- **Connexion rapide** dans la barre d'outils, avec prise en charge des URL `sftp://user:mdp@hôte:port/dossier`. `linscp sftp://…` fonctionne aussi en ligne de commande.
- **File de transferts** en parallèle (1 à 6), avec progression, vitesse, temps restant, annulation et relance.
- **Reprise** des transferts interrompus en SFTP et FTP/FTPS, dans les deux sens.
- Choix si le fichier existe déjà : Écraser / Reprendre / Ignorer, avec « appliquer à tous ».
- Envoi et téléchargement de **dossiers entiers**.
- **Glisser-déposer** entre les panneaux et depuis Nemo / Nautilus / Dolphin.
- **Fil d'Ariane cliquable** (`Ctrl+L` pour saisir un chemin), filtre rapide, fichiers cachés (`Ctrl+H`).
- Opérations sur les fichiers : renommer (`F2`), nouveau dossier (`F7`), supprimer (`Suppr`/`F8`), permissions avec chmod récursif, copier le chemin.
- Conservation de la **date de modification** et du bit exécutable.
- Vérification des **clés d'hôte SSH** et des **certificats TLS** : confiance au premier usage, alerte si l'empreinte change. LinSCP a son propre `known_hosts` et ne modifie jamais `~/.ssh`.
- **Reconnexion automatique** quand le serveur coupe une session inactive.
- **Thèmes** clair / sombre / système, icônes entièrement redessinées.
- Interface **français / anglais**, qui suit la langue du système.
- Paquet **.deb** (Linux Mint 21+, Ubuntu 22.04+, Debian 12+) avec entrée de menu et gestionnaire des liens `sftp://` et `scp://`.

### 🇬🇧 Added
- **Protocols**: SFTP, SCP, FTP, explicit and implicit FTPS.
- **SCP** works with Dropbear/BusyBox servers without an SFTP subsystem (Android boxes, routers).
- **Dual-pane** (local + remote) or **single-pane** layout (`Ctrl+D`).
- **Tabbed sessions**, with the connection state shown by the tab icon colour.
- **Site manager** with search, duplicate and default local/remote folders.
- Passwords stored in the **system keyring** (GNOME Keyring / KWallet), never in config files.
- **Password, SSH key** (with or without passphrase) or **SSH agent** authentication, plus keyboard-interactive fallback.
- **Quick connect** bar, with `sftp://user:pass@host:port/dir` URLs. `linscp sftp://…` also works from the command line.
- **Parallel transfer queue** (1–6), with progress, speed, ETA, cancel and retry.
- **Resume** of interrupted transfers over SFTP and FTP/FTPS, in both directions.
- File-exists prompt: Overwrite / Resume / Skip, with "apply to all".
- Whole-**folder** upload and download.
- **Drag and drop** between panes and from Nemo / Nautilus / Dolphin.
- **Clickable breadcrumb** (`Ctrl+L` to type a path), quick filter, hidden files (`Ctrl+H`).
- File operations: rename (`F2`), new folder (`F7`), delete (`Del`/`F8`), permissions with recursive chmod, copy path.
- **Modification time** and executable bit preserved.
- **SSH host-key** and **TLS certificate** checks: trust on first use, warning when the fingerprint changes. LinSCP keeps its own `known_hosts` and never touches `~/.ssh`.
- **Automatic reconnection** when the server drops an idle session.
- Light / dark / system **themes** and a fully redesigned icon set.
- **French / English** interface that follows the system language.
- **.deb** package (Linux Mint 21+, Ubuntu 22.04+, Debian 12+) with a menu entry and a handler for `sftp://` and `scp://` links.

### Limites connues / Known limitations
- Pas de reprise en SCP : le protocole ne la permet pas. / No resume over SCP (protocol limitation).
- FTPS implicite pas encore testé contre un vrai serveur. / Implicit FTPS not yet tested against a real server.
- Le changement de langue et de thème est complet au redémarrage. / Language and theme changes fully apply after a restart.

[1.0.5]: https://github.com/rerem8433/LinSCP/releases/tag/v1.0.5
[1.0.3]: https://github.com/rerem8433/LinSCP/releases/tag/v1.0.3
[1.0.0]: https://github.com/rerem8433/LinSCP/releases/tag/v1.0.0
