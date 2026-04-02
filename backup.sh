#!/bin/bash
# Backup automatique Badge Manager v2 — SQLite
# Usage : ./backup.sh [répertoire_backup] [chemin_bdd]

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKUP_DIR="${1:-$SCRIPT_DIR/backups}"
DB_PATH="${2:-${VIGIK_DB_PATH:-$SCRIPT_DIR/data/badge_manager.db}}"
DATE=$(date +%Y-%m-%d)
KEEP_DAYS=30

if [ ! -f "$DB_PATH" ]; then
    echo "[ERREUR] Base de données introuvable : $DB_PATH"
    exit 1
fi

mkdir -p "$BACKUP_DIR"

# Copie atomique via sqlite3 (safe même si la BDD est en cours d'utilisation)
sqlite3 "$DB_PATH" ".backup '$BACKUP_DIR/badge_manager_$DATE.db'"

if [ $? -eq 0 ]; then
    # Supprimer les backups de plus de 30 jours
    find "$BACKUP_DIR" -name "*.db" -mtime +$KEEP_DAYS -delete
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Backup OK → $BACKUP_DIR/badge_manager_$DATE.db"
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERREUR backup"
    exit 1
fi
