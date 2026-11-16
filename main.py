#!/usr/bin/env python3
"""Koi Through the Moon - ai-excited-01, round 4.

A giant koi leaps through the full moon; its splashing water turns into
golden stars while a tiny lantern boat drifts far below. One focus, one
strong diagonal, one thrilling moment.

Pure Python standard library (math, os, random, struct, zlib). No network,
no files read, no timestamps in the output: running it twice writes
byte-identical PNG bytes.

Usage (mirrors the kit's local run):
    MAKEFUN_OUTPUT_DIR=out python3 main.py   # writes out/entry.png
Without MAKEFUN_OUTPUT_DIR it writes /output/entry.png, as the grader does.
"""

import math
import os
import random
import struct
import zlib

W = H = 1024
SEED = 20261117

px = bytearray(W * H * 3)


# ---------------------------------------------------------------- helpers
def clamp(v, lo=0.0, hi=1.0):
    return lo if v < lo else (hi if v > hi else v)


def lerp(a, b, t):
    return a + (b - a) * t


def mix(c1, c2, t):
    return (int(lerp(c1[0], c2[0], t)), int(lerp(c1[1], c2[1], t)),
            int(lerp(c1[2], c2[2], t)))


def put(x, y, r, g, b):
    if 0 <= x < W and 0 <= y < H:
        i = (y * W + x) * 3
        px[i] = r
        px[i + 1] = g
        px[i + 2] = b


def blend(x, y, r, g, b, a):
    """Normal alpha blend of one pixel; a in 0..1."""
    if a <= 0.0 or not (0 <= x < W and 0 <= y < H):
        return
    i = (y * W + x) * 3
    if a >= 1.0:
        px[i] = r
        px[i + 1] = g
        px[i + 2] = b
        return
    ia = 1.0 - a
    px[i] = int(px[i] * ia + r * a)
    px[i + 1] = int(px[i + 1] * ia + g * a)
    px[i + 2] = int(px[i + 2] * ia + b * a)


def add(x, y, r, g, b, a):
    """Additive blend (glow); a scales the added colour."""
    if a <= 0.0 or not (0 <= x < W and 0 <= y < H):
        return
    i = (y * W + x) * 3
    px[i] = min(255, px[i] + int(r * a))
    px[i + 1] = min(255, px[i + 1] + int(g * a))
    px[i + 2] = min(255, px[i + 2] + int(b * a))


def row_fill(y, c):
    """Fill a whole row with one colour (fast, C-level)."""
    i = y * W * 3
    px[i:i + W * 3] = bytes(c) * W


def disc(cx, cy, rad, c, a=1.0, soft=1.2):
    """Anti-aliased filled disc."""
    r0 = max(0, int(cx - rad - 2))
    r1 = min(W - 1, int(cx + rad + 2))
    y0 = max(0, int(cy - rad - 2))
    y1 = min(H - 1, int(cy + rad + 2))
    rr = rad * rad
    cr, cg, cb = c
    for y in range(y0, y1 + 1):
        dy = y - cy
        for x in range(r0, r1 + 1):
            dx = x - cx
            d = math.sqrt(dx * dx + dy * dy) - rad
            if d >= soft:
                continue
            cov = 1.0 if d <= -soft else clamp(0.5 - d / (2.0 * soft))
            blend(x, y, cr, cg, cb, a * cov)


def glow(cx, cy, rad, c, peak=0.85):
    """Soft radial additive glow, fading to zero at rad."""
    r0 = max(0, int(cx - rad))
    r1 = min(W - 1, int(cx + rad))
    y0 = max(0, int(cy - rad))
    y1 = min(H - 1, int(cy + rad))
    cr, cg, cb = c
    rr = rad * rad
    for y in range(y0, y1 + 1):
        dy = y - cy
        for x in range(r0, r1 + 1):
            dx = x - cx
            d2 = dx * dx + dy * dy
            if d2 >= rr:
                continue
            t = 1.0 - d2 / rr
            add(x, y, cr, cg, cb, peak * t * t)


