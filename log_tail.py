#!/usr/bin/env python3
"""
log_tail.py — Lecteur de logs Badge Manager v2

Usage :
  python3 log_tail.py                    # 50 derniers logs
  python3 log_tail.py -n 200             # N derniers logs
  python3 log_tail.py -f                 # suivi temps réel (Ctrl+C pour quitter)
  python3 log_tail.py -e connexion       # filtrer par type d'événement
  python3 log_tail.py -u jean            # filtrer par utilisateur
  python3 log_tail.py -r admin           # filtrer par rôle (user|admin|superadmin)
  python3 log_tail.py --no-watchdog      # masquer les entrées watchdog
  python3 log_tail.py -f -e mct -u jean  # combinaisons
"""

import sqlite3, json, time, argparse, sys
from pathlib import Path
from datetime import datetime

DB_PATH = Path(__file__).parent / "data" / "badge_manager.db"

# ─── Couleurs ANSI ────────────────────────────────────────────────────────────

USE_COLOR = sys.stdout.isatty()

def ansi(code): return f"\033[{code}m" if USE_COLOR else ""

RESET  = ansi(0);  BOLD   = ansi(1);  DIM    = ansi(2)
CYAN   = ansi(96); GREEN  = ansi(92); YELLOW = ansi(93)
RED    = ansi(91); BLUE   = ansi(94); PURPLE = ansi(95)
WHITE  = ansi(97); GRAY   = ansi(90); TEAL   = ansi(36)

def col(color, text):
    return f"{color}{text}{RESET}"

# ─── Catégorisation des événements ────────────────────────────────────────────

EVENT_MAP = {
    # (couleur, icône)
    "connexion_ok":          (GREEN,  "✓"),
    "connexion_echec":       (RED,    "✗"),
    "user_created":          (CYAN,   "+"),
    "user_deleted":          (YELLOW, "~"),
    "user_deleted_soft":     (YELLOW, "~"),
    "user_deleted_final":    (RED,    "✗"),
    "user_blocked":          (YELLOW, "⛔"),
    "user_restored":         (GREEN,  "↺"),
    "password_changed":      (BLUE,   "🔑"),
    "password_reset":        (BLUE,   "🔑"),
    "mct_generated":         (CYAN,   "⚡"),
    "mct_cleanup":           (GRAY,   "🧹"),
    "badge_created":         (CYAN,   "🏷"),
    "badge_imported":        (CYAN,   "⬆"),
    "group_created":         (PURPLE, "◉"),
    "group_deleted":         (YELLOW, "✗"),
    "stock_badge_created":   (CYAN,   "📦"),
    "stock_badge_attributed":(PURPLE, "→"),
    "dispatch_user_to_admin":(PURPLE, "↗"),
    "dispatch_user_to_group":(PURPLE, "↗"),
    "dispatch_group_to_admin":(PURPLE,"↗"),
    "demande_submitted":     (YELLOW, "📨"),
    "watchdog_ok":           (GRAY,   "·"),
    "system_alert":          (RED,    "⚠"),
}

def event_style(event):
    for k, (color, icon) in EVENT_MAP.items():
        if k in event:
            return color, icon
    return WHITE, "?"

ROLE_COLORS = {"superadmin": PURPLE, "admin": CYAN, "user": GREEN}
DEVICE_ICONS = {"mobile": "📱", "tablet": "📟", "desktop": "🖥", "": ""}

# ─── Formatage d'une ligne ────────────────────────────────────────────────────

def fmt_row(row):
    ts      = (row["created_at"] or "")[:19].replace("T", " ")
    event   = row["event"] or ""
    user    = row["user_login"] or ""
    role    = row["role"] or ""
    ip      = row["ip"] or ""
    device  = DEVICE_ICONS.get(row["device"] or "", "")

    try:
        det = json.loads(row["detail"] or "{}")
        detail_parts = []
        for k, v in det.items():
            if v not in (None, "", {}, []):
                detail_parts.append(f"{k}={v}")
        detail_str = "  ".join(detail_parts)[:70]
    except Exception:
        detail_str = ""

    ev_color, ev_icon = event_style(event)
    role_color = ROLE_COLORS.get(role, GRAY)

    parts = [
        col(GRAY,      f"{ts:<19}"),
        col(ev_color,  f"{ev_icon} {event:<32}"),
        col(WHITE,     f"{user:<18}") if user else " " * 18,
    ]
    if role:
        parts.append(col(role_color, f"[{role:<10}]"))
    if ip and ip != "unknown":
        parts.append(col(GRAY, f"{ip:<15}"))
    if device:
        parts.append(device)
    if detail_str:
        parts.append(col(DIM, detail_str))

    return "  ".join(p for p in parts if p and p.strip())

# ─── Requêtes DB ──────────────────────────────────────────────────────────────

