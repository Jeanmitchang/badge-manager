# Badge Manager v3.0

Systeme de gestion de badges RFID multi-utilisateurs avec encodage Vigik.

Badge Manager permet de gerer des badges d'acces RFID, de les encoder au format MCT via un executable Windows (Wine), et de les distribuer aux utilisateurs via une interface web moderne.

## Fonctionnalites

### Controle d'acces RBAC (3 niveaux)

| Role | Capacites |
|------|-----------|
| **Superadmin** | Supervision globale, gestion des admins/users/groupes, parametres systeme, journal d'activite, monitoring serveur |
| **Admin** | Gestion de ses utilisateurs et groupes, traitement des demandes, messagerie |
| **User** | Gestion de ses badges, encodage MCT, demandes, messagerie |

### Gestion des badges

- Creation, edition, suppression de badges RFID (UID 8 hex)
- Encodage MCT via Wine + `vigik_loader_cli.exe`
- Telechargement des fichiers MCT generes
- Import/export de badges en JSON
- Stock de badges avec attribution hierarchique (superadmin -> admin -> user)
- Quota de badges par utilisateur, limite d'encodage quotidienne

### Communication et workflow

- Messagerie interne entre roles (user -> admin, admin -> superadmin)
- Systeme de demandes (quota, rallonge MCT, changement de groupe, suppression)
- Notifications en temps reel
- Journal d'activite complet avec export CSV/JSON

### Supervision (superadmin)

- Dashboard avec statistiques globales et heatmap d'activite
- Monitoring systeme (RAM, CPU, disque) avec alertes
- Dispatch d'utilisateurs et groupes entre admins
- Gestion des suspensions et restaurations de comptes

### Technique

- PWA responsive (mobile, tablette, desktop)
- Mode sombre natif
- Pas de framework frontend, pas de build step
- Backend FastAPI asynchrone
- Base de donnees SQLite (zero config)

---

## Prerequis

| Composant | Version | Notes |
|-----------|---------|-------|
| **OS** | Debian 12 / Ubuntu 22.04+ | Autres distros Linux : adapter les commandes apt |
| **Python** | 3.10+ | Avec pip et venv |
| **Wine** | 6.0+ | Pour executer l'encodeur Vigik Windows |
| **SQLite** | 3.35+ | Inclus avec Python |

### Fichiers proprietaires (non inclus)

Ces fichiers doivent etre fournis separement :

| Fichier | Description |
|---------|-------------|
| `vigik_loader_cli.exe` | Executable Windows d'encodage Vigik |
| `cert.txt` | Certificat Vigik pour l'encodage |

---

## Installation

### Option 1 : Script automatique (recommande)

```bash
git clone https://github.com/Jeanmitchang/badge-manager.git
cd badge-manager
sudo ./install.sh
```

Le script effectue automatiquement :
- Installation des dependances systeme (Python, Wine, SQLite)
- Creation du virtualenv Python
- Generation d'un **secret JWT fort** dans `.env`
- Installation du service systemd avec hardening securite
- Programmation du **backup quotidien** (cron, 3h du matin)

Puis completer l'installation :

```bash
# Copier les fichiers proprietaires
sudo cp vigik_loader_cli.exe /opt/badge-manager/
sudo cp cert.txt /opt/badge-manager/

# Initialiser la base de donnees et creer le compte superadmin
cd /opt/badge-manager
sudo -u $(whoami) venv/bin/python3 setup_v2.py

# Demarrer le service
sudo systemctl enable --now badge-manager

# Verifier
curl http://localhost:8766/api/ping
# -> {"status":"ok"}
```

### Option 2 : Docker

```bash
git clone https://github.com/Jeanmitchang/badge-manager.git
cd badge-manager

# Configuration
cp .env.example .env
# Editer .env si necessaire (le secret JWT est auto-genere au demarrage si absent)

# Placer les fichiers proprietaires a la racine du projet
cp /chemin/vers/vigik_loader_cli.exe .
cp /chemin/vers/cert.txt .

# Construire et demarrer
docker compose up -d --build

# Initialiser la base (premiere fois)
docker compose exec badge-manager python3 setup_v2.py

# Verifier
curl http://localhost:8766/api/ping
```

### Option 3 : Installation manuelle

```bash
git clone https://github.com/Jeanmitchang/badge-manager.git
cd badge-manager

# Dependances systeme
sudo dpkg --add-architecture i386
sudo apt update
sudo apt install -y python3 python3-pip python3-venv wine wine32 wine64 sqlite3

# Environnement Python
python3 -m venv venv
source venv/bin/activate
pip install -r requirements_v2.txt

# Configuration
cp .env.example .env
# Editer .env : definir VIGIK_JWT_SECRET
# Generer un secret : python3 -c "import secrets; print(secrets.token_urlsafe(48))"

# Copier vigik_loader_cli.exe et cert.txt dans le repertoire

# Initialisation
python3 setup_v2.py

# Demarrage
python3 server_v2.py
```

---

## Configuration

Toute la configuration se fait via le fichier `.env` (voir `.env.example` pour le template complet).

