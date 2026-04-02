#!/usr/bin/env python3
"""
setup_v2.py — Badge Manager v2
Initialise la base de données et crée le compte superadmin.
À lancer une seule fois avant le premier démarrage.
"""

import sys
import getpass
from pathlib import Path

# Ajouter le répertoire courant au path
sys.path.insert(0, str(Path(__file__).parent))

import database as D


def main():
    print()
    print("=" * 55)
    print("   Badge Manager v2 — Initialisation")
    print("=" * 55)
    print()

    # Créer les tables
    D.init_db()
    D.init_default_config()
    print("[✓] Base de données initialisée")
    print()

    # Vérifier si superadmin existe déjà
    existing = D.get_superadmin()
    if existing:
        print(f"[!] Un superadmin existe déjà : {existing['login']}")
        print("    Utilisez emergency_v2.py pour réinitialiser son mot de passe.")
        sys.exit(0)

    # Saisie identifiant superadmin
    print("Création du compte superadmin :")
    print()
    while True:
        login = input("  Identifiant (ex: superadmin) : ").strip()
        if len(login) < 2:
            print("  [!] Identifiant trop court (min 2 caractères)")
            continue
        if len(login) > 50:
            print("  [!] Identifiant trop long (max 50 caractères)")
            continue
        break

    # Saisie mot de passe (avec confirmation)
    print()
    while True:
        password = getpass.getpass(f"  Mot de passe (6–14 caractères) : ")
        err = D.validate_pwd(password)
        if err:
            print(f"  [!] {err}")
            continue
        confirm = getpass.getpass(f"  Confirmer le mot de passe : ")
        if password != confirm:
            print("  [!] Les mots de passe ne correspondent pas")
            continue
        break

    # Créer le superadmin
    sa = D.create_user(
        login=login,
        password=password,
        role="superadmin",
        badge_quota=99,
        jwt_ttl_hours=24,
        must_change_pwd=0,  # superadmin n'est pas forcé au premier login
    )

    print()
    print(f"[✓] Superadmin créé : {sa['login']}")
    print()

    # Créer le répertoire MCT
    mct_dir = Path(__file__).parent / "mct_output"
    mct_dir.mkdir(exist_ok=True)
    print(f"[✓] Répertoire MCT : {mct_dir}")

    # Créer le répertoire static_v2
    static_dir = Path(__file__).parent / "static_v2"
    static_dir.mkdir(exist_ok=True)
    print(f"[✓] Répertoire static_v2 créé")

    print()
    print("=" * 55)
    print("   Configuration terminée !")
    print("=" * 55)
    print()
    print("Prochaines étapes :")
    print()
    print("  1. Vérifier que index.html est dans static_v2/")
    print("  2. Démarrer le serveur :")
    print()
    print("     source venv/bin/activate")
    print("     python3 server_v2.py")
    print()
    print("  Ou via systemd :")
    print("     sudo systemctl start vigik-server-v2@$(whoami)")
    print()
    port = __import__('os').environ.get("VIGIK_PORT", "8766")
    print(f"  URL : https://<votre-domaine>:{port}")
    print()


if __name__ == "__main__":
    main()
