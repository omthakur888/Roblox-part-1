#!/usr/bin/env python3
"""
SPOOKY TOWN: "The Last Player"
Renders a ~58s vertical (9:16) Roblox-style horror short with audio + burned-in captions.

CPU only. No GPU, no OpenGL, no display needed -> works on GitHub Actions.
Everything is drawn with Pillow (pseudo-3D perspective) and piped to ffmpeg.

Env vars (all optional):
  PLAYER_NAME  username shown on the 4th plate / leaderboard   (default Player123)
  FPS          frames per second                               (default 24)
  OUT          output file                                     (default spooky_town.mp4)
  PREVIEW      comma list of seconds, e.g. "1,8,13" -> saves PNGs in ./previews and exits
"""
import os, sys, math, random, subprocess, wave, shutil
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageChops

# ----------------------------------------------------------------- config
W, H = 720, 1280
FPS = int(os.environ.get("FPS", 24))
DUR = 58.0
PLAYER = os.environ.get("PLAYER_NAME", "Player123")
OUT = os.environ.get("OUT", "spooky_town.mp4")
CX = W // 2
HOR = int(H * 0.42)          # horizon line
F = 640.0                    # focal length
CAMH = 1.6                   # camera height above ground
FOGC = (16, 18, 32)
SR = 22050

# ----------------------------------------------------------------- helpers
def clamp(x, a=0.0, b=1.0): return max(a, min(b, x))
def smooth(x):
    x = clamp(x); return x * x * (3 - 2 * x)
def mix(a, b, t): return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))
def dim(c, k): return tuple(int(clamp(v * k, 0, 255)) for v in c)
def P(x, y, z):
    z = max(z, 0.12)
    return (CX + x * F / z, HOR + y * F / z)

_fonts = {}
def font(sz, bold=True):
    k = (sz, bold)
    if k in _fonts: return _fonts[k]
    cands = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    ]
    f = None
    for p in cands:
        if os.path.exists(p):
            f = ImageFont.truetype(p, sz); break
    if f is None:
        try: f = ImageFont.load_default(size=sz)
        except TypeError: f = ImageFont.load_default()
    _fonts[k] = f
    return f

def text_c(img, xy, s, sz, fill=(255, 255, 255), stroke=4, sfill=(0, 0, 0), anchor="mm", bold=True):
    ImageDraw.Draw(img).text(xy, s, font=font(sz, bold), fill=fill, anchor=anchor,
                             stroke_width=stroke, stroke_fill=sfill)

_meas = ImageDraw.Draw(Image.new("RGB", (1, 1)))
def wrap(s, f, maxw):
    lines, cur = [], ""
    for w in s.split():
        test = (cur + " " + w).strip()
        if _meas.textlength(test, font=f) <= maxw: cur = test
        else:
            lines.append(cur); cur = w
    lines.append(cur)
    return lines

def panel(img, box, rgba):
    x0, y0, x1, y1 = [int(v) for v in box]
    reg = img.crop((x0, y0, x1, y1)).convert("RGBA")
    out = Image.alpha_composite(reg, Image.new("RGBA", reg.size, rgba)).convert("RGB")
    img.paste(out, (x0, y0))

def glow_at(img, pts, r, color, k=1.0):
    gl = Image.new("RGBA", img.size, (0, 0, 0, 0))
    gd = ImageDraw.Draw(gl)
    for (x, y) in pts:
        for m, a in ((7, 26), (4.5, 46), (3, 80), (1.8, 130), (1, 230)):
            gd.ellipse((x - r * m, y - r * m, x + r * m, y + r * m), fill=color + (int(clamp(a * k, 0, 255)),))
    img.paste(Image.alpha_composite(img.convert("RGBA"), gl).convert("RGB"))

def flick(t):
    n = int(t * 14)
    return 1.0 if ((n * 2654435761) >> 7) % 5 else 0.12

# ----------------------------------------------------------------- precomputed layers
_rng = np.random.default_rng(3)
def _make_sky():
    y = np.linspace(0, 1, H)[:, None, None]
    top = np.array([6, 6, 16.0]); bot = np.array([34, 26, 52.0])
    g = top + (bot - top) * np.clip(y / (HOR / H), 0, 1)
    arr = np.repeat(g, W, axis=1)
    for _ in range(110):
        sx, sy = _rng.integers(0, W), _rng.integers(0, int(HOR * 0.85))
        arr[sy, sx] = 210
    return Image.fromarray(arr.astype(np.uint8))
SKY = _make_sky()

_yy, _xx = np.mgrid[0:H, 0:W]
_r = np.sqrt(((_xx - CX) / (W / 2)) ** 2 + ((_yy - H / 2) / (H / 2)) ** 2)
VIG = np.clip(1.15 - 0.55 * _r ** 1.6, 0.25, 1)[..., None].astype(np.float32)
NOISE = [_rng.normal(0, 4, (H, W, 1)).astype(np.float32) for _ in range(6)]
_haze = np.exp(-(((np.arange(H) - HOR) / 210.0) ** 2)) * 190
HAZE = Image.fromarray(np.repeat(_haze[:, None], W, axis=1).astype(np.uint8), "L")
HAZE_SOLID = Image.new("RGB", (W, H), (46, 50, 76))

