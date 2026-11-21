#!/usr/bin/env python3
"""The Passport Page of a Country That Isn't There.

Draws one invented passport spread (1024x720 PNG) for the fictional
Republic of Zalvaria, using only the Python standard library, and writes
it to /output/entry.png.

Everything is drawn procedurally: paper, guilloche, an engraved-style
profile portrait, data fields, a machine-readable zone with real ICAO
check digits, and a set of mutually consistent entry/exit stamps and a
visa from the neighbouring countries Veldoria, Thalassa and Ostmarck.
All dates agree: issued 02 FEB 2021, every stamp after that date and
before the 01 FEB 2031 expiry.
"""

import math
import os
import struct
import sys
import zlib

W, H = 1024, 720
OUT = "/output/entry.png"

# ---------------------------------------------------------------- PNG writer

def _png_chunk(ctype, data):
    chunk = ctype + data
    return struct.pack(">I", len(data)) + chunk + struct.pack(">I", zlib.crc32(chunk) & 0xFFFFFFFF)


def write_png(path, width, height, rgb):
    """rgb: bytes, width*height*3. Filter 0 rows, zlib level 9."""
    raw = bytearray()
    stride = width * 3
    for y in range(height):
        raw.append(0)
        raw += rgb[y * stride:(y + 1) * stride]
    comp = zlib.compress(bytes(raw), 9)
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        f.write(_png_chunk(b"IHDR", ihdr))
        f.write(_png_chunk(b"IDAT", comp))
        f.write(_png_chunk(b"IEND", b""))


# ---------------------------------------------------------------- canvas

def rgb(r, g, b):
    return (r, g, b)