def fill_poly(pts, c, a=1.0):
    """Scanline fill of a polygon (list of (x, y))."""
    if len(pts) < 3:
        return
    ys = [p[1] for p in pts]
    y0 = max(0, int(min(ys)))
    y1 = min(H - 1, int(max(ys)) + 1)
    n = len(pts)
    cr, cg, cb = c
    for y in range(y0, y1 + 1):
        xs = []
        for k in range(n):
            x1, y1p = pts[k]
            x2, y2p = pts[(k + 1) % n]
            if (y1p <= y < y2p) or (y2p <= y < y1p):
                xs.append(x1 + (y - y1p) * (x2 - x1) / (y2p - y1p))
        if len(xs) < 2:
            continue
        xs.sort()
        for j in range(0, len(xs) - 1, 2):
            xa = max(0, int(xs[j]))
            xb = min(W - 1, int(xs[j + 1]))
            if xb < xa:
                continue
            i = (y * W + xa) * 3
            span = xb - xa + 1
            if a >= 1.0:
                px[i:i + span * 3] = bytes((cr, cg, cb)) * span
            else:
                for x in range(xa, xb + 1):
                    blend(x, y, cr, cg, cb, a)


def stroke_polyline(pts, width, c, a=1.0):
    """Thick polyline drawn as overlapping discs (smooth joins)."""
    step = max(1.0, width * 0.45)
    for k in range(len(pts) - 1):
        x1, y1 = pts[k]
        x2, y2 = pts[k + 1]
        seg = math.hypot(x2 - x1, y2 - y1)
        n = max(1, int(seg / step))
        for s in range(n + 1):
            t = s / n
            disc(lerp(x1, x2, t), lerp(y1, y2, t), width * 0.5, c, a, soft=1.0)


def bezier(p0, p1, p2, p3, n):
    """Sample a cubic bezier into n+1 points."""
    out = []
    for s in range(n + 1):
        t = s / n
        u = 1.0 - t
        x = (u * u * u * p0[0] + 3 * u * u * t * p1[0] +
             3 * u * t * t * p2[0] + t * t * t * p3[0])
        y = (u * u * u * p0[1] + 3 * u * u * t * p1[1] +
             3 * u * t * t * p2[1] + t * t * t * p3[1])
        out.append((x, y))
    return out


def star4(cx, cy, r, c, a=1.0, squash=1.0, rot=0.0):
    """Four-point sparkle star (long thin points), filled polygon."""
    pts = []
    for k in range(8):
        ang = math.pi / 2 * k - math.pi / 2 + rot
        rr = r if k % 2 == 0 else r * 0.30
        pts.append((cx + math.cos(ang) * rr,
                    cy + math.sin(ang) * rr * squash))
    fill_poly(pts, c, a)

# ---------------------------------------------------------------- palette
INK = (16, 14, 42)          # deep night outline
SKY_TOP = (8, 12, 38)
SKY_MID = (24, 28, 74)
SKY_LOW = (58, 44, 96)
MOON = (250, 238, 200)      # pale gold moon face
MOON_SHADE = (228, 205, 150)
MOON_GLOW = (255, 214, 130)
GOLD = (255, 196, 66)
GOLD_DEEP = (232, 148, 32)
KOI_WHITE = (250, 246, 236)
KOI_ORANGE = (238, 84, 40)
KOI_ORANGE_D = (206, 58, 28)
KOI_BLACK = (28, 22, 30)
WATER_TOP = (20, 30, 68)
WATER_BOT = (8, 12, 34)
LANTERN = (255, 166, 66)

rng = random.Random(SEED)

HORIZON = 852
MOON_C = (612.0, 362.0)
MOON_R = 292.0


def draw_sky():
    for y in range(HORIZON):
        if y < 430:
            t = y / 430.0
            c = mix(SKY_TOP, SKY_MID, t * t * (3 - 2 * t))
        else:
            t = (y - 430) / (HORIZON - 430)
            c = mix(SKY_MID, SKY_LOW, t)
        row_fill(y, c)


def draw_stars():
    # faint field stars, denser away from the moon
    for _ in range(210):
        x = rng.uniform(0, W)
        y = rng.uniform(0, HORIZON - 60)
        d = math.hypot(x - MOON_C[0], y - MOON_C[1])
        if d < MOON_R + 40:
            continue
        r = rng.uniform(0.6, 1.9)
        bright = rng.uniform(0.35, 0.95)
        warm = rng.random() < 0.3
        c = (255, 226, 170) if warm else (214, 226, 255)
        disc(x, y, r, c, bright, soft=0.9)
        if r > 1.6 and rng.random() < 0.4:
            star4(x, y, r * 4.2, c, bright * 0.55)


