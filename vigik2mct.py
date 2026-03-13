#!/usr/bin/env python3
"""
vigik2mct.py - Générateur de fichier MCT (Mifare Classic Tool) depuis VIGIK
===========================================================================
Usage:
  Étape 1 (Windows) : vigik_loader_cli.exe -c cert.txt -u <UID> -o mfd -f badge.mfd
  Étape 2 (ici)     : python vigik2mct.py badge.mfd badge.mct
  Étape 3 (Android) : Importer badge.mct dans MCT → Write Tag

Ou tout-en-un (Windows uniquement, nécessite vigik_loader_cli.exe dans le PATH):
  python vigik2mct.py --auto -c cert.txt -u <UID>
"""

import sys
import os
import argparse
import subprocess
import struct
from datetime import datetime
from pathlib import Path


# ─── Constantes VIGIK ──────────────────────────────────────────────────────────

MIFARE_1K_SIZE   = 1024   # bytes
MIFARE_4K_SIZE   = 4096
BLOCK_SIZE       = 16     # bytes par bloc
BLOCKS_PER_SECTOR_SMALL = 4   # secteurs 0-31 (1K) ou 0-31 (4K petits)
BLOCKS_PER_SECTOR_LARGE = 16  # secteurs 32-39 (4K grands)

# Clés VIGIK extraites du binaire vigik_loader_cli
VIGIK_KEY_A_SECTOR0 = bytes.fromhex("A0A1A2A3A4A5")  # Secteur 0, KeyA standard
VIGIK_KEY_STD       = bytes.fromhex("314B49474956")  # "1KIGIV" - clé data secteurs


def mfd_to_mct(mfd_data: bytes, uid: str = None) -> str:
    """
    Convertit un dump MFD (binaire Mifare) en format texte MCT.
    
    Format MCT:
      +Sector: N
      <bloc0_hex>
      <bloc1_hex>
      <bloc2_hex>
      <trailer_hex>   (KeyA + AccessBits + KeyB)
    """
    size = len(mfd_data)
    
    if size == MIFARE_1K_SIZE:
        num_sectors = 16
        card_type = "Mifare Classic 1K"
    elif size == MIFARE_4K_SIZE:
        num_sectors = 40
        card_type = "Mifare Classic 4K"
    else:
        raise ValueError(f"Taille MFD invalide: {size} bytes (attendu 1024 ou 4096)")

    lines = [
        f"# Généré par vigik2mct.py le {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"# Type: {card_type}",
    ]
    if uid:
        lines.append(f"# UID: {uid.upper()}")
    lines.append("")

    offset = 0
    for sector in range(num_sectors):
        # Mifare 4K: secteurs 32-39 ont 16 blocs au lieu de 4
        if sector >= 32:
            blocks_in_sector = BLOCKS_PER_SECTOR_LARGE
        else:
            blocks_in_sector = BLOCKS_PER_SECTOR_SMALL

        lines.append(f"+Sector: {sector}")
        
        for block in range(blocks_in_sector):
            block_data = mfd_data[offset:offset + BLOCK_SIZE]
            if len(block_data) < BLOCK_SIZE:
                block_data = block_data.ljust(BLOCK_SIZE, b'\x00')
            lines.append(block_data.hex().upper())
            offset += BLOCK_SIZE

    return "\n".join(lines) + "\n"


def generate_mfd_via_cli(cert_file: str, uid: str, duration: int = 84,
                          vigik_exe: str = "vigik_loader_cli.exe",
                          output_mfd: str = "badge.mfd",
                          when_load: str = None) -> bytes:
    """
    Lance vigik_loader_cli.exe en mode offline pour générer le MFD.
    Nécessite Windows ou Wine.
    
    Returns: contenu du fichier MFD en bytes
    """
    cmd = [
        vigik_exe,
        "-c", cert_file,
        "-u", uid,
        "-o", "mfd",
        "-f", output_mfd,
        "-d", str(duration),
    ]
    if when_load:
        cmd += ["--when-load", when_load]

    print(f"[*] Lancement: {' '.join(cmd)}")
    
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            print(f"[!] Erreur vigik_loader_cli (code {result.returncode}):")
            print(result.stdout)
            print(result.stderr)
            sys.exit(1)
        
        print(result.stdout.strip())
        
        if not os.path.exists(output_mfd):
            raise FileNotFoundError(f"Fichier MFD non généré: {output_mfd}")
        
        return Path(output_mfd).read_bytes()
        
    except FileNotFoundError:
        print(f"[!] Exécutable introuvable: {vigik_exe}")
        print("    Assurez-vous que vigik_loader_cli.exe est dans le même dossier ou dans le PATH")
        sys.exit(1)
    except subprocess.TimeoutExpired:
        print("[!] Timeout lors du lancement de vigik_loader_cli")
        sys.exit(1)


