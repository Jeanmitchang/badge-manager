#!/bin/bash
set -e

# ─── Badge Manager v2 — Script d'installation bare-metal ──
# Usage : sudo ./install.sh [répertoire_install]
# Prérequis : Debian/Ubuntu, accès root

INSTALL_DIR="${1:-/opt/badge-manager}"
SERVICE_USER="${SUDO_USER:-$(whoami)}"

echo ""
echo "═══════════════════════════════════════════════════"
echo "   Badge Manager v2 — Installation"
echo "═══════════════════════════════════════════════════"
echo ""
echo "  Répertoire : $INSTALL_DIR"
echo "  Utilisateur : $SERVICE_USER"
echo ""

# ─── Vérification root ───────────────────────────────────
if [ "$EUID" -ne 0 ]; then
    echo "[!] Ce script doit être exécuté avec sudo."
    echo "    Usage : sudo ./install.sh"
    exit 1
fi

# ─── Dépendances système ─────────────────────────────────
echo "[1/7] Installation des dépendances système..."
dpkg --add-architecture i386
apt-get update -qq
apt-get install -y -qq --no-install-recommends \
    python3 python3-pip python3-venv \
    wine wine32 wine64 \
    sqlite3 \
    ca-certificates > /dev/null
echo "  [OK] Dépendances installées"

# ─── Répertoire d'installation ────────────────────────────
echo "[2/7] Création du répertoire d'installation..."
mkdir -p "$INSTALL_DIR"
cp server_v2.py database.py setup_v2.py emergency_v2.py backup.sh "$INSTALL_DIR/"
cp requirements_v2.txt "$INSTALL_DIR/"
cp -r static_v2 "$INSTALL_DIR/"
chmod +x "$INSTALL_DIR/backup.sh"
echo "  [OK] Fichiers copiés"

# ─── Répertoires de données ──────────────────────────────
echo "[3/7] Création des répertoires de données..."
mkdir -p "$INSTALL_DIR/data" "$INSTALL_DIR/mct_output" "$INSTALL_DIR/backups"
echo "  [OK] Répertoires créés"

# ─── Environnement Python ────────────────────────────────
echo "[4/7] Configuration de l'environnement Python..."
python3 -m venv "$INSTALL_DIR/venv"
"$INSTALL_DIR/venv/bin/pip" install --quiet --no-cache-dir -r "$INSTALL_DIR/requirements_v2.txt"
echo "  [OK] Virtualenv prêt"

# ─── Configuration .env ──────────────────────────────────
echo "[5/7] Configuration..."
if [ ! -f "$INSTALL_DIR/.env" ]; then
    JWT_SECRET=$(python3 -c "import secrets; print(secrets.token_urlsafe(48))")
    cat > "$INSTALL_DIR/.env" << EOF
VIGIK_JWT_SECRET=$JWT_SECRET
VIGIK_HOST=0.0.0.0
VIGIK_PORT=8766
VIGIK_EXE=$INSTALL_DIR/vigik_loader_cli.exe
VIGIK_CERT=$INSTALL_DIR/cert.txt
VIGIK_MCT=$INSTALL_DIR/mct_output
VIGIK_DB_PATH=$INSTALL_DIR/data/badge_manager.db
VIGIK_SSL_CERT=
VIGIK_SSL_KEY=
VIGIK_CORS_ORIGINS=
EOF
    chmod 600 "$INSTALL_DIR/.env"
    echo "  [OK] .env créé avec un secret JWT fort"
else
    echo "  [OK] .env existant conservé"
fi

# ─── Service systemd ─────────────────────────────────────
echo "[6/7] Installation du service systemd..."
cat > /etc/systemd/system/badge-manager.service << EOF
[Unit]
Description=Badge Manager v2 Server
After=network.target

[Service]
Type=simple
User=$SERVICE_USER
WorkingDirectory=$INSTALL_DIR
EnvironmentFile=$INSTALL_DIR/.env
ExecStart=$INSTALL_DIR/venv/bin/python3 $INSTALL_DIR/server_v2.py
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=badge-manager-v2
NoNewPrivileges=yes
ProtectSystem=strict
ReadWritePaths=$INSTALL_DIR/data $INSTALL_DIR/mct_output $INSTALL_DIR/backups
ProtectHome=yes
PrivateTmp=yes

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
echo "  [OK] Service badge-manager installé"

# ─── Permissions ─────────────────────────────────────────
echo "[7/7] Application des permissions..."
chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"
echo "  [OK] Permissions appliquées"

# ─── Cron backup ─────────────────────────────────────────
CRON_LINE="0 3 * * * $INSTALL_DIR/backup.sh >> $INSTALL_DIR/backups/backup.log 2>&1"
(crontab -u "$SERVICE_USER" -l 2>/dev/null | grep -v "badge-manager"; echo "$CRON_LINE") | crontab -u "$SERVICE_USER" -
echo "  [OK] Backup quotidien programmé (3h du matin)"

echo ""
echo "═══════════════════════════════════════════════════"
echo "   Installation terminée !"
echo "═══════════════════════════════════════════════════"
echo ""
echo "  Prochaines étapes :"
echo ""
echo "  1. Copier les fichiers requis :"
echo "     cp vigik_loader_cli.exe $INSTALL_DIR/"
echo "     cp cert.txt $INSTALL_DIR/"
echo ""
echo "  2. (Optionnel) Configurer SSL dans $INSTALL_DIR/.env"
echo ""
echo "  3. Initialiser la base de données :"
echo "     cd $INSTALL_DIR"
echo "     sudo -u $SERVICE_USER venv/bin/python3 setup_v2.py"
echo ""
echo "  4. Démarrer le service :"
echo "     sudo systemctl enable --now badge-manager"
echo ""
echo "  5. Vérifier le statut :"
echo "     sudo systemctl status badge-manager"
echo "     curl http://localhost:8766/api/ping"
echo ""