class Canvas:
    def __init__(self, w, h, bg):
        self.w, self.h = w, h
        self.px = bytearray(bytes(bg) * (w * h))

    def _idx(self, x, y):
        return (y * self.w + x) * 3

    def set(self, x, y, c):
        if 0 <= x < self.w and 0 <= y < self.h:
            i = self._idx(x, y)
            self.px[i] = c[0]
            self.px[i + 1] = c[1]
            self.px[i + 2] = c[2]

    def get(self, x, y):
        i = self._idx(x, y)
        return (self.px[i], self.px[i + 1], self.px[i + 2])

    def blend(self, x, y, c, a):
        """Blend colour c over the pixel with alpha a (0..255)."""
        if 0 <= x < self.w and 0 <= y < self.h and a:
            i = self._idx(x, y)
            inv = 255 - a
            self.px[i] = (c[0] * a + self.px[i] * inv) // 255
            self.px[i + 1] = (c[1] * a + self.px[i + 1] * inv) // 255
            self.px[i + 2] = (c[2] * a + self.px[i + 2] * inv) // 255

    def fill_rect(self, x0, y0, x1, y1, c):
        x0 = max(0, x0); y0 = max(0, y0)
        x1 = min(self.w, x1); y1 = min(self.h, y1)
        if x1 <= x0 or y1 <= y0:
            return
        row = bytes(c) * (x1 - x0)
        for y in range(y0, y1):
            i = self._idx(x0, y)
            self.px[i:i + len(row)] = row

    def hline(self, x0, x1, y, c, t=1):
        for yy in range(y, y + t):
            self.fill_rect(x0, yy, x1, yy + 1, c)

    def vline(self, x, y0, y1, c, t=1):
        for xx in range(x, x + t):
            self.fill_rect(xx, y0, xx + 1, y1, c)

    def rect(self, x0, y0, x1, y1, c, t=1):
        self.hline(x0, x1, y0, c, t)
        self.hline(x0, x1, y1 - t, c, t)
        self.vline(x0, y0, y1, c, t)
        self.vline(x1 - t, y0, y1, c, t)

    def disc(self, cx, cy, r, c):
        if r <= 0:
            self.set(cx, cy, c)
            return
        r2 = r * r
        for dy in range(-r, r + 1):
            dx = int(math.sqrt(r2 - dy * dy))
            self.fill_rect(cx - dx, cy + dy, cx + dx + 1, cy + dy + 1, c)

    def line(self, x0, y0, x1, y1, c, t=1):
        """Bresenham line with round caps of thickness t."""
        dx = x1 - x0
        dy = y1 - y0
        steps = max(abs(dx), abs(dy), 1)
        r = max(0, t // 2)
        for s in range(steps + 1):
            x = x0 + dx * s // steps
            y = y0 + dy * s // steps
            if r:
                self.disc(x, y, r, c)
            else:
                self.set(x, y, c)

    def circle(self, cx, cy, r, c, t=1):
        if r <= 0:
            return
        x = 0
        y = r
        d = 1 - r
        while x <= y:
            for px, py in ((cx + x, cy + y), (cx - x, cy + y), (cx + x, cy - y),
                           (cx - x, cy - y), (cx + y, cy + x), (cx - y, cy + x),
                           (cx + y, cy - x), (cx - y, cy - x)):
                if t > 1:
                    self.disc(px, py, t // 2, c)
                else:
                    self.set(px, py, c)
            if d < 0:
                d += 2 * x + 3
            else:
                d += 2 * (x - y) + 5
                y -= 1
            x += 1

    def arc(self, cx, cy, r, a0, a1, c, t=1):
        """Arc from angle a0 to a1 (radians), 0 = east, positive clockwise (y down)."""
        if a1 < a0:
            a0, a1 = a1, a0
        n = max(2, int(abs(a1 - a0) * r))
        for i in range(n + 1):
            a = a0 + (a1 - a0) * i / n
            x = int(round(cx + r * math.cos(a)))
            y = int(round(cy + r * math.sin(a)))
            if t > 1:
                self.disc(x, y, t // 2, c)
            else:
                self.set(x, y, c)

    def polyfill(self, pts, c):
        """Scanline fill of a simple polygon (list of (x, y))."""
        if len(pts) < 3:
            return
        ys = [p[1] for p in pts]
        ymin, ymax = min(ys), max(ys)
        n = len(pts)
        for y in range(ymin, ymax + 1):
            xs = []
            for i in range(n):
                x0, y0 = pts[i]
                x1, y1 = pts[(i + 1) % n]
                if (y0 <= y < y1) or (y1 <= y < y0):
                    if y1 != y0:
                        xs.append(x0 + (y - y0) * (x1 - x0) / (y1 - y0))
            xs.sort()
            for i in range(0, len(xs) - 1, 2):
                self.fill_rect(int(math.ceil(xs[i])), y, int(math.floor(xs[i + 1])) + 1, y + 1, c)

    def polyline(self, pts, c, t=1, closed=False):
        seq = pts + [pts[0]] if closed and len(pts) > 2 else pts
        for a, b in zip(seq, seq[1:]):
            self.line(a[0], a[1], b[0], b[1], c, t)


# ---------------------------------------------------------------- stroke font
# Hand-drawn single-stroke capitals on a 5 x 7 grid (x 0..4, y 0..6).
# Each glyph: "M x,y L x,y ..." polylines, separated by " | ".
FONT = {
    "A": "M0,6 L2,0 L4,6 | M1,4 L3,4",
    "B": "M0,0 L0,6 L3,6 L4,5 L4,4 L3,3 L0,3 | M3,3 L4,2 L4,1 L3,0 L0,0",
    "C": "M4,1 L3,0 L1,0 L0,1 L0,5 L1,6 L3,6 L4,5",
    "D": "M0,0 L0,6 L2,6 L4,4 L4,2 L2,0 L0,0",
    "E": "M4,0 L0,0 L0,6 L4,6 | M0,3 L3,3",
    "F": "M0,0 L0,6 | M0,0 L4,0 | M0,3 L3,3",
    "G": "M4,1 L3,0 L1,0 L0,1 L0,5 L1,6 L3,6 L4,5 L4,3 L2,3",
    "H": "M0,0 L0,6 | M4,0 L4,6 | M0,3 L4,3",
    "I": "M2,0 L2,6 | M0,0 L4,0 | M0,6 L4,6",
    "J": "M1,0 L4,0 | M4,0 L4,5 L3,6 L1,6 L0,5",
    "K": "M0,0 L0,6 | M4,0 L0,3 L4,6",
    "L": "M0,0 L0,6 L4,6",
    "M": "M0,6 L0,0 L2,3 L4,0 L4,6",
    "N": "M0,6 L0,0 L4,6 L4,0",
    "O": "M1,0 L3,0 L4,1 L4,5 L3,6 L1,6 L0,5 L0,1 L1,0",
    "P": "M0,6 L0,0 L3,0 L4,1 L4,2 L3,3 L0,3",
    "Q": "M1,0 L3,0 L4,1 L4,5 L3,6 L1,6 L0,5 L0,1 L1,0 | M3,4 L4,6",
    "R": "M0,6 L0,0 L3,0 L4,1 L4,2 L3,3 L0,3 | M2,3 L4,6",
    "S": "M4,1 L3,0 L1,0 L0,1 L0,2 L1,3 L3,3 L4,4 L4,5 L3,6 L1,6 L0,5",
    "T": "M0,0 L4,0 | M2,0 L2,6",
    "U": "M0,0 L0,5 L1,6 L3,6 L4,5 L4,0",
    "V": "M0,0 L2,6 L4,0",
    "W": "M0,0 L1,6 L2,3 L3,6 L4,0",
    "X": "M0,0 L4,6 | M4,0 L0,6",
    "Y": "M0,0 L2,3 L4,0 | M2,3 L2,6",
    "Z": "M0,0 L4,0 L0,6 L4,6",
    "0": "M1,0 L3,0 L4,1 L4,5 L3,6 L1,6 L0,5 L0,1 L1,0 | M1,5 L3,1",
    "1": "M1,1 L2,0 L2,6 | M0,6 L4,6",
    "2": "M0,1 L1,0 L3,0 L4,1 L4,2 L3,3 L0,6 L4,6",
    "3": "M0,0 L3,0 L4,1 L4,2 L3,3 | M3,3 L4,4 L4,5 L3,6 L0,6",
    "4": "M3,0 L0,4 L4,4 | M3,0 L3,6",
    "5": "M4,0 L0,0 L0,3 L3,3 L4,4 L4,5 L3,6 L0,6",
    "6": "M4,1 L3,0 L1,0 L0,1 L0,5 L1,6 L3,6 L4,5 L4,4 L3,3 L0,3",
    "7": "M0,0 L4,0 L2,6",
    "8": "M1,0 L3,0 L4,1 L4,2 L3,3 L1,3 L0,2 L0,1 L1,0 | M1,3 L3,3 L4,4 L4,5 L3,6 L1,6 L0,5 L0,4 L1,3",
    "9": "M0,5 L0,2 L1,0 L3,0 L4,1 L4,5 L3,6 L1,6 L0,5 | M4,3 L1,3",
    "<": "M4,1 L1,3 L4,5",
    ">": "M0,1 L3,3 L0,5",
    "-": "M0,3 L4,3",
    "/": "M4,6 L0,0",
    ".": "M2,6 L2,6",
    ",": "M2,5 L1,6",
    "'": "M2,0 L2,2",
    "(": "M3,0 L2,1 L2,5 L3,6",
    ")": "M1,0 L2,1 L2,5 L1,6",
    ":": "M2,2 L2,2 | M2,4 L2,4",
    "+": "M2,1 L2,5 | M0,3 L4,3",
    "=": "M0,2 L4,2 | M0,4 L4,4",
    "!": "M2,0 L2,4 | M2,6 L2,6",
    " ": "",
}


def _parse_glyph(spec):
    """Return list of polylines; each a list of (x, y) grid points."""
    strokes = []
    for part in spec.split("|"):
        pts = []
        for tok in part.strip().split():
            cmd, xy = tok[0], tok[1:]
            x, y = (int(v) for v in xy.split(","))
            pts.append((x, y))
        if pts:
            strokes.append(pts)
    return strokes


_GLYPHS = {ch: _parse_glyph(spec) for ch, spec in FONT.items()}


def text_size(text, scale, spacing=None):
    """Width/height in px of text at given scale (scale = px per grid unit)."""
    if spacing is None:
        spacing = scale
    w = 0
    for ch in text:
        w += 5 * scale + spacing
    return (max(0, w - spacing) if text else 0, 7 * scale)


def draw_text_aa(cv, x, y, text, scale, color, spacing=None, align="left"):
    """Draw text with 2x supersampled anti-aliasing.

    Renders the string into a small offscreen buffer at 2x, then blends
    the downsampled coverage onto the canvas. scale is px per grid unit.
    """
    if not text:
        return
    if spacing is None:
        spacing = scale
    tw, th = text_size(text, scale, spacing)
    if tw <= 0:
        return
    if align == "center":
        x -= tw // 2
    elif align == "right":
        x -= tw
    ss = 2  # supersample factor
    bw, bh = tw * ss, th * ss
    # coverage buffer, 0..255
    cov = bytearray(bw * bh)
    lw = max(1, scale * ss // 3)  # stroke width in supersampled px
    cx = 0
    for ch in text:
        strokes = _GLYPHS.get(ch.upper(), [])
        for pts in strokes:
            for (ax, ay), (bx, by) in zip(pts, pts[1:]):
                _aa_line(cov, bw, bh, cx + ax * scale * ss, ay * scale * ss,
                         cx + bx * scale * ss, by * scale * ss, lw)
            if len(pts) == 1:
                px, py = pts[0]
                _aa_disc(cov, bw, bh, cx + px * scale * ss, py * scale * ss,
                         max(1, lw))
        cx += 5 * scale * ss + spacing * ss
    # downsample 2x2 -> blend onto canvas
    for yy in range(th):
        for xx in range(tw):
            a = (cov[(2 * yy) * bw + 2 * xx] + cov[(2 * yy) * bw + 2 * xx + 1]
                 + cov[(2 * yy + 1) * bw + 2 * xx] + cov[(2 * yy + 1) * bw + 2 * xx + 1]) // 4
            if a:
                cv.blend(x + xx, y + yy, color, a)


def _aa_line(cov, w, h, x0, y0, x1, y1, lw):
    dx = x1 - x0
    dy = y1 - y0
    steps = max(abs(dx), abs(dy), 1)
    r = max(0, lw // 2)
    for s in range(steps + 1):
        x = x0 + dx * s // steps
        y = y0 + dy * s // steps
        _aa_disc(cov, w, h, x, y, r)


def _aa_disc(cov, w, h, cx, cy, r):
    for dy in range(-r, r + 1):
        dx = int((r * r - dy * dy) ** 0.5)
        yy = cy + dy
        if 0 <= yy < h:
            base = yy * w
            for xx in range(cx - dx, cx + dx + 1):
                if 0 <= xx < w:
                    cov[base + xx] = 255


# ---------------------------------------------------------------- palette
PAPER = (246, 241, 227)      # warm passport paper
PAPER_DK = (232, 224, 200)   # slightly darker paper
INK = (31, 42, 68)           # deep navy ink
INK_SOFT = (74, 88, 120)     # softer navy for labels
GOLD = (166, 124, 46)        # emblem gold
BURGUNDY = (122, 34, 48)     # cover burgundy
TEAL = (31, 111, 107)        # stamp teal
PURPLE = (91, 58, 140)       # stamp violet
BLUE = (39, 75, 143)         # stamp blue
GREEN = (46, 110, 62)        # visa green
GUILLOCHE = (214, 203, 168)  # pale guilloche lines
GUILLOCHE2 = (226, 216, 186)
FAINT = (196, 186, 152)      # faint rules


# ---------------------------------------------------------------- guilloche

def guilloche(cv, x0, y0, x1, y1, color, step=9, corners=None):
    """Fine concentric arcs from the given page corners, clipped to the rect."""
    if corners is None:
        corners = [(x0, y0), (x1, y0), (x0, y1), (x1, y1)]
    maxr = int(((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5)
    for cx, cy in corners:
        r = step
        while r < maxr:
            # only the quarter-arc that sweeps across the page
            if cx == x0 and cy == y0:
                a0, a1 = 0.0, math.pi / 2
            elif cx == x1 and cy == y0:
                a0, a1 = math.pi / 2, math.pi
            elif cx == x0 and cy == y1:
                a0, a1 = -math.pi / 2, 0.0
            else:
                a0, a1 = math.pi, math.pi * 1.5
            # plot point by point, clipped to the rect
            n = max(2, int(abs(a1 - a0) * r))
            for i in range(n + 1):
                a = a0 + (a1 - a0) * i / n
                x = int(round(cx + r * math.cos(a)))
                y = int(round(cy + r * math.sin(a)))
                if x0 <= x < x1 and y0 <= y < y1:
                    cv.set(x, y, color)
            r += step


def guilloche_field(cv, x0, y0, x1, y1, color):
    """Overlapping wavy lines (rosette-free) for the photo background."""
    for k in range(0, (y1 - y0) + (x1 - x0), 7):
        pts = []
        for x in range(x0, x1 + 1, 8):
            y = y0 + k - (x - x0) + int(5 * math.sin((x - x0) / 23.0))
            pts.append((x, y))
        # clip polyline to the rect by drawing only in-range points
        for (ax, ay), (bx, by) in zip(pts, pts[1:]):
            if y0 <= ay <= y1 and y0 <= by <= y1:
                cv.line(ax, ay, bx, by, color, 1)


# ---------------------------------------------------------------- coat of arms

def coat_of_arms(cv, cx, cy, s):
    """Zalvaria's arms: a shield with a star over three mountain peaks."""
    # shield outline (width ~ 3.4s, height ~ 4s)
    w = 1.7 * s
    h = 2.0 * s
    pts = [
        (cx - w, cy - h), (cx + w, cy - h), (cx + w, cy + 0.4 * h),
        (cx, cy + h), (cx - w, cy + 0.4 * h),
    ]
    cv.polyfill([(int(x), int(y)) for x, y in pts], (233, 224, 196))
    cv.polyline([(int(x), int(y)) for x, y in pts], GOLD, 2, closed=True)
    cv.polyline([(int(x), int(y)) for x, y in pts], INK, 1, closed=True)
    # three peaks
    base = cy + 0.75 * h
    for i, (dx, ph) in enumerate(((-0.95, 0.75), (0.0, 1.15), (0.95, 0.6))):
        px = cx + dx * s
        cv.polyfill([
            (int(px - 0.75 * s), int(base)), (int(px), int(base - ph * s)),
            (int(px + 0.75 * s), int(base)),
        ], INK)
    # star above the peaks
    sx, sy, sr = cx, cy - 0.55 * h, 0.55 * s
    star = []
    for i in range(10):
        ang = -math.pi / 2 + i * math.pi / 5
        rr = sr if i % 2 == 0 else sr * 0.42
        star.append((int(sx + rr * math.cos(ang)), int(sy + rr * math.sin(ang))))
    cv.polyfill(star, GOLD)
    # supporters: two laurel sprigs
    for side in (-1, 1):
        for i in range(3):
            yy = cy - 0.1 * h + i * 0.35 * s
            xx = cx + side * (1.35 * s + i * 0.1 * s)
            cv.line(int(xx), int(yy), int(xx + side * 0.3 * s),
                    int(yy - 0.25 * s), TEAL, 1)


# ---------------------------------------------------------------- portrait

def portrait(cv, x0, y0, x1, y1):
    """Engraved-style profile portrait: dark silhouette on guilloche."""
    cv.fill_rect(x0, y0, x1, y1, (238, 231, 209))
    guilloche_field(cv, x0, y0, x1, y1, GUILLOCHE2)
    # head profile, facing left (polygon in the photo box's own coords)
    # box-local: head centre ~ (95, 80), head ~ 80 wide, 125 tall
    def P(px, py):
        return (x0 + int(px * (x1 - x0) / 190.0), y0 + int(py * (y1 - y0) / 240.0))
    head = [P(92, 12), P(120, 18), P(136, 36), P(140, 60), P(132, 88),
            P(122, 104), P(112, 118), P(102, 130), P(92, 134), P(86, 128),
            P(82, 122), P(78, 116), P(70, 110), P(62, 102), P(70, 88),
            P(68, 78), P(72, 60), P(78, 40), P(86, 22)]
    cv.polyfill(head, INK)
    # hair: a bob swept over the top and back of the head
    hair = [P(80, 30), P(95, 12), P(120, 16), P(136, 34), P(140, 58),
            P(134, 84), P(128, 96), P(126, 70), P(130, 46), P(116, 26),
            P(96, 18), P(84, 22)]
    cv.polyfill(hair, (58, 44, 34))
    # neck + shoulders
    shoulders = [P(70, 134), P(66, 168), P(34, 198), P(22, 240), P(168, 240),
                 P(156, 198), P(124, 168), P(106, 140), P(98, 134)]
    cv.polyfill(shoulders, INK)
    # collar line
    cv.line(P(66, 150)[0], P(66, 150)[1], P(104, 150)[0], P(104, 150)[1],
            PAPER, 2)
    # earring: a small gold dot
    cv.disc(P(116, 88)[0], P(116, 88)[1], 2, GOLD)
    # photo frame: double rule + corner marks
    cv.rect(x0, y0, x1, y1, INK, 2)
    cv.rect(x0 + 4, y0 + 4, x1 - 4, y1 - 4, GOLD, 1)


# ---------------------------------------------------------------- stamps

def oval_stamp(cv, cx, cy, rx, ry, color, lines, scale=2, tilt=0):
    """Oval border stamp with centred horizontal text lines.

    lines: list of (text, scale) or (text, scale, spacing) drawn stacked,
    centred on (cx, cy).
    """
    # ellipse border: draw with parametric points
    for rr in (0, 3):
        pts = []
        for k in range(140):
            a = 2 * math.pi * k / 140
            pts.append((int(cx + (rx - rr) * math.cos(a)),
                        int(cy + (ry - rr) * math.sin(a))))
        cv.polyline(pts, color, 2, closed=True)
    total_h = sum(text_size(t, s, sp)[1] + 4
                  for t, s, sp in (ln if len(ln) == 3 else (ln[0], ln[1], None)
                                   for ln in lines)) - 4
    y = cy - total_h // 2
    for ln in lines:
        t, s = ln[0], ln[1]
        sp = ln[2] if len(ln) == 3 else None
        draw_text_aa(cv, cx, y, t, s, color, spacing=sp, align="center")
        y += text_size(t, s, sp)[1] + 4


def rect_stamp(cv, x0, y0, x1, y1, color, lines, scale=2):
    """Rectangular stamp with a double rule and centred text lines."""
    cv.rect(x0, y0, x1, y1, color, 2)
    cv.rect(x0 + 4, y0 + 4, x1 - 4, y1 - 4, color, 1)
    total_h = sum(text_size(t, s)[1] + 3 for t, s in lines) - 3
    y = y0 + (y1 - y0 - total_h) // 2
    cx = (x0 + x1) // 2
    for t, s in lines:
        draw_text_aa(cv, cx, y, t, s, color, align="center")
        y += text_size(t, s)[1] + 3


def visa_sticker(cv, x0, y0, x1, y1):
    """Thalassa visa: green header band, fields, serial, perforation."""
    cv.fill_rect(x0, y0, x1, y1, (224, 238, 222))
    cv.rect(x0, y0, x1, y1, GREEN, 2)
    cv.fill_rect(x0, y0, x1, y0 + 26, GREEN)
    draw_text_aa(cv, (x0 + x1) // 2, y0 + 5, "VISA - THALASSA", 2, PAPER,
                 align="center")
    rows = [
        ("TYPE", "SINGLE ENTRY - 30 DAYS"),
        ("ISSUED", "28 MAR 2021 - KARSTAD"),
        ("VALID", "28 MAR - 27 JUN 2021"),
        ("NO", "TH-22914"),
    ]
    y = y0 + 34
    for label, val in rows:
        draw_text_aa(cv, x0 + 10, y, label, 1, INK_SOFT)
        draw_text_aa(cv, x0 + 78, y, val, 1, INK)
        y += 15
    # perforation ticks along the bottom edge
    for x in range(x0 + 6, x1 - 4, 12):
        cv.fill_rect(x, y1 - 5, x + 5, y1 - 2, PAPER)
    # small round seal overlapping the corner
    cv.circle(x1 - 34, y1 - 30, 16, GREEN, 2)
    draw_text_aa(cv, x1 - 34, y1 - 38, "TH", 2, GREEN, align="center")


# ---------------------------------------------------------------- MRZ (ICAO 9303)

_MRZ_VAL = {}
for _i, _c in enumerate("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"):
    _MRZ_VAL[_c] = _i
_MRZ_VAL["<"] = 0


def mrz_check(s):
    total = 0
    for i, ch in enumerate(s):
        total += _MRZ_VAL[ch] * (7, 3, 1)[i % 3]
    return str(total % 10)


def mrz_lines():
    line1 = "P<ZVAMIRZAK<<ELENA<VERA"
    line1 = line1 + "<" * (44 - len(line1))
    doc = "ZV481902<"
    dob = "940314"
    exp = "310201"
    opt = "<" * 15
    line2 = (doc + mrz_check(doc) + "ZVA" + dob + mrz_check(dob) + "F"
             + exp + mrz_check(exp) + opt)
    comp = doc + mrz_check(doc) + dob + mrz_check(dob) + exp + mrz_check(exp) + opt
    line2 = line2 + mrz_check(comp)
    assert len(line1) == 44 and len(line2) == 44, (len(line1), len(line2))
    return line1, line2


# ---------------------------------------------------------------- composition

def label_value(cv, x, y, label, value, vscale=2, width=250):
    draw_text_aa(cv, x, y, label, 1, INK_SOFT)
    draw_text_aa(cv, x, y + 10, value, vscale, INK)


def signature_squiggle(cv, x0, y, x1):
    pts = []
    n = 40
    for i in range(n + 1):
        t = i / n
        x = x0 + (x1 - x0) * t
        yy = y + int(4 * math.sin(t * 9.0) * (1 - t * 0.4)) - int(3 * math.sin(t * 23.0))
        pts.append((int(x), yy))
    cv.polyline(pts, INK, 2)
    # a second, lighter flourish
    pts2 = [(x0 + 6, y + 8), (x0 + 30, y - 6), (x0 + 70, y + 6), (x0 + 110, y - 2)]
    cv.polyline(pts2, INK_SOFT, 1)


def build():
    cv = Canvas(W, H, PAPER)
    # --- outer frame -------------------------------------------------
    cv.rect(13, 13, W - 13, H - 13, INK, 2)
    cv.rect(18, 18, W - 18, H - 18, GOLD, 1)
    # centre fold: soft shadow + rule
    cv.fill_rect(509, 18, 512, H - 18, (214, 203, 168))
    cv.vline(512, 18, H - 18, (120, 108, 76), 1)
    cv.fill_rect(513, 18, 516, H - 18, (250, 246, 236))

    # ================= LEFT PAGE: data page =========================
    L0, L1 = 26, 504   # page bounds
    lc = (L0 + L1) // 2
    # pale guilloche in the header band only, from the two top corners
    guilloche(cv, L0, 26, L1, 200, (228, 220, 192), step=16,
              corners=[(L0, 26), (L1, 26)])
    # header
    coat_of_arms(cv, lc, 66, 14)
    draw_text_aa(cv, lc, 108, "REPUBLIC OF ZALVARIA", 3, INK, align="center")
    draw_text_aa(cv, lc, 134, "REPUBLIKA ZALVARIA", 2, INK_SOFT, align="center")
    cv.hline(lc - 150, lc + 150, 162, GOLD, 2)
    draw_text_aa(cv, lc, 170, "PASSPORT", 4, BURGUNDY, align="center")

    # portrait
    portrait(cv, 44, 208, 224, 448)
    draw_text_aa(cv, 134, 454, "PHOTO", 1, INK_SOFT, align="center")

    # data fields
    fx = 246
    rows = [
        ("SURNAME", "MIRZAK"),
        ("GIVEN NAMES", "ELENA VERA"),
        ("NATIONALITY", "ZALVARIAN"),
        ("DATE OF BIRTH", "14 MAR 1994"),
        ("PLACE OF BIRTH", "KARSTAD"),
        ("SEX", "F"),
        ("DATE OF ISSUE", "02 FEB 2021"),
        ("DATE OF EXPIRY", "01 FEB 2031"),
        ("PASSPORT NO", "ZV 481 902"),
    ]
    y = 208
    for label, value in rows:
        label_value(cv, fx, y, label, value)
        y += 30
    # authority + signature
    draw_text_aa(cv, fx, y + 2, "AUTHORITY", 1, INK_SOFT)
    draw_text_aa(cv, fx, y + 12, "MINISTRY OF THE INTERIOR", 2, INK, spacing=0)
    draw_text_aa(cv, fx, y + 28, "KARSTAD", 2, INK)
    sig_y = y + 62
    draw_text_aa(cv, fx, sig_y, "HOLDER'S SIGNATURE", 1, INK_SOFT)
    signature_squiggle(cv, fx, sig_y + 22, fx + 150)
    cv.hline(fx, fx + 150, sig_y + 30, INK_SOFT, 1)

    # machine-readable zone
    mrz1, mrz2 = mrz_lines()
    cv.hline(40, 490, 580, FAINT, 1)
    draw_text_aa(cv, 40, 590, mrz1, 2, INK, spacing=0)
    draw_text_aa(cv, 40, 612, mrz2, 2, INK, spacing=0)
    draw_text_aa(cv, lc, 646,
                 "THIS PASSPORT IS THE PROPERTY OF THE REPUBLIC OF ZALVARIA",
                 1, INK_SOFT, align="center")
    draw_text_aa(cv, lc, 660,
                 "IF FOUND, PLEASE RETURN TO THE NEAREST ZALVARIAN MISSION",
                 1, INK_SOFT, align="center")

    # ================= RIGHT PAGE: visas & stamps ===================
    R0, R1 = 524, 998
    rc = (R0 + R1) // 2
    draw_text_aa(cv, rc, 34, "VISAS", 3, INK, align="center")
    draw_text_aa(cv, rc, 58, "VISA - STAMPS - ENDORSEMENTS", 1, INK_SOFT,
                 align="center")
    cv.hline(rc - 120, rc + 120, 80, GOLD, 2)

    # visa sticker (top left) + first stamp (top right)
    visa_sticker(cv, 540, 92, 780, 232)
    oval_stamp(cv, 890, 162, 96, 66, PURPLE,
               [("VELDORIA", 3), ("ENTRY", 2), ("17 MAR 2021", 2),
                ("DRAVNA", 1)])

    # stamp rows: (left centre x, right centre x, cy, left stamp, right stamp)
    stamp_rows = [
        (655, 890, 296,
         ("KARSTAD", BLUE, [("KARSTAD", 2), ("DEPARTURE", 2), ("16 MAR 2021", 2, 0)]),
         ("VELDORIA", PURPLE, [("VELDORIA", 2), ("EXIT", 2), ("02 APR 2021", 2, 0)])),
        (655, 890, 372,
         ("THALASSA", TEAL, [("THALASSA", 2), ("ENTRY", 2), ("03 APR 2021", 2, 0)]),
         ("THALASSA", TEAL, [("THALASSA", 2), ("EXIT", 2), ("19 APR 2021", 2, 0)])),
        (655, 890, 448,
         ("KARSTAD", BLUE, [("KARSTAD", 2), ("ARRIVAL", 2), ("20 APR 2021", 2, 0)]),
         ("OSTMARCK", BURGUNDY, [("OSTMARCK", 2), ("ENTRY", 2), ("09 JUN 2023", 2, 0)])),
        (655, 890, 524,
         ("OSTMARCK", BURGUNDY, [("OSTMARCK", 2), ("EXIT", 2), ("21 JUN 2023", 2, 0)]),
         ("KARSTAD", BLUE, [("KARSTAD", 2), ("ARRIVAL", 2), ("22 JUN 2023", 2, 0)])),
    ]
    for lcx, rcx, cy, left, right in stamp_rows:
        _, lcol, llines = left
        _, rcol, rlines = right
        oval_stamp(cv, lcx, cy, 108, 38, lcol, llines)
        oval_stamp(cv, rcx, cy, 108, 38, rcol, rlines)

    # endorsement + revenue stamp (bottom)
    ey0, ey1 = 566, 692
    cv.rect(540, ey0, 984, ey1, INK, 2)
    cv.fill_rect(540, ey0, 984, ey0 + 20, INK)
    draw_text_aa(cv, 552, ey0 + 4, "ENDORSEMENT", 2, PAPER)
    draw_text_aa(cv, 552, ey0 + 30,
                 "HOLDER IS EXEMPT FROM VISA FOR VELDORIA AND OSTMARCK", 1, INK)
    draw_text_aa(cv, 552, ey0 + 44,
                 "UNDER THE KARSTAD ACCORD OF 2019.", 1, INK)
    draw_text_aa(cv, 552, ey0 + 58,
                 "FEE PAID 45 ZVD - SEE REVENUE STAMP.", 1, INK)
    draw_text_aa(cv, 552, ey0 + 72,
                 "THIS PASSPORT CONTAINS 32 PAGES.", 1, INK)
    # revenue stamp
    rect_stamp(cv, 872, ey0 + 30, 972, ey1 - 14, BURGUNDY,
               [("45 ZVD", 2), ("REVENUE", 1), ("No 1187", 1)])
    return cv


def main():
    cv = build()
    path = OUT
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        write_png(path, W, H, bytes(cv.px))
    except OSError:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "entry.png")
        write_png(path, W, H, bytes(cv.px))
    size = os.path.getsize(path)
    print(f"wrote {path} {W}x{H} {size} bytes")
    if size > 1048576:
        print("WARNING: over the 1 MiB gate", file=sys.stderr)
    if W > 1024 or H > 1024:
        print("WARNING: over the 1024 px gate", file=sys.stderr)


if __name__ == "__main__":
    main()
