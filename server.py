#!/usr/bin/env python3
"""
server.py - Serveur VIGIK Badge Manager
FastAPI + JWT auth + génération MCT via vigik_loader_cli.exe (Wine)
"""

import json
import os
import subprocess
import sys
import uuid
import hashlib
import hmac
import base64
import time
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Depends, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field

# ─── Config (éditer ici ou via variables d'environnement) ──────────────────────

CONFIG = {
    "password_hash": os.environ.get(
        "VIGIK_PASSWORD_HASH",
        # Hash SHA256 du mot de passe par défaut "vigik1234" — À CHANGER
        "ef92b778bafe771207b4410fb14ab9600f4537ef6ff59c5bf20d8d91c4c0dc82"
    ),
    "jwt_secret": os.environ.get(
        "VIGIK_JWT_SECRET",
        "changeme-secret-jwt-32chars-minimum"
    ),
    "jwt_ttl_hours": int(os.environ.get("VIGIK_JWT_TTL", "24")),
    "vigik_exe": os.environ.get("VIGIK_EXE", "./vigik_loader_cli.exe"),
    "cert_file": os.environ.get("VIGIK_CERT", "./cert.txt"),
    "badges_file": os.environ.get("VIGIK_BADGES", "./badges.json"),
    "mct_output_dir": os.environ.get("VIGIK_MCT_DIR", "./mct_output"),
    "duration_hours": int(os.environ.get("VIGIK_DURATION", "84")),
    "host": os.environ.get("VIGIK_HOST", "0.0.0.0"),
    "port": int(os.environ.get("VIGIK_PORT", "8765")),
}

# ─── Modèles Pydantic ──────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    password: str

class BadgeCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    uid: str = Field(..., min_length=8, max_length=8, pattern=r'^[0-9A-Fa-f]{8}$')
    color: str = Field(default="#3B82F6", pattern=r'^#[0-9A-Fa-f]{6}$')
    icon: str = Field(default="🏠")

class BadgeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=50)
    uid: str | None = Field(default=None, min_length=8, max_length=8, pattern=r'^[0-9A-Fa-f]{8}$')
    color: str | None = Field(default=None, pattern=r'^#[0-9A-Fa-f]{6}$')
    icon: str | None = None

# ─── JWT minimal (sans dépendance externe) ────────────────────────────────────

def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode()

def _jwt_sign(payload: dict) -> str:
    header = _b64url(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    body   = _b64url(json.dumps(payload).encode())
    sig    = _b64url(hmac.new(
        CONFIG["jwt_secret"].encode(),
        f"{header}.{body}".encode(),
        hashlib.sha256
    ).digest())
    return f"{header}.{body}.{sig}"

def _jwt_verify(token: str) -> dict:
    try:
        header, body, sig = token.split(".")
        expected = _b64url(hmac.new(
            CONFIG["jwt_secret"].encode(),
            f"{header}.{body}".encode(),
            hashlib.sha256
        ).digest())
        if not hmac.compare_digest(sig, expected):
            raise ValueError("signature invalide")
        payload = json.loads(base64.urlsafe_b64decode(body + "=="))
        if payload.get("exp", 0) < time.time():
            raise ValueError("token expiré")
        return payload
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Token invalide: {e}")

# ─── Auth dependency ───────────────────────────────────────────────────────────

bearer = HTTPBearer()

def require_auth(creds: HTTPAuthorizationCredentials = Depends(bearer)) -> dict:
    return _jwt_verify(creds.credentials)

# ─── Badges storage ────────────────────────────────────────────────────────────

def load_badges() -> dict:
    p = Path(CONFIG["badges_file"])
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}

def save_badges(badges: dict):
    Path(CONFIG["badges_file"]).write_text(
        json.dumps(badges, ensure_ascii=False, indent=2)
    )

# ─── VIGIK encoding ────────────────────────────────────────────────────────────