def parse_json_blocks(json_text: str) -> bytes:
    """
    Parse le format JSON de vigik_loader_cli (mode stdout/json).
    
    Format JSON: { "blocks": [ { "id": N, "value": "AABBCC..." }, ... ] }
    Returns: bytes de 1024 ou 4096 bytes (MFD reconstitué)
    """
    import json, re
    
    # Extraire le JSON (ignorer les lignes de bannière)
    json_match = re.search(r'(\{.*"blocks".*\})', json_text, re.DOTALL)
    if not json_match:
        raise ValueError("Format JSON non trouvé dans la sortie")
    
    data = json.loads(json_match.group(1))
    blocks = data.get("blocks", [])
    
    if not blocks:
        raise ValueError("Aucun bloc dans le JSON")
    
    max_id = max(b["id"] for b in blocks)
    
    # Déterminer la taille (1K = 64 blocs, 4K = 256 blocs)
    if max_id < 64:
        total_blocks = 64
    else:
        total_blocks = 256
    
    mfd = bytearray(total_blocks * BLOCK_SIZE)
    
    block_by_id = {b["id"]: b["value"] for b in blocks}
    for block_id, value in block_by_id.items():
        offset = block_id * BLOCK_SIZE
        block_bytes = bytes.fromhex(value)
        mfd[offset:offset + BLOCK_SIZE] = block_bytes
    
    return bytes(mfd)


def inspect_mfd(mfd_data: bytes):
    """Affiche les informations extraites du MFD (UID, service, validité)."""
    print("\n── Inspection du MFD ──────────────────────────────────────")
    
    # Bloc 0 = bloc fabricant (UID + BCC + data)
    bloc0 = mfd_data[0:16]
    uid = bloc0[0:4]
    bcc = bloc0[4]
    print(f"  UID      : {uid.hex().upper()}")
    print(f"  BCC      : {bcc:02X}")
    print(f"  Fab data : {bloc0[5:16].hex().upper()}")
    
    # Secteur 0 blocs 1-2 : données VIGIK
    bloc1 = mfd_data[16:32]
    bloc2 = mfd_data[32:48]
    print(f"  Bloc 1   : {bloc1.hex().upper()}")
    print(f"  Bloc 2   : {bloc2.hex().upper()}")
    
    # Trailer secteur 0
    trailer0 = mfd_data[48:64]
    key_a = trailer0[0:6]
    access = trailer0[6:10]
    key_b = trailer0[10:16]
    print(f"  Trailer  : KeyA={key_a.hex().upper()} AC={access.hex().upper()} KeyB={key_b.hex().upper()}")
    print("────────────────────────────────────────────────────────────\n")


