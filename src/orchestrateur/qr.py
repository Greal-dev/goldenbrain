"""Code QR minimal (ISO/IEC 18004) : mode octet, correction M, versions 1 à 10, rendu SVG.

Rôle : dessiner l'adresse d'appairage d'un téléphone (INV-DISTANT-5) et le lien de téléchargement
de Tailscale, sans dépendance nouvelle ni service extérieur (rien ne quitte le poste).
Frontières : aucune entrée/sortie ; aucune donnée gardée ; ≤ 213 octets (version 10, M).
Invariants portés : INV-DISTANT-5 (le code QR se calcule sur le poste, jamais par un service tiers).
"""

from __future__ import annotations

# Correction M, versions 1..10 : octets de correction par bloc, nombre de blocs.
_ECC = (10, 16, 26, 18, 24, 16, 18, 22, 22, 26)
_BLOCS = (1, 1, 1, 2, 2, 4, 4, 4, 5, 5)
_FORMAT_M = 0  # bits de niveau : L=1, M=0, Q=3, H=2
VERSION_MAX = 10


def _gf_mul(x: int, y: int) -> int:
    z = 0
    for i in reversed(range(8)):
        z = (z << 1) ^ ((z >> 7) * 0x11D)
        z ^= ((y >> i) & 1) * x
    return z


def _rs_diviseur(degre: int) -> list[int]:
    r = [0] * (degre - 1) + [1]
    racine = 1
    for _ in range(degre):
        for j in range(degre):
            r[j] = _gf_mul(r[j], racine)
            if j + 1 < degre:
                r[j] ^= r[j + 1]
        racine = _gf_mul(racine, 0x02)
    return r


def _rs_reste(donnees: list[int], diviseur: list[int]) -> list[int]:
    r = [0] * len(diviseur)
    for b in donnees:
        f = b ^ r.pop(0)
        r.append(0)
        for i, c in enumerate(diviseur):
            r[i] ^= _gf_mul(c, f)
    return r


def _modules_bruts(v: int) -> int:
    r = (16 * v + 128) * v + 64
    if v >= 2:
        n = v // 7 + 2
        r -= (25 * n - 10) * n - 55
        if v >= 7:
            r -= 36
    return r


def _capacite(v: int) -> int:
    """Octets utiles en mode octet (en-tête de 4 + 8 ou 16 bits déduit)."""
    data = _modules_bruts(v) // 8 - _ECC[v - 1] * _BLOCS[v - 1]
    return (data * 8 - 4 - (8 if v < 10 else 16)) // 8


def _alignements(v: int, taille: int) -> list[int]:
    if v == 1:
        return []
    n = v // 7 + 2
    pas = (v * 8 + n * 3 + 5) // (n * 4 - 4) * 2
    return [6] + sorted(taille - 7 - i * pas for i in range(n - 1))