def draw_moon():
    cx, cy = MOON_C
    # halo
    glow(cx, cy, MOON_R * 1.55, MOON_GLOW, peak=0.34)
    glow(cx, cy, MOON_R * 1.18, (255, 236, 180), peak=0.5)
    # face with a soft vertical gradient: brighter upper-left
    r0 = max(0, int(cx - MOON_R - 2))
    r1 = min(W - 1, int(cx + MOON_R + 2))
    y0 = max(0, int(cy - MOON_R - 2))
    y1 = min(H - 1, int(cy + MOON_R + 2))
    for y in range(y0, y1 + 1):
        dy = y - cy
        for x in range(r0, r1 + 1):
            dx = x - cx
            d = math.sqrt(dx * dx + dy * dy)
            if d > MOON_R + 1.0:
                continue
            t = clamp((dx * -0.45 + dy * 0.35) / MOON_R * 0.5 + 0.5)
            base = mix(MOON, MOON_SHADE, t * 0.55)
            # limb darkening at the rim
            rim = clamp((d - (MOON_R - 26)) / 26.0)
            base = mix(base, (214, 186, 128), rim * 0.5)
            cov = 1.0 if d <= MOON_R - 1.0 else clamp(0.5 - (d - MOON_R))
            blend(x, y, base[0], base[1], base[2], cov)
    # craters: soft darker patches, seeded, clipped inside the disc
    for _ in range(14):
        ang = rng.uniform(0, math.tau)
        rr = rng.uniform(0, MOON_R * 0.8)
        x = cx + math.cos(ang) * rr
        y = cy + math.sin(ang) * rr
        cr = rng.uniform(7, 22)
        if math.hypot(x - cx, y - cy) + cr > MOON_R - 8:
            continue
        disc(x, y, cr, (206, 178, 122), rng.uniform(0.08, 0.16), soft=cr * 0.35)


def cloud(cx, cy, w, h, a):
    """Soft translucent cloud from overlapping discs, faded at the ends."""
    n = 7
    for k in range(n):
        t = k / (n - 1)
        env = math.sin(t * math.pi)
        x = cx - w * 0.5 + t * w
        y = cy + math.sin(t * math.pi) * -h * 0.18 + rng.uniform(-3, 3)
        r = h * (0.6 + 0.55 * env)
        disc(x, y, r, (196, 206, 240), a * (0.3 + 0.7 * env), soft=r * 0.6)


def draw_clouds():
    cloud(300, 168, 330, 34, 0.06)
    cloud(820, 120, 260, 26, 0.05)
    # wisp crossing the moon's lower edge
    cloud(430, 596, 420, 40, 0.08)
    cloud(760, 660, 300, 30, 0.06)


def draw_water():
    # deep water with a warm tint near the moonlight column
    for y in range(HORIZON, H):
        t = (y - HORIZON) / (H - HORIZON)
        c = mix(WATER_TOP, WATER_BOT, t)
        row_fill(y, c)
    # moonlight column: shimmering gold path under the moon
    for y in range(HORIZON, H):
        prog = (y - HORIZON) / (H - HORIZON)
        half = 60 + prog * 150
        for x in range(int(MOON_C[0] - half), int(MOON_C[0] + half) + 1):
            if not (0 <= x < W):
                continue
            rel = abs(x - MOON_C[0]) / half
            wave = (math.sin(x * 0.11 + y * 0.35) * 0.5 + 0.5)
            wave *= (math.sin(x * 0.031 - y * 0.21) * 0.5 + 0.5)
            a = (1.0 - rel) * (0.22 + 0.38 * wave) * (1.0 - prog * 0.55)
            add(x, y, 255, 196, 90, a * 0.7)
    # ripple strokes: short bright dashes, denser in the column
    for _ in range(150):
        y = rng.randint(HORIZON + 6, H - 4)
        x = rng.uniform(30, W - 30)
        ln = rng.uniform(14, 70)
        near = clamp(1.0 - abs(x - MOON_C[0]) / 420.0)
        a = rng.uniform(0.10, 0.30) * (0.4 + 0.6 * near)
        c = (255, 214, 130) if rng.random() < near * 0.7 else (140, 170, 230)
        for s in range(int(ln)):
            blend(int(x + s), y, c[0], c[1], c[2], a)

# ---------------------------------------------------------------- the koi
# Spine: tail low in the water at bottom-left, arcing up through the moon,
# head bursting out of the moon's upper-right rim.
SPINE = bezier((190, 830), (230, 800), (380, 560), (878, 168), 140)