| Variable | Obligatoire | Default | Description |
|----------|:-----------:|---------|-------------|
| `VIGIK_JWT_SECRET` | **oui** | *(auto-genere)* | Secret JWT. Generer : `python3 -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `VIGIK_PORT` | non | `8766` | Port d'ecoute |
| `VIGIK_HOST` | non | `0.0.0.0` | Adresse d'ecoute |
| `VIGIK_DB_PATH` | non | `./data/badge_manager.db` | Chemin base de donnees |
| `VIGIK_EXE` | non | `./vigik_loader_cli.exe` | Chemin executabe Vigik |
| `VIGIK_CERT` | non | `./cert.txt` | Chemin certificat Vigik |
| `VIGIK_MCT` | non | `./mct_output` | Repertoire sortie MCT |
| `VIGIK_SSL_CERT` | non | *(vide)* | Certificat TLS (vide = HTTP) |
| `VIGIK_SSL_KEY` | non | *(vide)* | Cle privee TLS |
| `VIGIK_CORS_ORIGINS` | non | *(vide)* | Origins CORS autorisees (virgule-separees) |

Les parametres applicatifs (quotas, limites MCT, TTL JWT, seuils d'alerte) sont configurables en temps reel via le dashboard superadmin.

---

## Acces reseau

Badge Manager est **agnostique du reseau**. Il fonctionne avec n'importe quelle solution d'acces :

| Solution | Configuration |
|----------|---------------|
| **Tailscale** | Installer Tailscale, le serveur est accessible via l'IP Tailscale |
| **ZeroTier** | Rejoindre le reseau, accessible via l'IP ZeroTier |
| **WireGuard** | Configurer le tunnel, accessible via l'IP WireGuard |
| **Reverse proxy** | nginx/Caddy/Traefik vers `localhost:8766` |
| **Acces direct** | Ouvrir le port dans le firewall |

---

## SSL/TLS

Trois options possibles :

**Reverse proxy (recommande)** — nginx, Caddy ou Traefik gere le TLS en frontal.

**TLS natif** — Renseigner `VIGIK_SSL_CERT` et `VIGIK_SSL_KEY` dans `.env`.

**Tunnel VPN** — Le chiffrement est assure par le tunnel (Tailscale, WireGuard, etc.).

---

## Maintenance

### Backup et restauration

```bash
# Backup manuel
./backup.sh

# Le backup automatique tourne chaque nuit a 3h (installe par install.sh)

# Restauration
sudo systemctl stop badge-manager
cp backups/badge_manager_YYYY-MM-DD.db data/badge_manager.db
sudo systemctl start badge-manager
```

### Mise a jour

```bash
cd /opt/badge-manager
sudo systemctl stop badge-manager
git pull origin main
venv/bin/pip install -r requirements_v2.txt
sudo systemctl start badge-manager
```

### Procedure d'urgence

En cas de perte du mot de passe superadmin :

```bash
cd /opt/badge-manager
sudo -u <user> venv/bin/python3 emergency_v2.py
```

### Logs

```bash
# Systemd
sudo journalctl -u badge-manager -f

# Docker
docker compose logs -f
```

---

## Securite

### Mesures implementees

- **Hashage bcrypt** des mots de passe (migration transparente depuis SHA256)
- **Rate limiting** login : 5 tentatives / 5 min, lockout 15 min
- **Headers de securite** : CSP, X-Frame-Options DENY, X-Content-Type-Options, Referrer-Policy, Permissions-Policy
- **Echappement XSS** systematique dans le frontend
- **CORS restrictif** : aucune origin par defaut (same-origin uniquement)
- **Secret JWT** auto-genere au demarrage si absent
- **Endpoint /health** protege par auth superadmin
- **Erreurs internes masquees** cote client (logguees cote serveur)
- **Systemd hardening** : NoNewPrivileges, ProtectSystem strict, PrivateTmp
- **Audit complet** : toutes les actions sont tracees dans le journal d'activite

### Recommandations

- Toujours utiliser HTTPS en production
- Definir un `VIGIK_JWT_SECRET` fort et persistant
- Restreindre l'acces reseau (VPN ou firewall)
- Surveiller les alertes systeme via le dashboard superadmin

---

## Architecture

```
badge-manager/
  server_v2.py            # Backend FastAPI — endpoints, auth, taches de fond
  database.py             # Couche SQLite — schema, requetes, transactions
  static_v2/
    index.html            # Shell HTML + CSS (PWA)
    app.js                # Frontend SPA vanilla JS
    manifest.json         # Manifest PWA
    icon.svg              # Icone application
  setup_v2.py             # Initialisation (premiere fois)
  emergency_v2.py         # Procedures d'urgence (SSH)
  backup.sh               # Backup SQLite atomique
  install.sh              # Installation automatique bare-metal
  Dockerfile              # Image Docker (Debian + Wine + Python)
  docker-compose.yml      # Orchestration Docker
  .env.example            # Template de configuration
  requirements_v2.txt     # Dependances Python
  vigik-server-v2@.service  # Template service systemd
```

---

## Licence

Projet prive — usage interne.
