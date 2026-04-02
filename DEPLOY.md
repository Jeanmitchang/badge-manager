# Badge Manager v2 — Guide de deploiement

## Prerequis

| Composant | Version min. | Notes |
|-----------|-------------|-------|
| OS | Debian 12 / Ubuntu 22.04+ | Autres distros : adapter les commandes apt |
| Python | 3.10+ | Avec pip et venv |
| Wine | 6.0+ | Pour executer `vigik_loader_cli.exe` |
| SQLite | 3.35+ | Inclus avec Python |

### Fichiers proprietaires requis (non inclus dans le repo)

| Fichier | Description |
|---------|-------------|
| `vigik_loader_cli.exe` | Executable Windows d'encodage Vigik |
| `cert.txt` | Certificat Vigik pour l'encodage des badges |

Ces fichiers doivent etre fournis separement et copies dans le repertoire d'installation.

---

## Option A : Installation automatique (bare-metal)

```bash
# Cloner le repo
git clone <url-du-repo> badge-manager
cd badge-manager

# Lancer l'installation (necessite sudo)
sudo ./install.sh

# Copier les fichiers proprietaires
sudo cp vigik_loader_cli.exe /opt/badge-manager/
sudo cp cert.txt /opt/badge-manager/
sudo chown badge-user:badge-user /opt/badge-manager/vigik_loader_cli.exe /opt/badge-manager/cert.txt

# Initialiser la base de donnees
cd /opt/badge-manager
sudo -u <user> venv/bin/python3 setup_v2.py

# Demarrer
sudo systemctl enable --now badge-manager
```

Le script `install.sh` effectue automatiquement :
- Installation des dependances systeme (Python, Wine, SQLite)
- Creation du virtualenv et installation des paquets Python
- Generation d'un secret JWT fort dans `.env`
- Installation du service systemd avec hardening
- Programmation du backup quotidien (cron, 3h du matin)

### Repertoire cible par defaut

```
/opt/badge-manager/
  server_v2.py          # Serveur FastAPI
  database.py           # Couche base de donnees
  setup_v2.py           # Initialisation
  emergency_v2.py       # Procedures d'urgence (SSH uniquement)
  backup.sh             # Script de backup SQLite
  .env                  # Configuration (genere par install.sh)
  requirements_v2.txt   # Dependances Python
  venv/                 # Environnement Python isole
  static_v2/            # Frontend PWA
  data/                 # Base de donnees SQLite
  mct_output/           # Fichiers MCT generes (temporaires)
  backups/              # Backups quotidiens de la BDD
  vigik_loader_cli.exe  # (a copier manuellement)
  cert.txt              # (a copier manuellement)
```

---

## Option B : Docker

```bash
# Cloner le repo
git clone <url-du-repo> badge-manager
cd badge-manager

# Preparer les fichiers proprietaires et la config
cp .env.example .env
# Editer .env : definir VIGIK_JWT_SECRET (ou laisser vide pour auto-generation)

# Placer les fichiers proprietaires a la racine
cp /chemin/vers/vigik_loader_cli.exe .
cp /chemin/vers/cert.txt .

# Construire et demarrer
docker compose up -d --build

# Initialiser la base de donnees (premiere fois uniquement)
docker compose exec badge-manager python3 setup_v2.py
```

### Volumes persistants

| Volume | Contenu |
|--------|---------|
| `./data` | Base de donnees SQLite |
| `./mct_output` | Fichiers MCT generes |
| `./backups` | Backups de la BDD |

### Backup dans Docker

```bash
# Backup manuel
docker compose exec badge-manager ./backup.sh

# Ou depuis l'hote (si le volume est monte)
sqlite3 ./data/badge_manager.db ".backup ./backups/badge_manager_$(date +%Y-%m-%d).db"
```

---

## Configuration (.env)