def radius_at(t):
    """Body radius along the spine (0 = tail, 1 = head)."""
    keys = [(0.00, 13), (0.10, 40), (0.25, 62), (0.42, 88),
            (0.58, 84), (0.72, 70), (0.86, 54), (1.00, 34)]
    for k in range(len(keys) - 1):
        t0, r0 = keys[k]
        t1, r1 = keys[k + 1]
        if t0 <= t <= t1:
            u = (t - t0) / (t1 - t0)
            u = u * u * (3 - 2 * u)
            return lerp(r0, r1, u)
    return keys[-1][1]


def spine_frame(t):
    """Point, unit tangent and unit normal at spine parameter t."""
    n = len(SPINE) - 1
    f = t * n
    k = min(int(f), n - 1)
    u = f - k
    x = lerp(SPINE[k][0], SPINE[k + 1][0], u)
    y = lerp(SPINE[k][1], SPINE[k + 1][1], u)
    dx = SPINE[k + 1][0] - SPINE[k][0]
    dy = SPINE[k + 1][1] - SPINE[k][1]
    ln = math.hypot(dx, dy) or 1.0
    return (x, y), (dx / ln, dy / ln), (-dy / ln, dx / ln)


def band_poly(t0, t1, inset, side=0):
    """Polygon strip along the spine between t0 and t1.
    side: 0 = full width, 1 = upper side only, -1 = lower side only."""
    left, right = [], []
    steps = 24
    for s in range(steps + 1):
        t = lerp(t0, t1, s / steps)
        (x, y), _, (nx, ny) = spine_frame(t)
        r = radius_at(t) * inset
        left.append((x + nx * r, y + ny * r))
        right.append((x - nx * r, y - ny * r))
    if side == 1:
        mid = []
        for s in range(steps + 1):
            t = lerp(t0, t1, s / steps)
            (x, y), _, _ = spine_frame(t)
            mid.append((x, y))
        return left + list(reversed(mid))
    if side == -1:
        mid = []
        for s in range(steps + 1):
            t = lerp(t0, t1, s / steps)
            (x, y), _, _ = spine_frame(t)
            mid.append((x, y))
        return list(reversed(right)) + mid
    return left + list(reversed(right))


def patch_blobs(t0, t1, c, inset=0.82, bias=0.0, a=1.0):
    """Organic colour patch: union of discs along the spine segment.
    bias shifts the patch toward one side of the body (-1..1)."""
    n = max(4, int((t1 - t0) * 160))
    for s in range(n + 1):
        t = lerp(t0, t1, s / n)
        (x, y), _, (nx, ny) = spine_frame(t)
        r = radius_at(t) * inset * (0.82 + 0.18 * math.sin(t * 57.0 + 1.3))
        disc(x + nx * r * bias, y + ny * r * bias, r * 0.94, c, a, soft=2.5)