# ----------------------------------------------------------------- drawing: street
PAL = [(58, 42, 48), (44, 50, 70), (66, 52, 42), (46, 58, 54), (70, 46, 56)]
SPECIAL_KG = 4
LAMPS = [(6 + 14 * i, -1 if i % 2 else 1) for i in range(8)]

def wall(x, za, zb, h, u0, u1, v0, v1):
    z0 = za + (zb - za) * u0; z1 = za + (zb - za) * u1
    return [P(x, CAMH - h * v0, z0), P(x, CAMH - h * v0, z1), P(x, CAMH - h * v1, z1), P(x, CAMH - h * v1, z0)]

def street(cam_z, lamps, fl=1.0, fog=0.8, lit=True, t=0.0):
    img = SKY.copy(); d = ImageDraw.Draw(img)
    gl = Image.new("RGBA", (W, H), (0, 0, 0, 0)); gd = ImageDraw.Draw(gl)
    d.ellipse((500, 110, 610, 220), fill=(205, 210, 235))
    d.ellipse((470, 100, 580, 210), fill=(13, 11, 25))
    d.rectangle((0, HOR, W, H), fill=(12, 14, 20))
    d.polygon([P(-2.4, CAMH, 0.3), P(2.4, CAMH, 0.3), P(2.4, CAMH, 90), P(-2.4, CAMH, 90)], fill=(26, 26, 34))
    for k in range(0, 24):
        z0 = k * 4 - (cam_z % 4)
        if z0 < 0.4: continue
        d.polygon([P(-0.08, CAMH, z0), P(0.08, CAMH, z0), P(0.08, CAMH, z0 + 1.5), P(-0.08, CAMH, z0 + 1.5)],
                  fill=mix((70, 62, 30), FOGC, clamp(z0 / 45)))
    focus = None
    g0 = int(cam_z // 9)
    for kg in range(g0 + 11, g0 - 1, -1):
        z0 = kg * 9 - cam_z
        if z0 + 6 < 0.7: continue
        for side in (-1, 1):
            special = (lit and kg == SPECIAL_KG and side == 1)
            rnd = (kg * 7919 + side * 131) % 97
            h = 3.6 if special else 3.0 + (rnd % 3) * 0.6
            base = PAL[rnd % len(PAL)]
            a = clamp(z0 / 48)
            fc = lambda c: mix(c, FOGC, a ** 0.8)
            x = side * 4.5
            za = max(z0, 0.5); zb = z0 + 6
            d.polygon([P(x, CAMH, za), P(x, CAMH, zb), P(x, CAMH - h, zb), P(x, CAMH - h, za)], fill=fc(base))
            d.polygon([P(x, CAMH - h, za), P(x, CAMH - h, zb), P(x + side * 2.5, CAMH - h - 1.4, zb),
                       P(x + side * 2.5, CAMH - h - 1.4, za)], fill=fc(dim(base, 0.6)))
            if z0 > 0.7:
                xo = x + side * 5
                d.polygon([P(x, CAMH, z0), P(xo, CAMH, z0), P(xo, CAMH - h, z0), P(x, CAMH - h, z0)], fill=fc(dim(base, 0.8)))
                d.polygon([P(x, CAMH - h, z0), P(xo, CAMH - h, z0), P(x + side * 2.5, CAMH - h - 1.4, z0)], fill=fc(dim(base, 0.5)))
            # windows + door on road-facing wall
            for (u0, u1) in ((0.35, 0.65),) if special else ((0.2, 0.4), (0.6, 0.8)):
                if z0 + 6 * u0 < 0.7: continue
                v0, v1 = (0.45, 0.75)
                quad = wall(x, z0, zb, h, u0, u1, v0, v1)
                if special:
                    d.polygon(quad, fill=(255, 205, 95))
                    cxw = sum(p[0] for p in quad) / 4; cyw = sum(p[1] for p in quad) / 4
                    focus = (cxw, cyw)
                    gd.polygon(quad, fill=(255, 200, 90, 0))
                    rr = abs(quad[1][0] - quad[0][0]) * 1.2 + 6
                    for m, al in ((3.4, 22), (2.4, 40), (1.6, 70)):
                        gd.ellipse((cxw - rr * m, cyw - rr * m, cxw + rr * m, cyw + rr * m), fill=(255, 190, 80, al))
                else:
                    d.polygon(quad, fill=fc((16, 18, 28)))
            if special and z0 + 6 * 0.1 > 0.7:
                d.polygon(wall(x, z0, zb, h, 0.08, 0.22, 0.0, 0.62), fill=(255, 180, 70))
    # lamps
    for (zw, side) in lamps:
        z = zw - cam_z
        if z < 0.8: continue
        x = side * 2.9
        bx, by_ = P(x, CAMH, z); tx, ty = P(x, CAMH - 3.3, z)
        d.line((bx, by_, tx, ty), fill=(34, 34, 44), width=max(2, int(0.14 * F / z)))
        r = 0.3 * F / z
        gp = P(x, CAMH, z)
        gd.ellipse((gp[0] - 2.8 * F / z, gp[1] - 0.35 * F / z, gp[0] + 2.8 * F / z, gp[1] + 0.35 * F / z),
                   fill=(255, 200, 110, int(46 * fl)))
        for m, al in ((5, 22), (3.4, 40), (2.3, 70), (1.5, 125), (1, 235)):
            gd.ellipse((tx - r * m, ty - r * m, tx + r * m, ty + r * m), fill=(255, 205, 120, int(clamp(al * fl, 0, 255))))
    img = Image.alpha_composite(img.convert("RGBA"), gl).convert("RGB")
    m = HAZE.point(lambda v: int(clamp(v * fog, 0, 255)))
    img = Image.composite(HAZE_SOLID, img, m)
    d = ImageDraw.Draw(img)
    for i in range(36):  # drifting dust / ash
        px = (i * 977 + t * (6 + i % 5 * 3)) % W
        py = (i * 613 + t * (12 + i % 3 * 6)) % H
        d.ellipse((px, py, px + 2 + i % 2, py + 2 + i % 2), fill=(150, 150, 175))
    return img, focus

def swing(img, cam_z, t):
    zs = 18.0 - cam_z
    if zs < 1.2: return
    d = ImageDraw.Draw(img); col = mix((36, 28, 28), FOGC, clamp(zs / 45))
    a = 0.55 * math.sin(t * 1.7)
    x0, x1 = -3.95, -2.65; ytop = 2.4
    w = max(2, int(0.1 * F / zs))
    for xx in (x0, x1):
        d.line((*P(xx, CAMH, zs - 0.5), *P(xx, CAMH - ytop, zs), ), fill=col, width=w)
        d.line((*P(xx, CAMH, zs + 0.5), *P(xx, CAMH - ytop, zs), ), fill=col, width=w)
    d.line((*P(x0, CAMH - ytop, zs), *P(x1, CAMH - ytop, zs)), fill=col, width=w)
    L = 1.6
    for xx in (-3.6, -3.0):
        top = P(xx, CAMH - ytop, zs)
        bot = P(xx, CAMH - ytop + L * math.cos(a), zs + L * math.sin(a))
        d.line((*top, *bot), fill=col, width=max(1, w // 2))
    s0 = P(-3.65, CAMH - ytop + L * math.cos(a), zs + L * math.sin(a))
    s1 = P(-2.95, CAMH - ytop + L * math.cos(a), zs + L * math.sin(a))
    d.line((*s0, *s1), fill=dim(col, 1.3), width=max(3, int(0.12 * F / zs)))

def avatar(img, cx, by, s, step, dm=1.0):
    d = ImageDraw.Draw(img)
    c = lambda col: tuple(int(v * dm) for v in col)
    bob = abs(math.sin(step)) * 6 * s if step else 0
    by -= bob
    sw = math.sin(step) * 16 * s
    lw, lh = 36 * s, 92 * s
    d.ellipse((cx - 70 * s, by - 10 * s, cx + 70 * s, by + 16 * s), fill=(6, 6, 10))
    d.rectangle((cx - lw, by - lh, cx - 2, by - max(0, sw)), fill=c((40, 160, 70)))
    d.rectangle((cx + 2, by - lh, cx + lw, by - max(0, -sw)), fill=c((40, 160, 70)))
    ty = by - lh - 112 * s
    d.rectangle((cx - lw, ty, cx + lw, by - lh), fill=c((30, 90, 210)))
    d.rectangle((cx - lw - 28 * s, ty + sw, cx - lw, ty + 92 * s + sw), fill=c((235, 200, 60)))
    d.rectangle((cx + lw, ty - sw, cx + lw + 28 * s, ty + 92 * s - sw), fill=c((235, 200, 60)))
    d.rectangle((cx - 32 * s, ty - 64 * s, cx + 32 * s, ty), fill=c((235, 200, 60)))
    d.rectangle((cx - 32 * s, ty - 64 * s, cx + 32 * s, ty - 44 * s), fill=c((60, 38, 24)))

def figure(img, z, eyek=1.0, x=0.0):
    """Tall blocky shadow figure with red eyes."""
    d = ImageDraw.Draw(img)
    def r(x0, y0, x1, y1, c):
        a = P(x + x0, CAMH - y1, z); b = P(x + x1, CAMH - y0, z)
        d.rectangle((a[0], a[1], b[0], b[1]), fill=c)
    body = (3, 3, 6)
    r(-0.3, 0, -0.04, 0.9, body); r(0.04, 0, 0.3, 0.9, body)
    r(-0.45, 0.8, 0.45, 2.45, body)
    r(-0.7, 0.5, -0.45, 2.4, body); r(0.45, 0.5, 0.7, 2.4, body)
    r(-0.36, 2.4, 0.36, 3.1, body)
    if eyek > 0.02:
        r(-0.22, 2.72, -0.08, 2.84, (255, 30, 30)); r(0.08, 2.72, 0.22, 2.84, (255, 30, 30))
        e1 = P(x - 0.15, CAMH - 2.78, z); e2 = P(x + 0.15, CAMH - 2.78, z)
        glow_at(img, [e1, e2], max(3, 0.1 * F / z), (255, 20, 20), eyek)

# ----------------------------------------------------------------- drawing: interior / corridor / gate
NAMES = ["Elias_204", "Mira.x", "Obby_King9"]

def interior(t):
    img = Image.new("RGB", (W, H), (20, 14, 14)); d = ImageDraw.Draw(img)
    BX0, BY0, BX1, BY1 = 170, 330, 550, 760
    d.polygon([(0, 0), (W, 0), (BX1, BY0), (BX0, BY0)], fill=(26, 18, 16))
    d.polygon([(0, H), (W, H), (BX1, BY1), (BX0, BY1)], fill=(52, 34, 24))
    d.polygon([(0, 0), (BX0, BY0), (BX0, BY1), (0, H)], fill=(44, 30, 28))
    d.polygon([(W, 0), (BX1, BY0), (BX1, BY1), (W, H)], fill=(40, 28, 26))
    d.rectangle((BX0, BY0, BX1, BY1), fill=(58, 42, 38))
    for i in range(-7, 8):
        d.line((CX + i * (BX1 - BX0) / 14, BY1, CX + i * W / 9, H), fill=(36, 24, 18), width=3)
    d.rectangle((CX - 70, BY0 + 70, CX + 70, BY0 + 210), fill=(12, 16, 36))
    d.line((CX, BY0 + 70, CX, BY0 + 210), fill=(40, 28, 24), width=6)
    d.line((CX - 70, BY0 + 140, CX + 70, BY0 + 140), fill=(40, 28, 24), width=6)
    # table
    d.rectangle((110, 1030, 140, 1180), fill=(60, 38, 22)); d.rectangle((580, 1030, 610, 1180), fill=(60, 38, 22))
    d.polygon([(230, 840), (490, 840), (650, 1030), (70, 1030)], fill=(92, 60, 36))
    d.rectangle((70, 1030, 650, 1062), fill=(66, 42, 26))
    plates = [(318, 880, 64), (402, 880, 64), (235, 962, 92), (485, 962, 92)]
    tags = NAMES + [PLAYER]
    for i, (px, py, pw) in enumerate(plates):
        d.ellipse((px - pw / 2, py - pw * 0.19, px + pw / 2, py + pw * 0.19), fill=(205, 205, 195))
        d.ellipse((px - pw / 3, py - pw * 0.12, px + pw / 3, py + pw * 0.12), fill=(170, 170, 160))
        ty = py + pw * 0.19 + 20
        fs = 17 if pw < 80 else 22
        tw = _meas.textlength(tags[i], font=font(fs)) + 14
        d.rectangle((px - tw / 2, ty - fs * 0.7, px + tw / 2, ty + fs * 0.7), fill=(225, 220, 200))
        col = (30, 20, 20)
        if i == 3 and t > 17: col = (int(150 + 100 * abs(math.sin(t * 6))), 0, 0)
        d.text((px, ty), tags[i], font=font(fs), fill=col, anchor="mm")
    d.rectangle((CX - 5, 880, CX + 5, 915), fill=(220, 210, 190))
    f = 0.55 + 0.25 * math.sin(t * 17) * math.sin(t * 5.3)
    d.ellipse((CX - 6, 862, CX + 6, 884), fill=(255, 190, 70))
    glow_at(img, [(CX, 872)], 26, (255, 160, 60), k=f)
    if t >= 26.8:  # something is watching from the dark
        k = smooth((t - 26.8) / 1.0)
        d.ellipse((CX - 33, 458, CX - 19, 468), fill=(255, 30, 30)); d.ellipse((CX + 19, 458, CX + 33, 468), fill=(255, 30, 30))
        glow_at(img, [(CX - 26, 463), (CX + 26, 463)], 8, (255, 20, 20), k)
    return img

def corridor(cam_z, light):
    img = Image.new("RGB", (W, H), (2, 2, 4)); d = ImageDraw.Draw(img)
    X, TOP = 1.7, 3.2
    for k in range(34, -1, -1):
        za = k * 2 - (cam_z % 2); zb = za + 2
        if zb < 0.3: continue
        za = max(za, 0.3)
        sh = clamp(1 - za / 34) * light
        alt = int(cam_z // 2 + k) % 2
        d.polygon([P(-X, CAMH, za), P(X, CAMH, za), P(X, CAMH, zb), P(-X, CAMH, zb)], fill=dim((70, 48, 34) if alt else (58, 38, 26), sh))
        d.polygon([P(-X, CAMH - TOP, za), P(X, CAMH - TOP, za), P(X, CAMH - TOP, zb), P(-X, CAMH - TOP, zb)], fill=dim((34, 26, 34), sh))
        for sx in (-1, 1):
            d.polygon([P(sx * X, CAMH, za), P(sx * X, CAMH - TOP, za), P(sx * X, CAMH - TOP, zb), P(sx * X, CAMH, zb)],
                      fill=dim((66, 48, 56), sh))
    for j in range(0, 12):
        for sx, off in ((-1, 3), (1, 7)):
            zd = int(cam_z // 8) * 8 + j * 8 + off - ((cam_z // 8) * 8 - (cam_z // 8) * 8)
            zd = (int(cam_z // 8) + j) * 8 + off - cam_z
            if zd < 0.5: continue
            sh = clamp(1 - zd / 34) * light
            q = [P(sx * X, CAMH, zd), P(sx * X, CAMH, zd + 1.6), P(sx * X, CAMH - 2.5, zd + 1.6), P(sx * X, CAMH - 2.5, zd)]
            d.polygon(q, fill=dim((98, 54, 30), sh))
            kn = P(sx * X, CAMH - 1.2, zd + 1.3)
            d.ellipse((kn[0] - 3, kn[1] - 3, kn[0] + 3, kn[1] + 3), fill=dim((220, 190, 90), sh))
    return img

def gate(img, z):
    d = ImageDraw.Draw(img)
    for sx in (-1, 1):
        a = P(sx * 2.7 - 0.28, CAMH, z); b = P(sx * 2.7 + 0.28, CAMH - 3.6, z)
        d.rectangle((min(a[0], b[0]), b[1], max(a[0], b[0]), a[1]), fill=(44, 44, 56))
    for i in range(13):
        x = -2.45 + i * 0.408
        d.line((*P(x, CAMH, z), *P(x, CAMH - 2.8, z)), fill=(10, 10, 14), width=7)
    for yy in (0.5, 2.5):
        d.line((*P(-2.45, CAMH - yy, z), *P(2.45, CAMH - yy, z)), fill=(10, 10, 14), width=7)
    sp = P(0, CAMH - 3.4, z)
    d.text(sp, "SPOOKY TOWN", font=font(max(14, int(0.5 * F / z))), fill=(150, 40, 40), anchor="mm")

# ----------------------------------------------------------------- scene dispatcher
STEPS = [(28.0, 20.0), (30, 16.5), (32, 13), (34, 10.5), (36, 8), (38, 5.8), (40, 4.2), (41.2, 3.0)]
SLAMS = [30.5, 32.4, 34.1, 35.5, 37.0, 38.3, 39.4]

def scene(t):
    fx = {}
    if t < 4:
        img, _ = street(0.0, [(5.5, -1)], flick(t), fog=1.0 - 0.45 * smooth(t / 4), t=t)
        avatar(img, CX, H - 150, 1.0, 0, 0.8)
        fx["dark"] = smooth(t / 0.6)
    elif t < 14:
        u = t - 4; cam = min(26.0, u * 2.7)
        img, foc = street(cam, LAMPS, 1.0, fog=0.6, t=t)
        swing(img, cam, t)
        avatar(img, CX, H - 150, 1.0, (t * 9 if u * 2.7 < 26 else 0), 0.8)
        if t > 11.2 and foc:
            fx["zoom"] = (1 + 1.7 * smooth((t - 11.2) / 2.8), foc[0], foc[1])
    elif t < 28:
        img = interior(t)
        u = smooth((t - 14) / 2.8)
        by = (H + 300) + ((H - 150) - (H + 300)) * u
        avatar(img, CX, by, 0.95, (t * 8 if u < 0.98 else 0), 0.75)
        if 16.5 <= t < 24: s = 1 + 0.55 * smooth((t - 16.5) / 3.5)
        elif t >= 24: s = 1.55 - 0.35 * smooth((t - 24) / 4)
        else: s = 1.0
        if s > 1.001: fx["zoom"] = (s, 485, 960)
        if t >= 27.6: fx["dark"] = 1 - 0.6 * smooth((t - 27.6) / 0.4)
    elif t < 42:
        slam = 0.0
        for s_ in SLAMS:
            if 0 <= t - s_ < 0.4: slam = max(slam, math.exp(-(t - s_) * 10))
        light = 1.0 if t < 28.8 else (0.17 * (1 if flick(t) > 0.5 else 0.6) + 0.5 * slam)
        cam = (t - 28) * 5.5
        img = corridor(cam, light)
        z = 20.0
        for ts, zz in STEPS:
            if t >= ts: z = zz
        blink = any(ts <= t < ts + 0.14 for ts, _ in STEPS[1:])
        if t >= 28.8:
            figure(img, z, eyek=smooth((t - 28.8) / 0.6))
        avatar(img, CX, H - 130, 1.0, t * 13, 0.55 + 0.3 * slam)
        fx["shake"] = 3 + slam * 16
        fx["red"] = clamp((t - 28.8) / 12) * 0.35
        fx["flash"] = slam * 0.3
        if blink: fx["dark"] = 0.0
        if t >= 41.2: fx["dark"] = fx.get("dark", 1) * (1 - 0.95 * smooth((t - 41.2) / 0.5) * (1 if t < 41.9 else 0))
    elif t < 52:
        img, _ = street(0.0, [(6, -1)], flick(t), fog=0.7, lit=False, t=t)
        if t >= 48.6:
            figure(img, 13 - 3.2 * smooth((t - 48.6) / 3.4), eyek=smooth((t - 48.6) / 0.6))
        gate(img, 9.0)
        avatar(img, CX, H - 150, 1.0, 0, 0.7)
        fx["shake"] = 14 if 49.3 <= t < 52 else 0
        fx["red"] = 0.25 if t >= 49.3 else 0.1
    else:
        img = Image.new("RGB", (W, H), (0, 0, 0))
        fx["noscene"] = True
    return img, fx

# ----------------------------------------------------------------- UI overlays
def skull(d, x, y, c):
    d.ellipse((x, y, x + 24, y + 20), fill=c); d.rectangle((x + 6, y + 16, x + 18, y + 26), fill=c)
    d.ellipse((x + 4, y + 7, x + 10, y + 14), fill=(0, 0, 0)); d.ellipse((x + 14, y + 7, x + 20, y + 14), fill=(0, 0, 0))
    d.line((x + 10, y + 19, x + 10, y + 26), fill=(0, 0, 0)); d.line((x + 14, y + 19, x + 14, y + 26), fill=(0, 0, 0))

def ui_chat(img, t):
    if t < 20.3: return
    panel(img, (16, 40, 520, 130), (0, 0, 0, 150))
    d = ImageDraw.Draw(img)
    d.text((32, 85), "[Server]:", font=font(30), fill=(255, 70, 70), anchor="lm")
    body = "Welcome back."[: int((t - 20.5) * 14)] if t > 20.5 else ""
    d.text((190, 85), body, font=font(30), fill=(255, 255, 255), anchor="lm")

def ui_menu(img, t):
    a = smooth((t - 42.6) / 0.3) * (1 - smooth((t - 46.2) / 0.3))
    if a <= 0.01: return
    panel(img, (120, 430, 600, 830), (10, 10, 14, int(210 * a)))
    d = ImageDraw.Draw(img)
    clicked = t >= 45.0
    for name, yc in (("Resume", 500), ("Reset Character", 590), ("Leave Game", 680)):
        leave = name == "Leave Game"
        panel(img, (160, yc - 32, 560, yc + 32), (70, 70, 84, int(230 * a)) if not (leave and clicked) else (40, 10, 10, int(230 * a)))
        d = ImageDraw.Draw(img)
        if leave and t > 43.3:
            k = int(120 + 135 * abs(math.sin(t * 5)))
            d.rectangle((160, yc - 32, 560, yc + 32), outline=(k, 0, 0), width=3)
        jit = random.uniform(-3, 3) if (leave and clicked) else 0
        d.text((360 + jit, yc), name, font=font(30), fill=(255, 255, 255), anchor="mm")
    if clicked and t > 45.3:
        d.text((360, 750), "You can't leave.", font=font(30), fill=(255, 40, 40), anchor="mm")
    p = smooth((t - 43.6) / 1.2)
    mx = 500 + (360 - 500) * p; my = 560 + (680 - 560) * p
    pts = [(0, 0), (0, 26), (7, 20), (12, 31), (17, 29), (12, 18), (21, 18)]
    d.polygon([(mx + x, my + y) for x, y in pts], fill=(255, 255, 255), outline=(0, 0, 0))

def ui_board(img, t):
    a = smooth((t - 46.5) / 0.3)
    if a <= 0.01: return
    panel(img, (W - 340, 50, W - 20, 330), (0, 0, 0, int(175 * a)))
    d = ImageDraw.Draw(img)
    d.text((W - 180, 82), "Players", font=font(30), fill=(255, 255, 255), anchor="mm")
    for i, nm in enumerate(NAMES + [PLAYER]):
        y = 140 + i * 52
        if i < 3:
            d.text((W - 325, y), nm, font=font(26), fill=(110, 110, 110), anchor="lm")
            skull(d, W - 60, y - 12, (150, 150, 150))
        else:
            col = (255, 255, 255) if int(t * 3) % 2 else (255, 40, 40)
            d.text((W - 325, y), nm, font=font(26), fill=col, anchor="lm")

CAPS = [
    (0.2, 3.8, "I joined a Roblox server with 0 players... and something was already waiting for me."),
    (4.2, 8.6, "The game was called Spooky Town. No ratings. No description. Just a black thumbnail."),
    (8.9, 14.0, "Every house was empty... except one. Its door was open. And the lights were ON."),
    (14.3, 21.0, "There were four plates. Three had names I didn't know. The fourth... had MY username."),
    (21.8, 27.8, "Back? I'd never played this game before."),
    (28.3, 35.0, "I ran. The doors slammed shut behind me, one by one."),
    (35.2, 41.4, "The figure didn't run... it just appeared closer every time I blinked."),
    (42.3, 46.4, "I tried to leave. The button wouldn't work."),
    (46.8, 49.0, "Then I saw the leaderboard..."),
]

def captions(img, t):
    for a, b, s in CAPS:
        if a <= t < b:
            f = font(46)
            lines = wrap(s, f, W - 90)
            y = int(H * 0.70)
            for ln in lines:
                text_c(img, (CX, y), ln, 46, stroke=6)
                y += 58
            break

def ui(img, t):
    if t < 4:
        k = 0.75 + 0.25 * math.sin(t * 9)
        text_c(img, (CX, 80), "0 PLAYERS ONLINE", 56, fill=(int(255 * k), 20, 20), stroke=5)
        text_c(img, (CX, 140), "SPOOKY TOWN", 32, fill=(210, 210, 210), stroke=4)
    elif 14 <= t < 28:
        ui_chat(img, t)
    elif 36 <= t < 42:
        j = lambda: random.uniform(-5, 5)
        text_c(img, (CX + j(), 300 + j()), "DON'T LOOK BACK", 64, fill=(255, 30, 30), stroke=6)
    elif 42 <= t < 52:
        ui_menu(img, t); ui_board(img, t)
        if t >= 49.3:
            j = lambda: random.uniform(-6, 6)
            text_c(img, (CX + j(), 420 + j()), "NOW WE'RE FOUR.", 58, fill=(255, 30, 30), stroke=6)
    elif t >= 52.9:
        s = f"{PLAYER} has joined the game."
        n = int((t - 53.2) * 22) if t > 53.2 else 0
        shown = s[:n]
        f = font(38)
        lines = wrap(s, f, 560)
        h = 40 * len(lines) + 40
        panel(img, (60, 520, W - 60, 520 + h), (0, 0, 0, 170))
        d = ImageDraw.Draw(img); cnt = 0; y = 540 + 20
        for ln in lines:
            part = shown[cnt:cnt + len(ln) + 1].strip(); cnt += len(ln) + 1
            d.text((CX, y), part, font=f, fill=(255, 255, 255), anchor="mm"); y += 40
        if t >= 55.3:
            a = smooth((t - 55.3) / 0.6)
            col = (int(255 * a), int(30 * a), int(30 * a))
            text_c(img, (CX, 800), "Follow...", 70, fill=col, stroke=6, sfill=(0, 0, 0))
            text_c(img, (CX, 885), "if you dare to join", 40, fill=col, stroke=5)
            text_c(img, (CX, 945), "SPOOKY TOWN", 58, fill=col, stroke=6)

GLITCH = [(41.9, 42.25, 1.0), (49.0, 49.2, 0.7), (49.3, 49.5, 0.6), (51.5, 52.8, 1.0), (53.0, 53.2, 0.6), (57.2, 58.0, 0.9)]
def glitch_k(t):
    return max([k for a, b, k in GLITCH if a <= t < b] + [0.0])

def glitch(arr, k, rnd):
    h = arr.shape[0]
    for _ in range(int(6 + 14 * k)):
        y = rnd.randrange(0, h - 70); hh = rnd.randrange(8, 60); dx = rnd.randrange(-90, 90)
        arr[y:y + hh] = np.roll(arr[y:y + hh], dx, axis=1)
    s = int(6 * k) + 2
    arr[..., 0] = np.roll(arr[..., 0], s, axis=1); arr[..., 2] = np.roll(arr[..., 2], -s, axis=1)
    return arr

def zoom(img, s, cx, cy):
    cw, ch = W / s, H / s
    x0 = clamp(cx - cx / s, 0, W - cw); y0 = clamp(cy - cy / s, 0, H - ch)
    return img.resize((W, H), Image.BILINEAR, box=(x0, y0, x0 + cw, y0 + ch))

def render_frame(t):
    random.seed(int(t * FPS) + 11)
    rnd = random.Random(int(t * FPS) + 5)
    img, fx = scene(t)
    if "zoom" in fx: img = zoom(img, *fx["zoom"])
    sh = fx.get("shake", 0)
    if sh > 0.5:
        img = ImageChops.offset(img, int(rnd.uniform(-sh, sh)), int(rnd.uniform(-sh, sh)))
    arr = np.asarray(img, dtype=np.float32)
    if not fx.get("noscene"):
        arr = arr * VIG
        arr = arr + NOISE[int(t * FPS) % 6]
        red = fx.get("red", 0)
        if red:
            arr[..., 0] += red * 70; arr[..., 1:] *= (1 - red * 0.45)
        if fx.get("flash"): arr += fx["flash"] * 90
    else:
        arr = arr + np.abs(NOISE[int(t * FPS) % 6]) * 0.4
    img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
    ui(img, t)
    captions(img, t)
    arr = np.asarray(img).copy()
    gk = glitch_k(t)
    if gk > 0: arr = glitch(arr, gk, rnd)
    dark = fx.get("dark", 1.0)
    if t > 57.4: dark *= clamp(1 - (t - 57.4) / 0.6)
    if dark < 0.999: arr = (arr * dark).astype(np.uint8)
    return arr

# ----------------------------------------------------------------- audio (synthesised, no files needed)
def make_audio(path):
    n = int(DUR * SR); t = np.arange(n) / SR
    rng = np.random.default_rng(7)
    wind = np.convolve(rng.normal(0, 1, n), np.ones(400) / 400, mode="same") * 20
    wind *= 0.4 + 0.6 * np.sin(2 * np.pi * 0.13 * t) ** 2
    drone = 0.6 * np.sin(2 * np.pi * 55 * t) + 0.35 * np.sin(2 * np.pi * 82.4 * t + 1)
    a = 0.13 * wind + 0.10 * drone * (0.6 + 0.4 * np.sin(2 * np.pi * 0.07 * t))

    def add(start, y, amp=1.0):
        i = int(start * SR); j = min(n, i + len(y))
        if i < n: a[i:j] += y[: j - i] * amp

    def thump(start, amp):
        t2 = np.arange(int(0.28 * SR)) / SR
        add(start, np.sin(2 * np.pi * (60 - 40 * t2) * t2) * np.exp(-t2 * 16), amp * 0.9)

    tt = 28.0
    while tt < 41.5:
        bpm = 80 + (tt - 28) / 14 * 70; per = 60 / bpm
        thump(tt, 1.0); thump(tt + per * 0.28, 0.7); tt += per

    t2 = np.arange(int(0.9 * SR)) / SR  # violin screech
    f = 880 + 380 * t2 / 0.9 + 14 * np.sin(2 * np.pi * 7 * t2)
    ph = 2 * np.pi * np.cumsum(f) / SR
    add(17.0, (np.sin(ph) + 0.5 * np.sin(2 * ph) + 0.33 * np.sin(3 * ph)) * np.minimum(1, t2 * 25) * np.exp(-t2 * 2.2), 0.28)

    for s_ in SLAMS:  # door slams
        t2 = np.arange(int(0.45 * SR)) / SR
        lo = np.convolve(rng.normal(0, 1, len(t2)), np.ones(25) / 25, mode="same") * 5
        add(s_, (lo + np.sin(2 * np.pi * 48 * t2)) * np.exp(-t2 * 11), 0.7)

    t2 = np.arange(int(1.6 * SR)) / SR  # twist boom
    add(42.0, np.sin(2 * np.pi * 42 * t2) * np.exp(-t2 * 3), 1.0)

    for k0 in (49.3, 49.75, 50.2):  # whisper "now we're four"
        t2 = np.arange(int(0.38 * SR)) / SR
        ns = rng.normal(0, 1, len(t2)); hiss = ns - np.convolve(ns, np.ones(8) / 8, mode="same")
        add(k0, hiss * np.sin(np.pi * t2 / 0.38) ** 2, 0.55)
        add(k0, np.sin(2 * np.pi * 95 * t2) * np.sin(np.pi * t2 / 0.38) ** 2, 0.25)

    t2 = np.arange(int(1.3 * SR)) / SR  # door creak
    f = 320 - 140 * t2 / 1.3
    ph = 2 * np.pi * np.cumsum(f) / SR
    add(56.2, (np.sin(ph) + 0.6 * np.sin(2 * ph) + 0.4 * np.sin(3 * ph)) * (0.55 + 0.45 * np.sin(2 * np.pi * 23 * t2)) * np.sin(np.pi * t2 / 1.3), 0.22)

    gain = np.ones(n)
    gain[(t > 40.9) & (t < 42.0)] = 0.05    # sudden silence before the twist
    gain[t > 57.6] = 0.0
    a *= gain
    a = a / (np.max(np.abs(a)) * 1.05)
    pcm = (a * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes(pcm.tobytes())

# ----------------------------------------------------------------- main
def find_ffmpeg():
    p = shutil.which("ffmpeg")
    if p: return p
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()

def main():
    pv = os.environ.get("PREVIEW")
    if pv:
        os.makedirs("previews", exist_ok=True)
        for s in pv.split(","):
            Image.fromarray(render_frame(float(s))).save(f"previews/t{float(s):05.1f}.png")
        print("previews saved"); return
    make_audio("audio.wav")
    total = int(DUR * FPS)
    cmd = [find_ffmpeg(), "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
           "-r", str(FPS), "-i", "-", "-i", "audio.wav", "-c:v", "libx264", "-preset", "veryfast", "-crf", "26",
           "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-t", str(DUR), "-movflags", "+faststart", OUT]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for i in range(total):
        proc.stdin.write(render_frame(i / FPS).tobytes())
        if i % (FPS * 5) == 0: print(f"frame {i}/{total}", flush=True)
    proc.stdin.close(); proc.wait()
    if proc.returncode != 0: sys.exit("ffmpeg failed")
    print("done ->", OUT)

if __name__ == "__main__":
    main()