def db_connect(db_path):
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=3000")
    return conn

def fetch_logs(conn, n=50, event_f=None, user_f=None, role_f=None,
               since_rowid=None, no_watchdog=False):
    q = "SELECT rowid, * FROM activity_log WHERE 1=1"
    p = []
    if event_f:
        q += " AND event LIKE ?"; p.append(f"%{event_f}%")
    if user_f:
        q += " AND user_login LIKE ?"; p.append(f"%{user_f}%")
    if role_f:
        q += " AND role=?"; p.append(role_f)
    if no_watchdog:
        q += " AND event NOT LIKE '%watchdog%'"
    if since_rowid is not None:
        q += " AND rowid > ?"; p.append(since_rowid)
        q += " ORDER BY rowid ASC"
    else:
        q += f" ORDER BY rowid DESC LIMIT {n}"
    rows = conn.execute(q, p).fetchall()
    return rows

def get_last_rowid(conn):
    r = conn.execute("SELECT MAX(rowid) FROM activity_log").fetchone()
    return r[0] or 0

# ─── Affichage en-tête ────────────────────────────────────────────────────────

def print_header(args):
    print(col(BOLD + CYAN, "╔══════════════════════════════════════════════════╗"))
    print(col(BOLD + CYAN, "║       Badge Manager — Journal d'activité         ║"))
    print(col(BOLD + CYAN, "╚══════════════════════════════════════════════════╝"))
    print(col(GRAY, f"  Base    : {args.db}"))
    filters = []
    if args.event: filters.append(f"event={args.event}")
    if args.user:  filters.append(f"user={args.user}")
    if args.role:  filters.append(f"role={args.role}")
    if args.no_watchdog: filters.append("no-watchdog")
    print(col(GRAY, f"  Filtres : {', '.join(filters) or '—'}"))
    if args.follow:
        print(col(YELLOW, "  Mode    : suivi temps réel — Ctrl+C pour quitter"))
    print(col(GRAY, "  " + "─" * 80))
    print(col(GRAY,
        f"  {'HORODATAGE':<19}  {'ÉVÉNEMENT':<34} {'UTILISATEUR':<18}  {'RÔLE':<12}  IP"))
    print(col(GRAY, "  " + "─" * 80))

# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Badge Manager — lecteur de logs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument("-n", "--lines",       type=int, default=50,
                        help="Nombre de logs initiaux (défaut : 50)")
    parser.add_argument("-f", "--follow",      action="store_true",
                        help="Mode suivi temps réel")
    parser.add_argument("-e", "--event",       type=str, default=None,
                        help="Filtrer par type d'événement (partiel)")
    parser.add_argument("-u", "--user",        type=str, default=None,
                        help="Filtrer par login utilisateur (partiel)")
    parser.add_argument("-r", "--role",        type=str, default=None,
                        choices=["user","admin","superadmin"],
                        help="Filtrer par rôle")
    parser.add_argument("--no-watchdog",       action="store_true",
                        help="Masquer les entrées watchdog_ok")
    parser.add_argument("--db",                type=str, default=str(DB_PATH),
                        help="Chemin de la base SQLite")
    parser.add_argument("--interval",          type=float, default=2.0,
                        help="Intervalle de polling en mode -f (défaut : 2s)")
    args = parser.parse_args()

    if not Path(args.db).exists():
        print(col(RED, f"✗ Base introuvable : {args.db}"))
        sys.exit(1)

    print_header(args)

    conn = db_connect(args.db)
    rows = fetch_logs(conn, n=args.lines,
                      event_f=args.event, user_f=args.user, role_f=args.role,
                      no_watchdog=args.no_watchdog)
    rows = list(reversed(rows))  # ordre chronologique

    for row in rows:
        print("  " + fmt_row(row))

    if not args.follow:
        print(col(GRAY, f"\n  {len(rows)} événement(s) — fin."))
        conn.close()
        return

    # ── Mode suivi ────────────────────────────────────────────────────────────
    last_rowid = get_last_rowid(conn)
    conn.close()

    print(col(GRAY, f"  En attente de nouveaux événements…"))
    try:
        while True:
            time.sleep(args.interval)
            try:
                conn = db_connect(args.db)
                new_rows = fetch_logs(conn,
                                      event_f=args.event, user_f=args.user, role_f=args.role,
                                      since_rowid=last_rowid, no_watchdog=args.no_watchdog)
                if new_rows:
                    last_rowid = max(r["rowid"] for r in new_rows)
                    for row in new_rows:
                        print("  " + fmt_row(row))
                    sys.stdout.flush()
                conn.close()
            except Exception as e:
                print(col(RED, f"  Erreur : {e}"))
    except KeyboardInterrupt:
        print(col(GRAY, "\n  Fin du suivi."))


if __name__ == "__main__":
    main()
