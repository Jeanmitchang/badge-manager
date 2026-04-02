#!/usr/bin/env python3
"""
database.py — Badge Manager v2
Modèle SQLite avec toutes les tables, contraintes et helpers.
"""

import sqlite3
import uuid
import hashlib
import hmac as _hmac
import os
import time
import json as _json
import bcrypt
from contextvars import ContextVar
from datetime import datetime, timedelta
from pathlib import Path
from contextlib import contextmanager

# Contexte de la requête courante — peuplé par le middleware HTTP
_ctx_ua: ContextVar[str] = ContextVar('ctx_ua', default='')
_ctx_device: ContextVar[str] = ContextVar('ctx_device', default='')

DB_PATH = Path(os.environ.get("VIGIK_DB_PATH", str(Path(__file__).parent / "data" / "badge_manager.db")))


def get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


@contextmanager
def db():
    conn = get_conn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ─── Schéma ───────────────────────────────────────────────────────────────────

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id              TEXT PRIMARY KEY,
    login           TEXT UNIQUE NOT NULL,
    pwd_hash        TEXT NOT NULL,
    role            TEXT NOT NULL CHECK(role IN ('superadmin','admin','user')),
    admin_id        TEXT REFERENCES users(id),
    group_id        TEXT REFERENCES groups(id),
    badge_quota     INTEGER NOT NULL DEFAULT 5,
    jwt_ttl_hours   INTEGER NOT NULL DEFAULT 24,
    is_active       INTEGER NOT NULL DEFAULT 1,
    is_deleted      INTEGER NOT NULL DEFAULT 0,
    deleted_by      TEXT,
    must_change_pwd INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS groups (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    color       TEXT NOT NULL DEFAULT '#8b5cf6',
    admin_id    TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS badges (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    uid           TEXT NOT NULL,
    icon          TEXT NOT NULL DEFAULT '🔑',
    owner_id      TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    is_stock      INTEGER NOT NULL DEFAULT 0,
    stock_status  TEXT NOT NULL DEFAULT 'owned'
                  CHECK(stock_status IN ('owned','available','attributed')),
    attributed_to TEXT REFERENCES users(id),
    last_encoded  TEXT,
    created_at    TEXT NOT NULL,
    UNIQUE(owner_id, uid)
);

CREATE TABLE IF NOT EXISTS mct_history (
    id         TEXT PRIMARY KEY,
    badge_id   TEXT NOT NULL REFERENCES badges(id) ON DELETE CASCADE,
    user_id    TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    mct_path   TEXT NOT NULL,
    mct_size   INTEGER,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS requests (
    id           TEXT PRIMARY KEY,
    type         TEXT NOT NULL CHECK(type IN ('badge_quota','mct_rallonge','group_change','delete_user')),
    status       TEXT NOT NULL DEFAULT 'pending'
                 CHECK(status IN ('pending','approved','refused','cancelled')),
    requester_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    target_id    TEXT,
    group_from   TEXT,
    group_to     TEXT,
    motif        TEXT,
    handled_by   TEXT REFERENCES users(id),
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id         TEXT PRIMARY KEY,
    from_id    TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    to_id      TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    content    TEXT NOT NULL CHECK(length(content) <= 280),
    is_read    INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS notifications (
    id         TEXT PRIMARY KEY,
    user_id    TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type       TEXT NOT NULL,
    title      TEXT NOT NULL,
    body       TEXT,
    is_read    INTEGER NOT NULL DEFAULT 0,
    ref_id     TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS activity_log (
    id         TEXT PRIMARY KEY,
    event      TEXT NOT NULL,
    user_id    TEXT,
    user_login TEXT,
    role       TEXT,
    group_id   TEXT,
    admin_id   TEXT,
    ip         TEXT,
    user_agent TEXT,
    device     TEXT,
    detail     TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS config (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_badges_owner ON badges(owner_id);
CREATE INDEX IF NOT EXISTS idx_mct_user     ON mct_history(user_id);
CREATE INDEX IF NOT EXISTS idx_mct_created  ON mct_history(created_at);
CREATE INDEX IF NOT EXISTS idx_req_status   ON requests(status);
CREATE INDEX IF NOT EXISTS idx_msg_to       ON messages(to_id, is_read);
CREATE INDEX IF NOT EXISTS idx_notif_user   ON notifications(user_id, is_read);
CREATE INDEX IF NOT EXISTS idx_log_event    ON activity_log(event);
CREATE INDEX IF NOT EXISTS idx_log_user     ON activity_log(user_id);
CREATE INDEX IF NOT EXISTS idx_groups_admin ON groups(admin_id);
"""


def init_db():
    with db() as conn:
        conn.executescript(SCHEMA)


# ─── Utils ────────────────────────────────────────────────────────────────────

def new_id() -> str:
    return str(uuid.uuid4())

def now() -> str:
    return datetime.utcnow().isoformat()

def hash_pwd(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def _is_legacy_sha256(stored_hash: str) -> bool:
    """Détecte un ancien hash SHA256 (64 hex chars) vs bcrypt ($2b$...)."""
    return len(stored_hash) == 64 and not stored_hash.startswith("$")

def check_pwd(password: str, stored_hash: str) -> bool:
    if _is_legacy_sha256(stored_hash):
        # Migration transparente : vérifie avec SHA256, puis upgrade vers bcrypt
        legacy = hashlib.sha256(password.encode("utf-8")).hexdigest()
        if _hmac.compare_digest(legacy, stored_hash):
            return True
        return False
    return bcrypt.checkpw(password.encode("utf-8"), stored_hash.encode("utf-8"))

def validate_pwd(password: str) -> str | None:
    if len(password) < 6:
        return "Mot de passe trop court (min 6 caractères)"
    if len(password) > 14:
        return "Mot de passe trop long (max 14 caractères)"
    return None


# ─── Config ───────────────────────────────────────────────────────────────────

def get_config(key: str, default: str = None) -> str | None:
    with db() as conn:
        row = conn.execute("SELECT value FROM config WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

def set_config(key: str, value: str):
    with db() as conn:
        conn.execute("""
            INSERT INTO config (key, value, updated_at) VALUES (?,?,?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
        """, (key, str(value), now()))

def init_default_config():
    defaults = {
        "badge_quota_default": "5",
        "mct_daily_limit": "5",
        "jwt_ttl_hours_default": "24",
        "vigik_duration_hours": "84",
        "disk_alert_threshold_pct": "80",
        "admin_group_limit_default": "0",
    }
    for k, v in defaults.items():
        if get_config(k) is None:
            set_config(k, v)


# ─── Users ────────────────────────────────────────────────────────────────────

def create_user(login: str, password: str, role: str,
                admin_id: str = None, group_id: str = None,
                badge_quota: int = 5, jwt_ttl_hours: int = 24,
                must_change_pwd: int = 1) -> dict:
    uid = new_id()
    ts = now()
    with db() as conn:
        conn.execute("""
            INSERT INTO users (id,login,pwd_hash,role,admin_id,group_id,
                badge_quota,jwt_ttl_hours,is_active,is_deleted,must_change_pwd,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,1,0,?,?,?)
        """, (uid, login, hash_pwd(password), role, admin_id, group_id,
              badge_quota, jwt_ttl_hours, must_change_pwd, ts, ts))
    return get_user_by_id(uid)

def get_user_by_login(login: str) -> dict | None:
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE login=? AND is_deleted=0", (login,)
        ).fetchone()
        return dict(row) if row else None

def get_user_by_id(uid: str) -> dict | None:
    with db() as conn:
        row = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        return dict(row) if row else None

def get_users_by_admin(admin_id: str, include_deleted: bool = False) -> list:
    with db() as conn:
        q = "SELECT * FROM users WHERE admin_id=? AND role='user'"
        if not include_deleted:
            q += " AND is_deleted=0"
        return [dict(r) for r in conn.execute(q + " ORDER BY login", (admin_id,)).fetchall()]

def get_all_users(include_deleted: bool = False) -> list:
    with db() as conn:
        q = "SELECT * FROM users WHERE role='user'" + ("" if include_deleted else " AND is_deleted=0")
        return [dict(r) for r in conn.execute(q + " ORDER BY login").fetchall()]

def get_all_admins() -> list:
    with db() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM users WHERE role='admin' AND is_deleted=0 ORDER BY login"
        ).fetchall()]

def get_superadmin() -> dict | None:
    with db() as conn:
        row = conn.execute("SELECT * FROM users WHERE role='superadmin' LIMIT 1").fetchone()
        return dict(row) if row else None

def update_user(uid: str, **kwargs) -> dict | None:
    allowed = {"login","pwd_hash","group_id","badge_quota","jwt_ttl_hours",
               "is_active","is_deleted","deleted_by","must_change_pwd","admin_id"}
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return get_user_by_id(uid)
    fields["updated_at"] = now()
    sets = ", ".join(f"{k}=?" for k in fields)
    vals = list(fields.values()) + [uid]
    with db() as conn:
        conn.execute(f"UPDATE users SET {sets} WHERE id=?", vals)
    return get_user_by_id(uid)

def soft_delete_user(uid: str, deleted_by: str):
    with db() as conn:
        conn.execute("""
            UPDATE users SET is_deleted=1, is_active=0, deleted_by=?, updated_at=?
            WHERE id=?
        """, (deleted_by, now(), uid))

def restore_user(uid: str):
    with db() as conn:
        conn.execute("""
            UPDATE users SET is_deleted=0, is_active=1, deleted_by=NULL, updated_at=?
            WHERE id=?
        """, (now(), uid))

def get_suspended_users() -> list:
    """Users soft-deleted en attente de décision superadmin."""
    with db() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM users WHERE is_deleted=1 ORDER BY updated_at DESC"
        ).fetchall()]


# ─── Groups ───────────────────────────────────────────────────────────────────

def create_group(name: str, admin_id: str, color: str = "#8b5cf6") -> dict:
    gid = new_id()
    with db() as conn:
        conn.execute(
            "INSERT INTO groups (id,name,color,admin_id,created_at) VALUES (?,?,?,?,?)",
            (gid, name, color, admin_id, now())
        )
    return get_group(gid)

def get_group(gid: str) -> dict | None:
    with db() as conn:
        row = conn.execute("SELECT * FROM groups WHERE id=?", (gid,)).fetchone()
        return dict(row) if row else None

def get_groups_by_admin(admin_id: str) -> list:
    with db() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM groups WHERE admin_id=? ORDER BY name", (admin_id,)
        ).fetchall()]

def get_all_groups() -> list:
    with db() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM groups ORDER BY name").fetchall()]

def count_admin_groups(admin_id: str) -> int:
    with db() as conn:
        return conn.execute(
            "SELECT COUNT(*) FROM groups WHERE admin_id=?", (admin_id,)
        ).fetchone()[0]

def delete_group(gid: str):
    with db() as conn:
        conn.execute("""
            UPDATE users SET group_id=NULL, is_active=0, updated_at=?
            WHERE group_id=? AND is_deleted=0
        """, (now(), gid))
        conn.execute("DELETE FROM groups WHERE id=?", (gid,))

def update_group(gid: str, **kwargs) -> dict | None:
    allowed = {"name","color"}
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return get_group(gid)
    sets = ", ".join(f"{k}=?" for k in fields)
    vals = list(fields.values()) + [gid]
    with db() as conn:
        conn.execute(f"UPDATE groups SET {sets} WHERE id=?", vals)
    return get_group(gid)


# ─── Badges ───────────────────────────────────────────────────────────────────

def create_badge(name: str, uid: str, icon: str,
                 owner_id: str, is_stock: bool = False) -> dict:
    bid = new_id()
    status = "available" if is_stock else "owned"
    with db() as conn:
        conn.execute("""
            INSERT INTO badges (id,name,uid,icon,owner_id,is_stock,stock_status,created_at)
            VALUES (?,?,?,?,?,?,?,?)
        """, (bid, name, uid.upper(), icon, owner_id, 1 if is_stock else 0, status, now()))
    return get_badge(bid)

def get_badge(bid: str) -> dict | None:
    with db() as conn:
        row = conn.execute("SELECT * FROM badges WHERE id=?", (bid,)).fetchone()
        return dict(row) if row else None

def get_badges_by_owner(owner_id: str) -> list:
    with db() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM badges WHERE owner_id=? AND is_stock=0 ORDER BY created_at",
            (owner_id,)
        ).fetchall()]

def get_stock_badges() -> list:
    with db() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM badges WHERE is_stock=1 ORDER BY created_at"
        ).fetchall()]

def update_badge(bid: str, **kwargs) -> dict | None:
    allowed = {"name","uid","icon","last_encoded","stock_status","attributed_to"}
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return get_badge(bid)
    sets = ", ".join(f"{k}=?" for k in fields)
    vals = list(fields.values()) + [bid]
    with db() as conn:
        conn.execute(f"UPDATE badges SET {sets} WHERE id=?", vals)
    return get_badge(bid)

def delete_badge(bid: str):
    with db() as conn:
        conn.execute("DELETE FROM badges WHERE id=?", (bid,))

def count_user_badges(user_id: str) -> int:
    with db() as conn:
        # Badges normaux + badges stock attribués à cet utilisateur
        own = conn.execute(
            "SELECT COUNT(*) FROM badges WHERE owner_id=? AND is_stock=0",
            (user_id,)
        ).fetchone()[0]
        attributed = conn.execute(
            "SELECT COUNT(*) FROM badges WHERE is_stock=1 AND attributed_to=?",
            (user_id,)
        ).fetchone()[0]
        return own + attributed

def wipe_user_badges(user_id: str):
    with db() as conn:
        conn.execute("DELETE FROM badges WHERE owner_id=? AND is_stock=0", (user_id,))

def uid_exists_for_user(user_id: str, uid: str, exclude_badge_id: str = None) -> bool:
    with db() as conn:
        q = "SELECT 1 FROM badges WHERE owner_id=? AND uid=? AND is_stock=0"
        params = [user_id, uid.upper()]
        if exclude_badge_id:
            q += " AND id != ?"
            params.append(exclude_badge_id)
        return conn.execute(q, params).fetchone() is not None


# ─── MCT history ──────────────────────────────────────────────────────────────

def record_mct(badge_id: str, user_id: str,
               mct_path: str, mct_size: int,
               validity_hours: int = 84) -> dict:
    mid = new_id()
    exp = (datetime.utcnow() + timedelta(hours=validity_hours)).isoformat()
    with db() as conn:
        conn.execute("""
            INSERT INTO mct_history (id,badge_id,user_id,mct_path,mct_size,expires_at,created_at)
            VALUES (?,?,?,?,?,?,?)
        """, (mid, badge_id, user_id, mct_path, mct_size, exp, now()))
    return {"id": mid, "expires_at": exp}

def count_mct_last_24h(user_id: str) -> int:
    cutoff = datetime.utcfromtimestamp(time.time() - 86400).isoformat()
    with db() as conn:
        return conn.execute(
            "SELECT COUNT(*) FROM mct_history WHERE user_id=? AND created_at > ?",
            (user_id, cutoff)
        ).fetchone()[0]

def reset_mct_counter(user_id: str) -> int:
    """Supprime les entrées mct_history des 24h pour remettre le compteur à 0."""
    cutoff = datetime.utcfromtimestamp(time.time() - 86400).isoformat()
    with db() as conn:
        n = conn.execute(
            "DELETE FROM mct_history WHERE user_id=? AND created_at > ?",
            (user_id, cutoff)
        ).rowcount
    return n

def cleanup_expired_mct() -> int:
    ts = now()
    with db() as conn:
        expired = conn.execute(
            "SELECT mct_path FROM mct_history WHERE expires_at < ?", (ts,)
        ).fetchall()
        count = 0
        for row in expired:
            p = Path(row["mct_path"])
            if p.exists():
                try:
                    p.unlink()
                    count += 1
                except Exception:
                    pass
        conn.execute("DELETE FROM mct_history WHERE expires_at < ?", (ts,))
    return count

def get_mct_history_by_user(user_id: str, limit: int = 20) -> list:
    with db() as conn:
        return [dict(r) for r in conn.execute("""
            SELECT m.*, b.name as badge_name, b.uid as badge_uid
            FROM mct_history m JOIN badges b ON m.badge_id=b.id
            WHERE m.user_id=? ORDER BY m.created_at DESC LIMIT ?
        """, (user_id, limit)).fetchall()]


# ─── Requests ─────────────────────────────────────────────────────────────────

def create_request(type_: str, requester_id: str,
                   motif: str = None, target_id: str = None,
                   group_from: str = None, group_to: str = None) -> dict:
    rid = new_id()
    ts = now()
    with db() as conn:
        conn.execute("""
            INSERT INTO requests (id,type,status,requester_id,target_id,
                group_from,group_to,motif,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, (rid, type_, "pending", requester_id, target_id,
              group_from, group_to, motif, ts, ts))
    return get_request(rid)

def get_request(rid: str) -> dict | None:
    with db() as conn:
        row = conn.execute("SELECT * FROM requests WHERE id=?", (rid,)).fetchone()
        return dict(row) if row else None

def get_pending_requests(for_admin_id: str = None) -> list:
    with db() as conn:
        if for_admin_id:
            rows = conn.execute("""
                SELECT r.* FROM requests r
                JOIN users u ON r.requester_id=u.id
                WHERE r.status='pending' AND u.admin_id=?
                ORDER BY r.created_at DESC
            """, (for_admin_id,)).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM requests WHERE status='pending' ORDER BY created_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]

def has_pending_request(requester_id: str, type_: str) -> bool:
    with db() as conn:
        return conn.execute(
            "SELECT 1 FROM requests WHERE requester_id=? AND type=? AND status='pending'",
            (requester_id, type_)
        ).fetchone() is not None

def update_request(rid: str, status: str, handled_by: str) -> dict | None:
    with db() as conn:
        conn.execute(
            "UPDATE requests SET status=?, handled_by=?, updated_at=? WHERE id=?",
            (status, handled_by, now(), rid)
        )
    return get_request(rid)


# ─── Messages ─────────────────────────────────────────────────────────────────

def send_message(from_id: str, to_id: str, content: str) -> dict:
    mid = new_id()
    ts = now()
    with db() as conn:
        conn.execute("""
            INSERT INTO messages (id,from_id,to_id,content,is_read,created_at)
            VALUES (?,?,?,?,0,?)
        """, (mid, from_id, to_id, content[:280], ts))
    return {"id": mid, "created_at": ts}

def get_conversation(user1_id: str, user2_id: str) -> list:
    with db() as conn:
        return [dict(r) for r in conn.execute("""
            SELECT * FROM messages
            WHERE (from_id=? AND to_id=?) OR (from_id=? AND to_id=?)
            ORDER BY created_at ASC LIMIT 100
        """, (user1_id, user2_id, user2_id, user1_id)).fetchall()]

def mark_messages_read(to_id: str, from_id: str):
    with db() as conn:
        conn.execute(
            "UPDATE messages SET is_read=1 WHERE to_id=? AND from_id=? AND is_read=0",
            (to_id, from_id)
        )

def count_unread_messages(user_id: str) -> int:
    with db() as conn:
        return conn.execute(
            "SELECT COUNT(*) FROM messages WHERE to_id=? AND is_read=0", (user_id,)
        ).fetchone()[0]

def get_conversations_list(user_id: str) -> list:
    with db() as conn:
        rows = conn.execute("""
            SELECT DISTINCT
                CASE WHEN m.from_id=? THEN m.to_id ELSE m.from_id END AS other_id,
                MAX(m.created_at) as last_at
            FROM messages m WHERE m.from_id=? OR m.to_id=?
            GROUP BY other_id ORDER BY last_at DESC
        """, (user_id, user_id, user_id)).fetchall()
        result = []
        for row in rows:
            other = get_user_by_id(row["other_id"])
            if not other:
                continue
            unread = conn.execute(
                "SELECT COUNT(*) FROM messages WHERE to_id=? AND from_id=? AND is_read=0",
                (user_id, row["other_id"])
            ).fetchone()[0]
            last = conn.execute("""
                SELECT content FROM messages
                WHERE (from_id=? AND to_id=?) OR (from_id=? AND to_id=?)
                ORDER BY created_at DESC LIMIT 1
            """, (user_id, row["other_id"], row["other_id"], user_id)).fetchone()
            result.append({
                "other_id": row["other_id"],
                "other_login": other["login"],
                "other_role": other["role"],
                "unread": unread,
                "last_message": last["content"][:50] if last else "",
                "last_at": row["last_at"],
            })
        return result


# ─── Notifications ────────────────────────────────────────────────────────────

def push_notif(user_id: str, type_: str, title: str,
               body: str = None, ref_id: str = None):
    with db() as conn:
        conn.execute("""
            INSERT INTO notifications (id,user_id,type,title,body,is_read,ref_id,created_at)
            VALUES (?,?,?,?,?,0,?,?)
        """, (new_id(), user_id, type_, title, body, ref_id, now()))

def get_notifs(user_id: str, unread_only: bool = False) -> list:
    with db() as conn:
        q = "SELECT * FROM notifications WHERE user_id=?"
        if unread_only:
            q += " AND is_read=0"
        return [dict(r) for r in conn.execute(q + " ORDER BY created_at DESC LIMIT 50", (user_id,)).fetchall()]

def mark_notifs_read(user_id: str):
    with db() as conn:
        conn.execute("UPDATE notifications SET is_read=1 WHERE user_id=? AND is_read=0", (user_id,))

def delete_notif(user_id: str, notif_id: str) -> bool:
    with db() as conn:
        n = conn.execute("DELETE FROM notifications WHERE id=? AND user_id=?", (notif_id, user_id)).rowcount
    return n > 0

def count_unread_notifs(user_id: str) -> int:
    with db() as conn:
        return conn.execute(
            "SELECT COUNT(*) FROM notifications WHERE user_id=? AND is_read=0", (user_id,)
        ).fetchone()[0]


# ─── Activity log ─────────────────────────────────────────────────────────────

def log_event(event: str, user_id: str = None, user_login: str = None,
              role: str = None, group_id: str = None, admin_id: str = None,
              ip: str = None, user_agent: str = None, device: str = None,
              detail: dict = None):
    ua  = user_agent if user_agent is not None else (_ctx_ua.get() or None)
    dev = device     if device     is not None else (_ctx_device.get() or None)
    with db() as conn:
        conn.execute("""
            INSERT INTO activity_log
            (id,event,user_id,user_login,role,group_id,admin_id,ip,user_agent,device,detail,created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """, (new_id(), event, user_id, user_login, role, group_id, admin_id,
              ip, ua, dev, _json.dumps(detail or {}), now()))

def get_logs(limit: int = 100, event_filter: str = None,
             date_from: str = None, date_to: str = None) -> list:
    with db() as conn:
        conds, params = [], []
        if event_filter:
            conds.append("event LIKE ?"); params.append(f"%{event_filter}%")
        if date_from:
            conds.append("created_at >= ?"); params.append(date_from)
        if date_to:
            conds.append("created_at <= ?"); params.append(date_to + "T23:59:59")
        where = ("WHERE " + " AND ".join(conds)) if conds else ""
        rows = conn.execute(
            f"SELECT * FROM activity_log {where} ORDER BY created_at DESC LIMIT ?",
            params + [limit]
        ).fetchall()
        return [dict(r) for r in rows]


# ─── Stats ────────────────────────────────────────────────────────────────────

def get_global_stats() -> dict:
    with db() as conn:
        admins    = conn.execute("SELECT COUNT(*) FROM users WHERE role='admin' AND is_deleted=0").fetchone()[0]
        users     = conn.execute("SELECT COUNT(*) FROM users WHERE role='user' AND is_deleted=0").fetchone()[0]
        suspended = conn.execute("SELECT COUNT(*) FROM users WHERE role='user' AND is_deleted=1").fetchone()[0]
        groups    = conn.execute("SELECT COUNT(*) FROM groups").fetchone()[0]
        badges    = conn.execute("SELECT COUNT(*) FROM badges WHERE is_stock=0").fetchone()[0]
        stock     = conn.execute("SELECT COUNT(*) FROM badges WHERE is_stock=1").fetchone()[0]
        pending   = conn.execute("SELECT COUNT(*) FROM requests WHERE status='pending'").fetchone()[0]
        cutoff24  = datetime.utcfromtimestamp(time.time()-86400).isoformat()
        cutoff7d  = datetime.utcfromtimestamp(time.time()-7*86400).isoformat()
        mct_24h   = conn.execute("SELECT COUNT(*) FROM mct_history WHERE created_at > ?", (cutoff24,)).fetchone()[0]
        mct_7d    = conn.execute("SELECT COUNT(*) FROM mct_history WHERE created_at > ?", (cutoff7d,)).fetchone()[0]
    return {
        "admins": admins, "users": users, "suspended": suspended,
        "groups": groups, "badges": badges, "stock_badges": stock,
        "pending_requests": pending, "mct_24h": mct_24h, "mct_7d": mct_7d,
    }

def get_heatmap_data() -> list:
    cutoff = datetime.utcfromtimestamp(time.time()-7*86400).isoformat()
    with db() as conn:
        rows = conn.execute(
            "SELECT created_at FROM mct_history WHERE created_at > ?", (cutoff,)
        ).fetchall()
    counts: dict = {}
    for row in rows:
        dt = datetime.fromisoformat(row["created_at"])
        key = (dt.weekday(), dt.hour)
        counts[key] = counts.get(key, 0) + 1
    return [{"day": d, "hour": h, "count": counts.get((d,h),0)} for d in range(7) for h in range(24)]

def get_mct_by_day(days: int = 7) -> list:
    result = []
    for i in range(days-1, -1, -1):
        start = datetime.utcfromtimestamp(time.time()-((i+1)*86400)).isoformat()
        end   = datetime.utcfromtimestamp(time.time()-(i*86400)).isoformat()
        with db() as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM mct_history WHERE created_at > ? AND created_at <= ?",
                (start, end)
            ).fetchone()[0]
        result.append(count)
    return result

def get_disk_usage() -> dict:
    import shutil
    base = Path(__file__).parent
    total, used, free = shutil.disk_usage(str(base))
    pct = round(used/total*100, 1)
    return {
        "total_gb": round(total/1e9, 1),
        "used_gb": round(used/1e9, 1),
        "free_gb": round(free/1e9, 1),
        "pct": pct,
        "alert": pct > float(get_config("disk_alert_threshold_pct","80")),
    }