def draw_koi():
    # outline: body band slightly wider, in dark ink
    fill_poly(band_poly(0.0, 1.0, 1.045), INK)
    # body
    fill_poly(band_poly(0.0, 1.0, 1.0), KOI_WHITE)
    # rounded head cap: a white disc centred on the spine end, rounding
    # the snout off. No ink ring: the body's own outline runs into it.
    (hx, hy), htang, (hnx, hny) = spine_frame(1.0)
    hr = radius_at(1.0)
    disc(hx, hy, hr, KOI_WHITE, 1.0, soft=1.4)
    # belly light: warm gold wash along the lower side
    fill_poly(band_poly(0.12, 0.97, 0.97, side=-1), (255, 226, 160), 0.5)
    # kohaku orange patches (organic blobs, not rectangles)
    patch_blobs(0.17, 0.29, KOI_ORANGE, inset=0.68, bias=0.18)
    patch_blobs(0.51, 0.61, KOI_ORANGE, inset=0.70, bias=-0.10)
    patch_blobs(0.81, 0.90, KOI_ORANGE, inset=0.66, bias=0.22)
    patch_blobs(0.63, 0.70, KOI_ORANGE_D, inset=0.52, bias=-0.35)
    # black accents
    patch_blobs(0.38, 0.43, KOI_BLACK, inset=0.42, bias=0.35)
    patch_blobs(0.72, 0.76, KOI_BLACK, inset=0.40, bias=-0.4)
    # scale shimmer: faint arcs along the back, white areas only
    for k in range(26):
        t = 0.08 + k * 0.032
        if (0.16 <= t <= 0.36) or (0.50 <= t <= 0.64) or (0.80 <= t <= 0.94):
            continue
        (x, y), _, (nx, ny) = spine_frame(t)
        r = radius_at(t)
        disc(x + nx * r * 0.45, y + ny * r * 0.45, 4.0,
             (226, 214, 196), 0.18, soft=2.0)
    # dorsal fin: curved blade along the upper edge, swept back
    (bx, by), _, (nx, ny) = spine_frame(0.34)
    (cx2, cy2), _, _ = spine_frame(0.55)
    fin = [(bx + nx * 50, by + ny * 50),
           (bx + nx * 150, by + ny * 100 - 52),
           (bx + nx * 205, by + ny * 135 - 150),
           (cx2 + nx * 120, cy2 + ny * 84),
           (cx2 + nx * 52, cy2 + ny * 52)]
    fill_poly(fin, KOI_ORANGE)
    stroke_polyline(fin, 3.0, INK, 0.85)
    # pectoral fin near the head, sweeping down-back
    (px0, py0), ptang, (pnx, pny) = spine_frame(0.84)
    pfin = [(px0 - pnx * 10, py0 - pny * 10),
            (px0 - pnx * 110 - ptang[0] * 36, py0 - pny * 110 - ptang[1] * 36 + 62),
            (px0 - pnx * 158 - ptang[0] * 96, py0 - pny * 158 - ptang[1] * 96 + 118),
            (px0 - pnx * 66 - ptang[0] * 16, py0 - pny * 66 - ptang[1] * 16 + 54)]
    fill_poly(pfin, (250, 150, 80))
    stroke_polyline(pfin, 3.0, INK, 0.85)
    # tail fin: two wide flowing fan blades behind the tail base.
    # Attach points straddle the tail width; each blade fans out to a tip.
    (tx, ty), ttang, (tnx, tny) = spine_frame(0.0)
    bd = (-ttang[0], -ttang[1])  # backward along the spine
    a_up = (tx - tnx * 12, ty - tny * 12)
    a_dn = (tx + tnx * 12, ty + tny * 12)
    tip_up = (tx + bd[0] * 140 - tnx * 70, ty + bd[1] * 140 - tny * 70)
    tip_dn = (tx + bd[0] * 150 + tnx * 80, ty + bd[1] * 150 + tny * 80)
    upper = [a_up,
             (tx + bd[0] * 60 - tnx * 50, ty + bd[1] * 60 - tny * 50),
             tip_up,
             (tx + bd[0] * 80 + tnx * 5, ty + bd[1] * 80 + tny * 5),
             a_dn]
    lower = [a_dn,
             (tx + bd[0] * 70 + tnx * 55, ty + bd[1] * 70 + tny * 55),
             tip_dn,
             (tx + bd[0] * 90 - tnx * 5, ty + bd[1] * 90 - tny * 5),
             a_up]
    fill_poly(upper, (250, 130, 60))
    fill_poly(lower, (238, 96, 44))
    stroke_polyline(upper, 3.0, INK, 0.8)
    stroke_polyline(lower, 3.0, INK, 0.8)
    # eye, on the upper side of the head
    (ex, ey), _, (enx, eny) = spine_frame(0.955)
    ex += enx * 15
    ey += eny * 15
    disc(ex, ey, 10.5, KOI_BLACK, 1.0, soft=1.4)
    disc(ex - 3, ey - 3, 3.6, (255, 255, 255), 1.0, soft=1.0)
    disc(ex + 2.5, ey + 2.5, 1.8, (255, 220, 120), 0.9, soft=0.8)