| Variable | Obligatoire | Default | Description |
|----------|:-----------:|---------|-------------|
| `VIGIK_JWT_SECRET` | **oui** | (auto-genere) | Secret de signature JWT. Generer avec : `python3 -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `VIGIK_PORT` | non | `8766` | Port d'ecoute |
| `VIGIK_HOST` | non | `0.0.0.0` | Adresse d'ecoute |
| `VIGIK_EXE` | non | `./vigik_loader_cli.exe` | Chemin vers l'executable Vigik |
| `VIGIK_CERT` | non | `./cert.txt` | Chemin vers le certificat Vigik |
| `VIGIK_MCT` | non | `./mct_output` | Repertoire de sortie MCT |
| `VIGIK_DB_PATH` | non | `./data/badge_manager.db` | Chemin vers la BDD SQLite |
| `VIGIK_SSL_CERT` | non | (vide) | Chemin vers le certificat TLS |
| `VIGIK_SSL_KEY` | non | (vide) | Chemin vers la cle privee TLS |
| `VIGIK_CORS_ORIGINS` | non | (vide) | Origins CORS autorisees (comma-separated) |

---

## SSL/TLS

### Option 1 : Reverse proxy (recommande)

Utiliser nginx, Caddy ou Traefik en frontal. Le serveur Badge Manager tourne en HTTP derriere le proxy.

Exemple nginx :

```nginx
server {
    listen 443 ssl;
    server_name badges.mon-domaine.com;

    ssl_certificate     /etc/letsencrypt/live/badges.mon-domaine.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/badges.mon-domaine.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8766;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### Option 2 : TLS natif

```bash
# Dans .env :
VIGIK_SSL_CERT=/chemin/vers/cert.pem
VIGIK_SSL_KEY=/chemin/vers/key.pem
```

### Option 3 : Tunnel VPN

Compatible avec tout tunnel VPN (Tailscale, ZeroTier, WireGuard, OpenVPN...).
Le serveur ecoute sur `0.0.0.0` par defaut et accepte les connexions de n'importe quelle interface reseau.

---

## Acces reseau / VPN

Badge Manager est agnostique du reseau. Il ecoute sur le port configure et n'a aucune dependance a un fournisseur VPN specifique.

| Solution | Configuration cote Badge Manager |
|----------|----------------------------------|
| **Tailscale** | Aucune. Installer Tailscale sur la machine, le serveur est accessible via l'IP Tailscale. |
| **ZeroTier** | Aucune. Rejoindre le reseau ZeroTier, le serveur est accessible via l'IP ZeroTier. |
| **WireGuard** | Aucune. Configurer l'interface WireGuard, le serveur est accessible via l'IP du tunnel. |
| **Acces direct** | Ouvrir le port 8766 (ou le port configure) dans le firewall. |
| **Reverse proxy** | Configurer nginx/Caddy/Traefik pour proxifier vers `localhost:8766`. |

---

## Maintenance

### Backup et restauration

```bash
# Backup manuel
./backup.sh

# Restauration
systemctl stop badge-manager
cp backups/badge_manager_2026-04-01.db data/badge_manager.db
systemctl start badge-manager
```

### Mise a jour

```bash
cd /opt/badge-manager
systemctl stop badge-manager
git pull origin main
venv/bin/pip install -r requirements_v2.txt
systemctl start badge-manager
```

### Procedures d'urgence

En cas de perte du mot de passe superadmin ou de compte bloque :

```bash
# Via SSH sur le serveur
cd /opt/badge-manager
sudo -u <user> venv/bin/python3 emergency_v2.py
```

Options disponibles :
1. Reinitialiser le mot de passe superadmin
2. Debloquer le compte
3. Generer un token temporaire (1h)

### Logs

```bash
# Logs systemd
sudo journalctl -u badge-manager -f

# Logs Docker
docker compose logs -f badge-manager

# Export des logs applicatifs (via l'API, auth superadmin requise)
curl -H "Authorization: Bearer <token>" https://serveur:8766/api/logs/export?format=csv -o logs.csv
```

---

## Securite

### Mesures implementees

- **Hashage bcrypt** des mots de passe (avec migration transparente depuis SHA256)
- **Rate limiting** sur le login (5 tentatives / 5 min, lockout 15 min)
- **Headers de securite** : CSP, X-Frame-Options DENY, X-Content-Type-Options nosniff
- **Echappement XSS** systematique dans le frontend
- **CORS restrictif** : pas d'origin autorisee par defaut (same-origin)
- **JWT auto-genere** si absent au demarrage
- **Endpoint /health protege** par authentification superadmin
- **Erreurs Wine masquees** cote client (logguees cote serveur)
- **Systemd hardening** : NoNewPrivileges, ProtectSystem, PrivateTmp

### Recommandations supplementaires

- Toujours utiliser HTTPS en production (TLS natif ou reverse proxy)
- Definir un `VIGIK_JWT_SECRET` fort et persistant dans `.env`
- Restreindre l'acces reseau au serveur (firewall, VPN)
- Surveiller les logs d'activite via le dashboard superadmin
- Effectuer des backups reguliers (cron configure par `install.sh`)
