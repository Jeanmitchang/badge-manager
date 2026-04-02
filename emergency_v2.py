#!/usr/bin/env python3
"""
emergency_v2.py — Badge Manager v2
Procédure d'urgence : reset MDP superadmin, déblocage, token temporaire.
À exécuter UNIQUEMENT via SSH sur le serveur.
"""

import sys
import getpass
import time
import base64
import hashlib
import hmac
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import database as D


def gen_emergency_token(user_id: str, secret: str) -> str:
    """Génère un JWT valide 1 heure."""
    import os
    secret = os.environ.get("VIGIK_JWT_SECRET", secret)
    payload = {
        "sub": user_id, "role": "superadmin",
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600,
        "emergency": True,
    }
    def b64(data):
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode()
    h = b64(json.dumps({"alg":"HS256","typ":"JWT"}).encode())
    b = b64(json.dumps(payload).encode())
    s = b64(hmac.new(secret.encode(), f"{h}.{b}".encode(), hashlib.sha256).digest())
    return f"{h}.{b}.{s}"


def main():
    print()
    print("=" * 55)
    print("   Badge Manager v2 — PROCÉDURE D'URGENCE")
    print("   Accès réservé SSH uniquement")
    print("=" * 55)
    print()

    D.init_db()
    sa = D.get_superadmin()

    if not sa:
        print("[!] Aucun superadmin trouvé en base.")
        print("    Exécutez setup_v2.py pour créer le superadmin.")
        sys.exit(1)

    print(f"Compte superadmin trouvé : {sa['login']}")
    print(f"Statut : {'Actif' if sa['is_active'] else '⚠️ BLOQUÉ'}")
    print()
    print("Options disponibles :")
    print("  1. Réinitialiser le mot de passe")
    print("  2. Débloquer le compte")
    print("  3. Générer un token temporaire (1h)")
    print("  4. Quitter")
    print()

    choice = input("Votre choix [1-4] : ").strip()

    if choice == "1":
        print()
        while True:
            new_pwd = getpass.getpass("Nouveau mot de passe (6–14 car.) : ")
            err = D.validate_pwd(new_pwd)
            if err:
                print(f"[!] {err}")
                continue
            confirm = getpass.getpass("Confirmer : ")
            if new_pwd != confirm:
                print("[!] Les mots de passe ne correspondent pas")
                continue
            break
        D.update_user(sa["id"], pwd_hash=D.hash_pwd(new_pwd), must_change_pwd=0,
                      is_active=1, is_deleted=0)
        D.log_event("superadmin_emergency_access",
                    user_id=sa["id"], user_login=sa["login"],
                    detail={"action": "password_reset"})
        print()
        print(f"[✓] Mot de passe réinitialisé pour : {sa['login']}")

    elif choice == "2":
        D.update_user(sa["id"], is_active=1, is_deleted=0)
        D.log_event("superadmin_emergency_access",
                    user_id=sa["id"], user_login=sa["login"],
                    detail={"action": "account_unblocked"})
        print(f"[✓] Compte débloqué : {sa['login']}")

    elif choice == "3":
        import os
        secret = input("JWT secret (Entrée pour lire depuis .env) : ").strip()
        if not secret:
            secret = os.environ.get("VIGIK_JWT_SECRET", "")
        if not secret:
            print("[!] VIGIK_JWT_SECRET introuvable. Définissez-le dans .env ou saisissez-le.")
            sys.exit(1)
        token = gen_emergency_token(sa["id"], secret)
        D.log_event("superadmin_emergency_access",
                    user_id=sa["id"], user_login=sa["login"],
                    detail={"action": "emergency_token_generated"})
        print()
        print("[✓] Token d'urgence généré (valide 1h) :")
        print()
        print(f"  {token}")
        print()
        print("Utilisation dans la PWA :")
        print("  Ouvrir la console du navigateur et exécuter :")
        print(f"  localStorage.setItem('bm_token', '{token[:30]}...')")
        print("  Puis recharger la page.")

    elif choice == "4":
        print("Annulé.")
    else:
        print("[!] Choix invalide.")

    print()


if __name__ == "__main__":
    main()
