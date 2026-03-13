#!/usr/bin/env python3
"""
setup.py - Configuration initiale du serveur VIGIK Badge Manager
Lance ce script une fois pour configurer le mot de passe et générer le .env
"""

import hashlib
import secrets
import getpass
import sys
import os
from pathlib import Path


def main():
    print("=" * 55)
    print("  VIGIK Badge Manager — Configuration initiale")
    print("=" * 55)
    print()

    # ── Mot de passe ───────────────────────────────────────────
    print("1. Définir le mot de passe d'accès à la PWA")
    while True:
        pwd = getpass.getpass("   Mot de passe : ")
        if len(pwd) < 6:
            print("   ⚠️  Minimum 6 caractères"); continue
        confirm = getpass.getpass("   Confirmer    : ")
        if pwd != confirm:
            print("   ⚠️  Les mots de passe ne correspondent pas"); continue
        break

    pwd_hash = hashlib.sha256(pwd.encode()).hexdigest()
    print(f"   ✓ Hash SHA256 : {pwd_hash[:16]}...")

    # ── JWT secret ────────────────────────────────────────────
    jwt_secret = secrets.token_hex(32)
    print(f"\n2. JWT secret généré automatiquement")

    # ── Chemins ───────────────────────────────────────────────
    print("\n3. Chemins des fichiers (Entrée = valeur par défaut)")

    vigik_exe = input("   vigik_loader_cli.exe [./vigik_loader_cli.exe] : ").strip()
    if not vigik_exe: vigik_exe = "./vigik_loader_cli.exe"

    cert_file = input("   cert.txt [./cert.txt] : ").strip()
    if not cert_file: cert_file = "./cert.txt"

    port = input("   Port serveur [8765] : ").strip()
    if not port: port = "8765"

    duration = input("   Durée validité badges en heures [84] : ").strip()
    if not duration: duration = "84"

    # ── Écriture .env ─────────────────────────────────────────
    env_content = f"""# VIGIK Badge Manager - Configuration
# Généré par setup.py - NE PAS VERSIONNER CE FICHIER

VIGIK_PASSWORD_HASH={pwd_hash}
VIGIK_JWT_SECRET={jwt_secret}
VIGIK_JWT_TTL=24

VIGIK_EXE={vigik_exe}
VIGIK_CERT={cert_file}
VIGIK_BADGES=./badges.json
VIGIK_MCT_DIR=./mct_output
VIGIK_DURATION={duration}

VIGIK_HOST=0.0.0.0
VIGIK_PORT={port}
"""
    Path(".env").write_text(env_content)
    print(f"\n   ✓ Fichier .env créé")

    # ── Vérification dépendances ───────────────────────────────
    print("\n4. Vérification des dépendances")

    checks = {
        "wine"   : "which wine",
        "python3": "which python3",
    }
    for name, cmd in checks.items():
        ok = os.system(f"{cmd} > /dev/null 2>&1") == 0
        print(f"   {'✓' if ok else '✗'} {name}")

    if not Path(cert_file).exists():
        print(f"   ⚠️  {cert_file} introuvable — à placer dans ce dossier")
    else:
        print(f"   ✓ {cert_file}")

    if not Path(vigik_exe).exists():
        print(f"   ⚠️  {vigik_exe} introuvable — à placer dans ce dossier")
    else:
        print(f"   ✓ {vigik_exe}")

    # ── Install dépendances Python ─────────────────────────────
    print("\n5. Installation des dépendances Python")
    os.system(f"{sys.executable} -m pip install fastapi uvicorn python-multipart --break-system-packages -q")
    print("   ✓ fastapi, uvicorn installés")

    # ── Résumé final ───────────────────────────────────────────
    print()
    print("=" * 55)
    print("  Configuration terminée !")
    print()
    print("  Lancer le serveur :")
    print(f"    python3 server.py")
    print()
    print(f"  Accès depuis Android (Tailscale) :")
    print(f"    http://<tailscale-ip>:{port}")
    print("=" * 55)


if __name__ == "__main__":
    main()
