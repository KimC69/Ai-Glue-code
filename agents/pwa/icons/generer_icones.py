"""
generer_icones.py — Fabrique les icônes de la PWA (icon-192.png, icon-512.png).

AUCUNE dépendance : encodeur PNG écrit à la main avec la bibliothèque standard
(zlib + struct), fidèle à la philosophie du projet. Le motif est un carré arrondi
ambre sur fond « noir cinéma » avec un triangle « lecture » — l'identité visuelle
de la régie. Relancer ce script régénère les deux tailles :

    python generer_icones.py
"""

import os
import struct
import zlib

FOND = (14, 15, 19)        # #0e0f13 — noir cinéma
AMBRE = (245, 179, 1)      # #f5b301 — accent projecteur


def _dans_carre_arrondi(x, y, n):
    """Vrai si (x, y) est dans le grand carré aux coins arrondis (la « plaque »)."""
    marge = n * 0.16
    rayon = n * 0.18
    x0, y0, x1, y1 = marge, marge, n - marge, n - marge
    if not (x0 <= x <= x1 and y0 <= y <= y1):
        return False
    # Coins : hors du rectangle rétréci, tester la distance au centre du coin.
    cx = min(max(x, x0 + rayon), x1 - rayon)
    cy = min(max(y, y0 + rayon), y1 - rayon)
    return (x - cx) ** 2 + (y - cy) ** 2 <= rayon ** 2


def _dans_triangle_lecture(x, y, n):
    """Vrai si (x, y) est dans le triangle « lecture » (pointe à droite)."""
    xg, xd = n * 0.41, n * 0.63          # bord gauche / pointe droite
    ht, hb = n * 0.35, n * 0.65          # haut / bas
    cy = n / 2.0
    if not (xg <= x <= xd):
        return False
    demi_hauteur = (hb - ht) / 2.0 * (xd - x) / (xd - xg)
    return abs(y - cy) <= demi_hauteur


def _pixels(n):
    """Construit les octets bruts RGB de l'image (n×n) selon le motif."""
    lignes = bytearray()
    for y in range(n):
        lignes.append(0)                 # octet de filtre PNG (0 = aucun) par ligne
        for x in range(n):
            couleur = FOND
            if _dans_carre_arrondi(x + 0.5, y + 0.5, n):
                couleur = AMBRE
                if _dans_triangle_lecture(x + 0.5, y + 0.5, n):
                    couleur = FOND
            lignes.extend(couleur)
    return bytes(lignes)


def _chunk(type_, donnees):
    return (struct.pack(">I", len(donnees)) + type_ + donnees
            + struct.pack(">I", zlib.crc32(type_ + donnees) & 0xffffffff))


def ecrire_png(chemin, n):
    entete = struct.pack(">IIBBBBB", n, n, 8, 2, 0, 0, 0)  # 8 bits, type 2 = RGB
    donnees = zlib.compress(_pixels(n), 9)
    with open(chemin, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        f.write(_chunk(b"IHDR", entete))
        f.write(_chunk(b"IDAT", donnees))
        f.write(_chunk(b"IEND", b""))


if __name__ == "__main__":
    ici = os.path.dirname(os.path.abspath(__file__))
    for taille in (192, 512):
        chemin = os.path.join(ici, f"icon-{taille}.png")
        ecrire_png(chemin, taille)
        print(f"écrit : {chemin}")