def main():
    parser = argparse.ArgumentParser(
        description="Convertit un dump VIGIK MFD en fichier MCT pour Mifare Classic Tool (Android)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples:
  # Mode manuel: convertir un MFD existant
  python vigik2mct.py badge.mfd badge.mct

  # Mode auto (Windows): générer + convertir en une commande
  python vigik2mct.py --auto -c cert.txt -u 8ABC1E53

  # Avec durée personnalisée (48h) et date de chargement fixe
  python vigik2mct.py --auto -c cert.txt -u 8ABC1E53 -d 48 --when-load 2603091200

  # Depuis JSON (sortie stdout de vigik_loader_cli)
  vigik_loader_cli.exe -c cert.txt -u 8ABC1E53 > output.json
  python vigik2mct.py --from-json output.json badge.mct
        """
    )
    
    # Mode de fonctionnement
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--auto", action="store_true",
                            help="Lancer vigik_loader_cli.exe automatiquement (nécessite Windows/Wine)")
    mode_group.add_argument("--from-json", metavar="JSON_FILE",
                            help="Convertir depuis un fichier JSON (sortie stdout de vigik_loader_cli)")
    
    # Arguments positionnels (mode conversion simple)
    parser.add_argument("input", nargs="?", metavar="INPUT.mfd",
                        help="Fichier MFD source (mode conversion simple)")
    parser.add_argument("output", nargs="?", metavar="OUTPUT.mct",
                        help="Fichier MCT de sortie")

    # Options mode --auto
    parser.add_argument("-c", "--cert", metavar="FILE", help="Fichier cert.txt")
    parser.add_argument("-u", "--uid", metavar="UID", 
                        help="UID de la carte cible (8 hex chars, ex: 8ABC1E53)")
    parser.add_argument("-d", "--duration", type=int, default=84, metavar="HH",
                        help="Durée de validité en heures (1-84, défaut: 84)")
    parser.add_argument("--when-load", metavar="yymmddhhmm",
                        help="Date/heure de chargement (format: yymmddhhmm)")
    parser.add_argument("--exe", default="vigik_loader_cli.exe",
                        metavar="PATH", help="Chemin vers vigik_loader_cli.exe")
    parser.add_argument("--mfd-tmp", default="badge_tmp.mfd",
                        help="Fichier MFD temporaire (mode --auto)")
    parser.add_argument("--inspect", action="store_true",
                        help="Afficher les infos extraites du MFD")
    
    args = parser.parse_args()

    # ── Mode --auto ───────────────────────────────────────────────
    if args.auto:
        if not args.cert:
            parser.error("--auto requiert --cert / -c")
        if not args.uid:
            parser.error("--auto requiert --uid / -u")
        
        output_mct = args.output or f"vigik_{args.uid.upper()}.mct"
        
        mfd_data = generate_mfd_via_cli(
            cert_file=args.cert,
            uid=args.uid,
            duration=args.duration,
            vigik_exe=args.exe,
            output_mfd=args.mfd_tmp,
            when_load=args.when_load,
        )
        
        if args.inspect:
            inspect_mfd(mfd_data)
        
        mct_content = mfd_to_mct(mfd_data, uid=args.uid)
        Path(output_mct).write_text(mct_content, encoding="utf-8")
        
        print(f"[✓] Fichier MCT généré : {output_mct}")
        print(f"    → Copier sur Android et ouvrir avec Mifare Classic Tool")
        
        # Nettoyage fichier temporaire
        if os.path.exists(args.mfd_tmp):
            os.remove(args.mfd_tmp)
        return

    # ── Mode --from-json ──────────────────────────────────────────
    if args.from_json:
        if not os.path.exists(args.from_json):
            print(f"[!] Fichier JSON introuvable: {args.from_json}")
            sys.exit(1)
        
        output_mct = args.output or args.from_json.replace(".json", ".mct")
        json_text = Path(args.from_json).read_text(encoding="utf-8", errors="replace")
        
        print(f"[*] Parsing JSON: {args.from_json}")
        mfd_data = parse_json_blocks(json_text)
        
        if args.inspect:
            inspect_mfd(mfd_data)
        
        mct_content = mfd_to_mct(mfd_data, uid=args.uid)
        Path(output_mct).write_text(mct_content, encoding="utf-8")
        
        print(f"[✓] Fichier MCT généré : {output_mct}")
        return

    # ── Mode conversion simple MFD → MCT ─────────────────────────
    if not args.input:
        parser.print_help()
        sys.exit(0)
    
    if not os.path.exists(args.input):
        print(f"[!] Fichier MFD introuvable: {args.input}")
        sys.exit(1)
    
    output_mct = args.output or args.input.replace(".mfd", ".mct")
    if output_mct == args.input:
        output_mct = args.input + ".mct"
    
    mfd_data = Path(args.input).read_bytes()
    print(f"[*] Lecture MFD: {args.input} ({len(mfd_data)} bytes)")
    
    if args.inspect:
        inspect_mfd(mfd_data)
    
    mct_content = mfd_to_mct(mfd_data, uid=args.uid)
    Path(output_mct).write_text(mct_content, encoding="utf-8")
    
    print(f"[✓] Fichier MCT généré : {output_mct}")
    print(f"    → Copier sur Android et ouvrir avec Mifare Classic Tool")


if __name__ == "__main__":
    main()
