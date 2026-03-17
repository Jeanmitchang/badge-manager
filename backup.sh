#!/bin/bash
# Backup automatique Badge Manager v2 — SQLite

BACKUP_DIR="/home/budgie/Documents/Vigik_v2/backups"
DB_PATH="/home/budgie/Documents/Vigik_v2/data/badge_manager.db"
DATE=$(date +%Y-%m-%d)
KEEP_DAYS=30

mkdir -p "$BACKUP_DIR"

# Copie atomique via sqlite3 (safe même si la BDD est en cours d'utilisation)
sqlite3 "$DB_PATH" ".backup '$BACKUP_DIR/badge_manager_$DATE.db'"

# Supprimer les backups de plus de 30 jours
find "$BACKUP_DIR" -name "*.db" -mtime +$KEEP_DAYS -delete

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Backup OK → badge_manager_$DATE.db"