def json_to_mfd(json_path: Path) -> bytes:
    """Convertit le JSON produit par vigik_loader_cli.exe en binaire MFD 1024 bytes."""
    data = json.loads(json_path.read_text())
    blocks = {b["id"]: bytes.fromhex(b["value"]) for b in data["blocks"]}
    mfd = bytearray(64 * 16)  # Mifare 1K = 64 blocs x 16 bytes
    for bid, val in blocks.items():
        mfd[bid * 16:(bid + 1) * 16] = val
    # Corriger le BCC (byte 4 du bloc 0 = XOR des 4 bytes UID)
    mfd[4] = mfd[0] ^ mfd[1] ^ mfd[2] ^ mfd[3]
    return bytes(mfd)


def encode_badge(uid: str, name: str) -> Path:
    """Lance vigik_loader_cli.exe via Wine en mode offline, retourne le .mct"""
    uid = uid.upper()
    out_dir = Path(CONFIG["mct_output_dir"])
    out_dir.mkdir(exist_ok=True)

    json_path = out_dir / f"badge_{uid}.json"
    mct_path  = out_dir / f"vigik_{name.replace(' ', '_')}_{uid}.mct"

    # Vérifications
    if not Path(CONFIG["cert_file"]).exists():
        raise HTTPException(500, f"cert.txt introuvable: {CONFIG['cert_file']}")
    if not Path(CONFIG["vigik_exe"]).exists():
        raise HTTPException(500, f"vigik_loader_cli.exe introuvable: {CONFIG['vigik_exe']}")

    # Lancer vigik_loader_cli.exe via Wine — output JSON (format réel du binaire)
    cmd = [
        "wine", CONFIG["vigik_exe"],
        "-c", CONFIG["cert_file"],
        "-u", uid,
        "-o", "json",
        "-f", str(json_path),
        "-d", str(CONFIG["duration_hours"]),
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            env={**os.environ, "WINEDEBUG": "-all"}
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(500, "Timeout lors de l'encodage VIGIK")
    except FileNotFoundError:
        raise HTTPException(500, "Wine non installé (sudo apt install wine)")

    if not json_path.exists():
        raise HTTPException(500, f"Erreur vigik_loader_cli:\n{result.stdout}\n{result.stderr}")

    # JSON → MFD binaire → MCT texte
    try:
        mfd_data = json_to_mfd(json_path)
    except Exception as e:
        json_path.unlink(missing_ok=True)
        raise HTTPException(500, f"Erreur conversion JSON->MFD: {e}")
    json_path.unlink(missing_ok=True)

    mct_content = mfd_to_mct(mfd_data, uid=uid, name=name)
    mct_path.write_text(mct_content, encoding="utf-8")

    return mct_path


def mfd_to_mct(mfd_data: bytes, uid: str = "", name: str = "") -> str:
    """Convertit un dump MFD binaire en format texte MCT."""
    size = len(mfd_data)
    if size == 1024:
        num_sectors, card_type = 16, "Mifare Classic 1K"
    elif size == 4096:
        num_sectors, card_type = 40, "Mifare Classic 4K"
    else:
        raise HTTPException(500, f"Taille MFD invalide: {size} bytes")

    lines = [
        f"# VIGIK Badge: {name}",
        f"# UID: {uid.upper()}",
        f"# Généré le {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"# Type: {card_type}",
        "",
    ]

    offset = 0
    for sector in range(5):
        blocks_count = 16 if sector >= 32 else 4
        lines.append(f"+Sector: {sector}")
        for _ in range(blocks_count):
            block = mfd_data[offset:offset + 16]
            lines.append(block.hex().upper())
            offset += 16

    return "\n".join(lines) + "\n"

# ─── App FastAPI ───────────────────────────────────────────────────────────────

app = FastAPI(title="VIGIK Badge Manager", docs_url=None, redoc_url=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Servir la PWA (fichiers statiques)
app.mount("/static", StaticFiles(directory="static"), name="static")


# ── Auth ────────────────────────────────────────────────────────────────────────

@app.post("/api/login")
def login(req: LoginRequest):
    h = hashlib.sha256(req.password.encode()).hexdigest()
    if not hmac.compare_digest(h, CONFIG["password_hash"]):
        raise HTTPException(401, "Mot de passe incorrect")
    token = _jwt_sign({
        "sub": "admin",
        "iat": int(time.time()),
        "exp": int(time.time()) + CONFIG["jwt_ttl_hours"] * 3600,
    })
    return {"token": token, "ttl_hours": CONFIG["jwt_ttl_hours"]}


# ── Badges CRUD ─────────────────────────────────────────────────────────────────

@app.get("/api/badges")
def list_badges(_=Depends(require_auth)):
    badges = load_badges()
    return list(badges.values())


@app.post("/api/badges", status_code=201)
def create_badge(data: BadgeCreate, _=Depends(require_auth)):
    badges = load_badges()
    # Vérifier unicité UID
    if any(b["uid"].upper() == data.uid.upper() for b in badges.values()):
        raise HTTPException(409, f"UID {data.uid.upper()} déjà enregistré")
    bid = str(uuid.uuid4())
    badge = {
        "id": bid,
        "name": data.name,
        "uid": data.uid.upper(),
        "color": data.color,
        "icon": data.icon,
        "created_at": datetime.now().isoformat(),
        "last_encoded": None,
    }
    badges[bid] = badge
    save_badges(badges)
    return badge


@app.patch("/api/badges/{badge_id}")
def update_badge(badge_id: str, data: BadgeUpdate, _=Depends(require_auth)):
    badges = load_badges()
    if badge_id not in badges:
        raise HTTPException(404, "Badge introuvable")
    badge = badges[badge_id]
    if data.name  is not None: badge["name"]  = data.name
    if data.uid   is not None: badge["uid"]   = data.uid.upper()
    if data.color is not None: badge["color"] = data.color
    if data.icon  is not None: badge["icon"]  = data.icon
    save_badges(badges)
    return badge


@app.delete("/api/badges/{badge_id}", status_code=204)
def delete_badge(badge_id: str, _=Depends(require_auth)):
    badges = load_badges()
    if badge_id not in badges:
        raise HTTPException(404, "Badge introuvable")
    del badges[badge_id]
    save_badges(badges)


# ── Encoding ────────────────────────────────────────────────────────────────────

@app.post("/api/badges/{badge_id}/encode")
def encode(badge_id: str, _=Depends(require_auth)):
    badges = load_badges()
    if badge_id not in badges:
        raise HTTPException(404, "Badge introuvable")
    badge = badges[badge_id]

    mct_path = encode_badge(uid=badge["uid"], name=badge["name"])

    # Mettre à jour last_encoded
    badge["last_encoded"] = datetime.now().isoformat()
    save_badges(badges)

    return FileResponse(
        path=str(mct_path),
        media_type="application/octet-stream",
        filename=mct_path.name,
        headers={"X-Badge-Name": badge["name"], "X-Badge-UID": badge["uid"]},
    )


# ── Health ──────────────────────────────────────────────────────────────────────

@app.get("/api/health")
def health():
    wine_ok = subprocess.run(["which", "wine"], capture_output=True).returncode == 0
    exe_ok  = Path(CONFIG["vigik_exe"]).exists()
    cert_ok = Path(CONFIG["cert_file"]).exists()
    return {
        "status": "ok",
        "wine": wine_ok,
        "vigik_exe": exe_ok,
        "cert": cert_ok,
        "badges_count": len(load_badges()),
    }


# ── Servir la PWA (fallback SPA) ────────────────────────────────────────────────

@app.get("/{full_path:path}")
def serve_pwa(full_path: str):
    return FileResponse("static/index.html")


# ─── Lancement ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    print(f"[*] VIGIK Badge Manager démarré sur {CONFIG['host']}:{CONFIG['port']}")
    print(f"[*] Accessible via : https://budgie-server.tail609373.ts.net:{CONFIG['port']}")
    uvicorn.run(
        "server:app",
        host=CONFIG["host"],
        port=CONFIG["port"],
        reload=False,
        ssl_certfile="/home/budgie/Documents/Vigik/budgie-server.tail609373.ts.net.crt",
        ssl_keyfile="/home/budgie/Documents/Vigik/budgie-server.tail609373.ts.net.key",
    )