def draw_splash_and_stars():
    # water burst where the tail leaves the water
    (tx, ty), _, _ = spine_frame(0.02)
    glow(tx, ty - 10, 90, (150, 190, 255), peak=0.30)
    for _ in range(46):
        ang = rng.uniform(-2.6, -0.4)
        dist = rng.uniform(8, 150)
        x = tx + math.cos(ang) * dist * 1.15
        y = ty + math.sin(ang) * dist * 0.75 - 8
        r = rng.uniform(2.0, 9.0) * (1.0 - dist / 220.0) + 1.5
        disc(x, y, r, (226, 238, 255), rng.uniform(0.5, 0.95), soft=1.2)
        disc(x - r * 0.3, y - r * 0.3, r * 0.4, (255, 255, 255), 0.7, soft=0.8)
    # droplets trailing the koi's underside, rising along the arc
    for k in range(34):
        t = rng.uniform(0.03, 0.52)
        (x, y), _, (nx, ny) = spine_frame(t)
        off = rng.uniform(0.9, 1.7) * radius_at(t)
        dx = x - nx * off + rng.uniform(-14, 14)
        dy = y - ny * off + rng.uniform(-10, 26)
        r = rng.uniform(2.5, 8.5)
        disc(dx, dy, r, (210, 228, 255), rng.uniform(0.55, 0.95), soft=1.2)
    # droplets become gold stars as they rise past the moon
    for k in range(30):
        t = rng.uniform(0.42, 1.0)
        (x, y), _, (nx, ny) = spine_frame(t)
        off = rng.uniform(0.95, 1.9) * radius_at(t)
        sx = x - nx * off + rng.uniform(-30, 30)
        sy = y - ny * off + rng.uniform(-34, 20)
        r = rng.uniform(5, 15) * (0.6 + 0.7 * t)
        glow(sx, sy, r * 2.0, GOLD, peak=0.32)
        star4(sx, sy, r, GOLD, 0.95, rot=rng.uniform(0, 1.57))
        star4(sx, sy, r * 0.45, (255, 240, 190), 1.0, rot=rng.uniform(0, 1.57))
    # a bright burst where the head breaks out of the moon
    (hx, hy), _, _ = spine_frame(0.99)
    glow(hx, hy, 90, GOLD, peak=0.32)
    for k in range(12):
        ang = rng.uniform(0, math.tau)
        d = rng.uniform(30, 105)
        star4(hx + math.cos(ang) * d, hy + math.sin(ang) * d,
              rng.uniform(6, 14), GOLD, 0.9, rot=rng.uniform(0, 1.57))

# ---------------------------------------------------------------- lantern boat
def draw_boat():
    bx, by = 742.0, 936.0
    # warm halo of the lantern on the water
    glow(bx, by - 52, 95, LANTERN, peak=0.42)
    # hull: small wooden boat, bow tipped up
    hull = [(bx - 78, by - 14), (bx + 82, by - 14), (bx + 66, by + 12),
            (bx + 34, by + 20), (bx - 44, by + 20), (bx - 66, by + 10)]
    fill_poly(hull, (74, 44, 28))
    fill_poly([(bx - 78, by - 14), (bx + 82, by - 14), (bx + 74, by - 2),
               (bx - 70, by - 2)], (112, 66, 40))
    stroke_polyline(hull, 2.5, INK, 0.8)
    # mast + paper lantern
    stroke_polyline([(bx, by - 12), (bx, by - 74)], 4.0, (52, 32, 20))
    disc(bx, by - 52, 21, (255, 196, 110), 1.0, soft=1.5)
    disc(bx, by - 52, 15, (255, 226, 150), 1.0, soft=1.2)
    disc(bx, by - 52, 8, (255, 246, 200), 1.0, soft=1.0)
    disc(bx, by - 74, 3.5, (255, 180, 80), 1.0, soft=1.0)
    # tiny silhouetted rower
    disc(bx - 26, by - 30, 7, INK, 1.0, soft=1.2)
    fill_poly([(bx - 34, by - 24), (bx - 18, by - 24), (bx - 14, by - 12),
               (bx - 38, by - 12)], INK)
    # lantern reflection shimmering down the water
    for k in range(26):
        y = int(by + 26 + k * 2)
        if y >= H - 2:
            break
        wdt = 8 + k * 1.1
        a = 0.34 * (1.0 - k / 30.0)
        for s in range(int(wdt)):
            x = int(bx + rng.uniform(-1, 1) * wdt * 0.4 + s - wdt / 2)
            add(x, y, 255, 170, 70, a * rng.uniform(0.4, 1.0))


# ---------------------------------------------------------------- PNG writer
def png_bytes(w, h, data):
    raw = bytearray()
    for y in range(h):
        raw.append(0)  # filter: None
        raw += data[y * w * 3:(y + 1) * w * 3]
    comp = zlib.compress(bytes(raw), 9)

    def chunk(tag, payload):
        out = struct.pack(">I", len(payload)) + tag + payload
        return out + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)

    out = b"\x89PNG\r\n\x1a\n"
    out += chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
    out += chunk(b"IDAT", comp)
    out += chunk(b"IEND", b"")
    return out


def main():
    draw_sky()
    draw_stars()
    draw_moon()
    draw_clouds()
    draw_water()
    draw_koi()
    draw_splash_and_stars()
    draw_boat()
    outdir = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")
    os.makedirs(outdir, exist_ok=True)
    path = os.path.join(outdir, "entry.png")
    with open(path, "wb") as f:
        f.write(png_bytes(W, H, px))


if __name__ == "__main__":
    main()