class _Grille:
    def __init__(self, v: int):
        self.v, self.n = v, v * 4 + 17
        self.m = [[False] * self.n for _ in range(self.n)]
        self.fonction = [[False] * self.n for _ in range(self.n)]

    def poser(self, x: int, y: int, noir: bool) -> None:
        self.m[y][x], self.fonction[y][x] = noir, True

    def motifs(self) -> None:
        n = self.n
        for i in range(n):
            self.poser(6, i, i % 2 == 0)
            self.poser(i, 6, i % 2 == 0)
        for cx, cy in ((3, 3), (n - 4, 3), (3, n - 4)):  # repères de position + séparateurs
            for dy in range(-4, 5):
                for dx in range(-4, 5):
                    x, y = cx + dx, cy + dy
                    if 0 <= x < n and 0 <= y < n:
                        d = max(abs(dx), abs(dy))
                        self.poser(x, y, d not in (2, 4))
        pos = _alignements(self.v, n)
        for i, a in enumerate(pos):
            for j, b in enumerate(pos):
                if (i, j) in ((0, 0), (0, len(pos) - 1), (len(pos) - 1, 0)):
                    continue
                for dy in range(-2, 3):
                    for dx in range(-2, 3):
                        self.poser(a + dx, b + dy, max(abs(dx), abs(dy)) != 1)
        self.format(0)
        if self.v >= 7:
            r = self.v
            for _ in range(12):
                r = (r << 1) ^ ((r >> 11) * 0x1F25)
            bits = self.v << 12 | r
            for i in range(18):
                noir = (bits >> i) & 1 == 1
                a, b = n - 11 + i % 3, i // 3
                self.poser(a, b, noir)
                self.poser(b, a, noir)

    def format(self, masque: int) -> None:
        d = _FORMAT_M << 3 | masque
        r = d
        for _ in range(10):
            r = (r << 1) ^ ((r >> 9) * 0x537)
        bits = (d << 10 | r) ^ 0x5412
        b = [(bits >> i) & 1 == 1 for i in range(15)]
        n = self.n
        for i in range(6):
            self.poser(8, i, b[i])
        self.poser(8, 7, b[6])
        self.poser(8, 8, b[7])
        self.poser(7, 8, b[8])
        for i in range(9, 15):
            self.poser(14 - i, 8, b[i])
        for i in range(8):
            self.poser(n - 1 - i, 8, b[i])
        for i in range(8, 15):
            self.poser(8, n - 15 + i, b[i])
        self.poser(8, n - 8, True)

    def donnees(self, octets: list[int]) -> None:
        i, n, droite = 0, self.n, self.n - 1
        while droite >= 1:
            if droite == 6:
                droite = 5
            for vert in range(n):
                for j in range(2):
                    x = droite - j
                    y = n - 1 - vert if (droite + 1) & 2 == 0 else vert
                    if not self.fonction[y][x] and i < len(octets) * 8:
                        self.m[y][x] = (octets[i >> 3] >> (7 - (i & 7))) & 1 == 1
                        i += 1
            droite -= 2

    def masquer(self, k: int) -> None:
        f = (lambda x, y: (x + y) % 2 == 0, lambda x, y: y % 2 == 0, lambda x, y: x % 3 == 0,
             lambda x, y: (x + y) % 3 == 0, lambda x, y: (x // 3 + y // 2) % 2 == 0,
             lambda x, y: x * y % 2 + x * y % 3 == 0, lambda x, y: (x * y % 2 + x * y % 3) % 2 == 0,
             lambda x, y: ((x + y) % 2 + x * y % 3) % 2 == 0)[k]
        for y in range(self.n):
            for x in range(self.n):
                if not self.fonction[y][x] and f(x, y):
                    self.m[y][x] = not self.m[y][x]


def _penalite(m: list[list[bool]]) -> int:
    n, p = len(m), 0
    lignes = m + [list(c) for c in zip(*m)]
    motif_a, motif_b = [1, 0, 1, 1, 1, 0, 1, 0, 0, 0, 0], [0, 0, 0, 0, 1, 0, 1, 1, 1, 0, 1]
    for ligne in lignes:
        suite = 1
        for i in range(1, n + 1):
            if i < n and ligne[i] == ligne[i - 1]:
                suite += 1
                continue
            if suite >= 5:
                p += 3 + suite - 5
            suite = 1
        bits = [int(c) for c in ligne]
        p += 40 * sum(bits[i:i + 11] in (motif_a, motif_b) for i in range(n - 10))
    p += 3 * sum(m[y][x] == m[y][x + 1] == m[y + 1][x] == m[y + 1][x + 1]
                 for y in range(n - 1) for x in range(n - 1))
    noirs, total = sum(map(sum, m)), n * n
    return p + ((abs(noirs * 20 - total * 10) + total - 1) // total - 1) * 10


def matrice(texte: str, masque: int | None = None) -> list[list[bool]]:
    """Modules du code (True = noir), sans marge. `masque` forcé : réservé aux tests."""
    octets = texte.encode("utf-8")
    v = next((v for v in range(1, VERSION_MAX + 1) if len(octets) <= _capacite(v)), 0)
    if not v:
        raise ValueError("texte trop long pour le code QR")
    bits: list[int] = []
    for val, lg in ((0b0100, 4), (len(octets), 8 if v < 10 else 16), *((b, 8) for b in octets)):
        bits += [(val >> i) & 1 for i in reversed(range(lg))]
    ecc, nb, brut = _ECC[v - 1], _BLOCS[v - 1], _modules_bruts(v) // 8
    capa = (brut - ecc * nb) * 8
    bits += [0] * min(4, capa - len(bits))
    bits += [0] * (-len(bits) % 8)
    data = [int("".join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits), 8)]
    pad = 0xEC
    while len(data) * 8 < capa:
        data.append(pad)
        pad ^= 0xEC ^ 0x11
    courts, lg_court = nb - brut % nb, brut // nb
    div, blocs, k = _rs_diviseur(ecc), [], 0
    for i in range(nb):
        dat = data[k:k + lg_court - ecc + (0 if i < courts else 1)]
        k += len(dat)
        reste = _rs_reste(dat, div)
        blocs.append(dat + ([0] if i < courts else []) + reste)
    final = [b[i] for i in range(len(blocs[0])) for j, b in enumerate(blocs)
             if i != lg_court - ecc or j >= courts]
    g = _Grille(v)
    g.motifs()
    g.donnees(final)
    choix = range(8) if masque is None else (masque,)
    meilleur = None
    for k in choix:
        g.masquer(k)
        g.format(k)
        score = _penalite(g.m)
        if meilleur is None or score < meilleur[0]:
            meilleur = (score, [r[:] for r in g.m])
        g.masquer(k)  # le masque est son propre inverse
    return meilleur[1]


def svg(texte: str, marge: int = 4) -> str:
    """Code QR en SVG (un seul chemin, mise à l'échelle par le conteneur)."""
    m = matrice(texte)
    n = len(m) + 2 * marge
    d = "".join(f"M{x + marge} {y + marge}h1v1h-1z" for y, r in enumerate(m) for x, c in enumerate(r) if c)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {n} {n}" shape-rendering="crispEdges">'
            f'<rect width="{n}" height="{n}" fill="#fff"/><path d="{d}" fill="#000"/></svg>')


def png(texte: str, marge: int = 4, echelle: int = 8) -> bytes:
    """Code QR en PNG (niveaux de gris, 8 bits), pour l'envoi en image (Telegram) ; calculé sur le poste."""
    import struct
    import zlib
    m = matrice(texte)
    n = (len(m) + 2 * marge) * echelle
    blanc = [255] * (marge * echelle)
    lignes = []
    for y in range(-marge, len(m) + marge):
        r = m[y] if 0 <= y < len(m) else None
        pixels = bytes(blanc + [0 if c else 255 for c in (r or []) for _ in range(echelle)]
                       + blanc) if r else bytes([255] * n)
        lignes += [b"\x00" + pixels] * echelle

    def bloc(type_: bytes, donnees: bytes) -> bytes:
        return struct.pack(">I", len(donnees)) + type_ + donnees + struct.pack(">I", zlib.crc32(type_ + donnees))

    return (b"\x89PNG\r\n\x1a\n" + bloc(b"IHDR", struct.pack(">IIBBBBB", n, n, 8, 0, 0, 0, 0))
            + bloc(b"IDAT", zlib.compress(b"".join(lignes))) + bloc(b"IEND", b""))
