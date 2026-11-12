#!/usr/bin/env python3
"""
IN THIS TOWN, NOBODY IS ALLOWED TO SCREAM!  -  Roblox-style 3D YouTube Short
=========================================================================
One file, two roles:

  python generate_short.py --mode preview     # 10 s preview (fast)
  python generate_short.py --mode full        # complete 57 s short + preview

      -> pipeline: narration (Edge TTS) -> synthesized music/ambience/SFX ->
         Blender 4.x 3D render (Cycles) -> ffmpeg (captions, end card, audio mix)

  blender -b --python generate_short.py -- --config build/scene.json --start 0 --end 299
      -> (called automatically) builds the 3D town, characters, animation,
         cameras and renders the frames.
"""
import os, sys, math, json, random, subprocess, shutil, argparse, re, time

HERE = os.path.dirname(os.path.abspath(__file__))

try:
    import bpy, bmesh
    from mathutils import Matrix
    IN_BLENDER = True
except Exception:
    IN_BLENDER = False

FPS = 30


def S(t):
    """seconds -> frame number"""
    return int(round(t * FPS))


def rad(d):
    return math.radians(d)


# =====================================================================
#  PART A - BLENDER 3D SCENE
# =====================================================================
class _Ctx:
    scene = None
    cfg = None
    windows = []        # (object, base_location)
    lamps = []          # (light_data, base_energy)
    lamp_mat = None
    cur_h = {}


C = _Ctx()
_mats = {}


def hex2lin(h):
    h = h.lstrip('#')
    r, g, b = [int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
    return (r ** 2.2, g ** 2.2, b ** 2.2)


def set_interp(kind):
    try:
        bpy.context.preferences.edit.keyframe_new_interpolation_type = kind
    except Exception:
        pass


def link(o):
    C.scene.collection.objects.link(o)
    return o


def new_empty(name, loc=(0, 0, 0), parent=None, size=0.2):
    e = bpy.data.objects.new(name, None)
    e.empty_display_size = size
    link(e)
    if parent is not None:
        e.parent = parent
    e.location = loc
    return e


def mat(name, color, rough=0.7, metal=0.0, emit=None, strength=0.0):
    key = name
    if key in _mats:
        return _mats[key]
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes.get('Principled BSDF')
    b.inputs['Base Color'].default_value = (color[0], color[1], color[2], 1)
    b.inputs['Roughness'].default_value = rough
    b.inputs['Metallic'].default_value = metal
    if emit is not None:
        b.inputs['Emission Color'].default_value = (emit[0], emit[1], emit[2], 1)
        b.inputs['Emission Strength'].default_value = strength
    _mats[key] = m
    return m


def _mesh(name, bm):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    return me


def box_mesh(name, sx, sy, sz):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=(sx, sy, sz), verts=bm.verts)
    return _mesh(name, bm)


def cyl_mesh(name, r, h, seg=16, axis='Z', r2=None):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=seg,
                          radius1=r, radius2=(r if r2 is None else r2), depth=h)
    if axis == 'X':
        bmesh.ops.rotate(bm, cent=(0, 0, 0), matrix=Matrix.Rotation(math.pi / 2, 3, 'Y'), verts=bm.verts)
    return _mesh(name, bm)


def sphere_mesh(name, r, seg=16, sx=1.0, sy=1.0, sz=1.0):
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=max(6, seg // 2), radius=r)
    bmesh.ops.scale(bm, vec=(sx, sy, sz), verts=bm.verts)
    return _mesh(name, bm)


def roof_mesh(name, w, d, h):
    bm = bmesh.new()
    R = 1.0
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=4, radius1=R, radius2=0.0, depth=h)
    bmesh.ops.rotate(bm, cent=(0, 0, 0), matrix=Matrix.Rotation(math.pi / 4, 3, 'Z'), verts=bm.verts)
    side = R * math.sqrt(2)
    bmesh.ops.scale(bm, vec=(w / side, d / side, 1.0), verts=bm.verts)
    return _mesh(name, bm)


def obj(name, me, material, loc=(0, 0, 0), parent=None, rot=(0, 0, 0), scale=(1, 1, 1), bevel=0.0):
    o = bpy.data.objects.new(name, me)
    link(o)
    if material is not None:
        o.data.materials.append(material)
    if parent is not None:
        o.parent = parent
    o.location = loc
    o.rotation_euler = rot
    o.scale = scale
    if bevel > 0:
        m = o.modifiers.new('bevel', 'BEVEL')
        m.width = bevel
        m.segments = 2
        m.limit_method = 'ANGLE'
    return o


def box(name, size, loc, material, parent=None, rot=(0, 0, 0), bevel=0.0):
    return obj(name, box_mesh(name, *size), material, loc, parent, rot, bevel=bevel)


def unit_box(name, size, loc, material, parent=None):
    """cube object whose SCALE holds the size (so it can be animated)"""
    return obj(name, box_mesh(name, 1, 1, 1), material, loc, parent, scale=size)


def vis(objs, t, flag):
    if not isinstance(objs, (list, tuple)):
        objs = [objs]
    for o in objs:
        o.hide_render = not flag
        o.keyframe_insert('hide_render', frame=S(t))


# ---------------------------------------------------------------- characters
EXPR = {  # mouth_w, mouth_h, mouth_dz, eye_h_mult
    'neutral': (0.34, 0.06, 0.0, 1.0),
    'smile':   (0.52, 0.08, 0.015, 0.95),
    'grin':    (0.60, 0.15, 0.0, 0.85),
    'flat':    (0.30, 0.035, -0.01, 1.0),
    'sad':     (0.20, 0.05, -0.03, 1.0),
    'open':    (0.22, 0.18, -0.03, 1.4),
    'scream':  (0.34, 0.36, -0.07, 1.75),
    'awe':     (0.18, 0.20, -0.04, 1.5),
}


class Char:
    """Blocky Roblox-style humanoid built from real 3D boxes with pivots at hips/shoulders/neck."""

    def __init__(self, name, d, skin, shirt, pants, glow_eyes=None):
        self.name, self.d = name, d
        self.parts, self.cur_h, self.cur_expr = [], 0.0, None
        self.root = new_empty(name + '_root')
        lh, th, tw, td = d['leg_h'], d['torso_h'], d['torso_w'], d['torso_d']
        lw, ah, aw = d['leg_w'], d['arm_h'], d['arm_w']
        hx, hy, hz = d['head']
        m_skin = mat(name + '_skin', skin, 0.6)
        m_shirt = mat(name + '_shirt', shirt, 0.75)
        m_pants = mat(name + '_pants', pants, 0.8)
        self.m_skin = m_skin
        P = self.parts.append
        # torso
        P(box(name + '_torso', (tw, td, th), (0, 0, lh + th / 2), m_shirt, self.root, bevel=0.03))
        # legs
        self.leg_l = new_empty(name + '_legL', (-lw / 2, 0, lh), self.root)
        self.leg_r = new_empty(name + '_legR', (lw / 2, 0, lh), self.root)
        for piv in (self.leg_l, self.leg_r):
            P(box(piv.name + '_m', (lw, lw if lw > td else td, lh), (0, 0, -lh / 2), m_pants, piv, bevel=0.03))
        # arms (+hands)
        ax = tw / 2 + aw / 2
        self.arm_l = new_empty(name + '_armL', (-ax, 0, lh + th), self.root)
        self.arm_r = new_empty(name + '_armR', (ax, 0, lh + th), self.root)
        for piv in (self.arm_l, self.arm_r):
            P(box(piv.name + '_m', (aw, td, ah), (0, 0, -ah / 2), m_shirt, piv, bevel=0.03))
            P(box(piv.name + '_hand', (aw * 1.02, td * 1.02, ah * 0.26), (0, 0, -ah + ah * 0.13), m_skin, piv, bevel=0.02))
        # head + neck pivot
        self.neck = new_empty(name + '_neck', (0, 0, lh + th), self.root)
        P(box(name + '_head', (hx, hy, hz), (0, 0, hz / 2), m_skin, self.neck, bevel=0.05))
        # face
        self.eye_w, self.eye_h = 0.13 * hx, 0.17 * hz
        if glow_eyes is None:
            m_eye = mat('face_black', (0.01, 0.01, 0.012), 0.4)
            self.eyes = [unit_box(name + '_eye%d' % i, (self.eye_w, 0.04, self.eye_h),
                                  (s * 0.22 * hx, hy / 2 + 0.012, hz * 0.60), m_eye, self.neck) for i, s in enumerate((-1, 1))]
            self.mouth = unit_box(name + '_mouth', (hx * 0.34, 0.04, hz * 0.06), (0, hy / 2 + 0.012, hz * 0.28), m_eye, self.neck)
            for e in self.eyes + [self.mouth]:
                P(e)
            self.expr(0.0, 'neutral')
        else:
            m_eye = mat(name + '_glow', glow_eyes, 0.2, emit=glow_eyes, strength=60.0)
            self.eyes = [unit_box(name + '_eye%d' % i, (hx * 0.20, 0.05, hz * 0.07),
                                  (s * 0.2 * hx, hy / 2 + 0.012, hz * 0.62), m_eye, self.neck) for i, s in enumerate((-1, 1))]
            for e in self.eyes:
                e.rotation_euler = (0, rad(-12 * (1 if e.location[0] > 0 else -1)), 0)
                P(e)
            self.mouth = None

    # ----- visibility
    def show(self, t, flag):
        vis(self.parts, t, flag)

    # ----- face
    def _apply(self, name, f):
        mx, mz, dz, em = EXPR[name]
        hx, hy, hz = self.d['head']
        self.mouth.scale = (hx * mx, 0.04, hz * mz)
        self.mouth.location = (0, hy / 2 + 0.012, hz * (0.28 + dz))
        self.mouth.keyframe_insert('scale', frame=f)
        self.mouth.keyframe_insert('location', frame=f)
        for e in self.eyes:
            e.scale = (self.eye_w, 0.04, self.eye_h * em)
            e.keyframe_insert('scale', frame=f)

    def expr(self, t, name):
        if self.mouth is None:
            return
        f = S(t)
        if self.cur_expr and f > 3:
            self._apply(self.cur_expr, f - 3)
        self._apply(name, f)
        self.cur_expr = name

    def blink(self, t):
        if self.mouth is None:
            return
        em = EXPR[self.cur_expr or 'neutral'][3]
        f = S(t)
        for ff, k in ((f - 2, 1.0), (f, 0.08), (f + 3, 1.0)):
            for e in self.eyes:
                e.scale = (self.eye_w, 0.04, self.eye_h * em * k)
                e.keyframe_insert('scale', frame=max(0, ff))

    # ----- poses
    def _key(self, o, axis, t, val):
        o.rotation_euler[axis] = val
        o.keyframe_insert('rotation_euler', index=axis, frame=S(t))

    def arm_pulse(self, t0, t1, ang, side='both', rise=0.3, swing_z=0.0):
        for s, piv in (('l', self.arm_l), ('r', self.arm_r)):
            if side in ('both', s):
                self._key(piv, 0, t0, 0.0)
                self._key(piv, 0, t0 + rise, ang)
                self._key(piv, 0, t1, ang)
                self._key(piv, 0, t1 + rise, 0.0)

    def leg_kick(self, t, ang=1.5, side='r'):
        piv = self.leg_r if side == 'r' else self.leg_l
        self._key(piv, 0, t - 0.25, 0.0)
        self._key(piv, 0, t, ang)
        self._key(piv, 0, t + 0.35, 0.0)

    def head(self, t, x=None, z=None):
        if x is not None:
            self._key(self.neck, 0, t, x)
        if z is not None:
            self._key(self.neck, 2, t, z)

    def nod(self, t0, t1, period=0.5, amp=0.14):
        k, t = 0, t0
        while t < t1:
            self._key(self.neck, 0, t, -amp if k % 2 else 0.0)
            t += period / 2
            k += 1
        self._key(self.neck, 0, t1, 0.0)

    def turn(self, t0, t1, deg):
        self.root.rotation_euler[2] = rad(self.cur_h)
        self.root.keyframe_insert('rotation_euler', index=2, frame=S(t0))
        self.root.rotation_euler[2] = rad(deg)
        self.root.keyframe_insert('rotation_euler', index=2, frame=S(t1))
        self.cur_h = deg

    def z(self, t, val):
        self.root.location[2] = val
        self.root.keyframe_insert('location', index=2, frame=S(t))

    # ----- movement: waypoints (t, x, y[, heading_deg])
    def path(self, wps, arms_off=(), gait=None):
        W = []
        for w in wps:
            w = list(w) + [None] * (4 - len(w))
            W.append(w)
        # position keys (linear)
        set_interp('LINEAR')
        for t, x, y, h in W:
            self.root.location[0], self.root.location[1] = x, y
            self.root.keyframe_insert('location', index=0, frame=S(t))
            self.root.keyframe_insert('location', index=1, frame=S(t))
        # headings
        set_interp('BEZIER')
        prev = None
        turn_t = 0.3
        for i, (t, x, y, h) in enumerate(W):
            H = h
            if H is None and i + 1 < len(W):
                dx, dy = W[i + 1][1] - x, W[i + 1][2] - y
                if math.hypot(dx, dy) / max(1e-3, W[i + 1][0] - t) > 0.15:
                    H = math.degrees(math.atan2(-dx, dy))
            if H is None:
                continue
            if prev is not None:
                while H - prev > 180:
                    H -= 360
                while H - prev < -180:
                    H += 360
                self.root.rotation_euler[2] = rad(prev)
                self.root.keyframe_insert('rotation_euler', index=2, frame=S(t))
            self.root.rotation_euler[2] = rad(H)
            self.root.keyframe_insert('rotation_euler', index=2, frame=S(t + (turn_t if prev is not None else 0.0)))
            prev = H
        self.cur_h = prev if prev is not None else 0.0
        # limbs
        def in_off(f):
            return any(S(a) <= f <= S(b) for a, b in arms_off)
        for i in range(len(W) - 1):
            t0, x0, y0, _ = W[i]
            t1, x1, y1, _ = W[i + 1]
            speed = math.hypot(x1 - x0, y1 - y0) / max(1e-3, t1 - t0)
            f0, f1 = S(t0), S(t1)
            moving = speed > 0.15
            nxt_moving = False
            if i + 2 < len(W):
                tt, xx, yy, _ = W[i + 2]
                nxt_moving = math.hypot(xx - x1, yy - y1) / max(1e-3, tt - t1) > 0.15
            if not moving:
                continue
            if gait:
                cyc, amp = gait
            else:
                cyc = max(9.0, min(45.0, 60.0 / speed))
                amp = 0.65 if speed < 3.5 else 1.0
            q = cyc / 4.0
            k, f = 0, float(f0)
            while f <= f1 + 0.01:
                s = math.sin(k * math.pi / 2)
                fi = int(round(f))
                self.leg_r.rotation_euler[0] = amp * s
                self.leg_l.rotation_euler[0] = -amp * s
                self.leg_r.keyframe_insert('rotation_euler', index=0, frame=fi)
                self.leg_l.keyframe_insert('rotation_euler', index=0, frame=fi)
                if not in_off(fi):
                    self.arm_r.rotation_euler[0] = -0.7 * amp * s
                    self.arm_l.rotation_euler[0] = 0.7 * amp * s
                    self.arm_r.keyframe_insert('rotation_euler', index=0, frame=fi)
                    self.arm_l.keyframe_insert('rotation_euler', index=0, frame=fi)
                k += 1
                f += q
            if not nxt_moving:
                for piv in (self.leg_l, self.leg_r):
                    piv.rotation_euler[0] = 0.0
                    piv.keyframe_insert('rotation_euler', index=0, frame=f1 + 5)
                if not in_off(f1 + 5):
                    for piv in (self.arm_l, self.arm_r):
                        piv.rotation_euler[0] = 0.0
                        piv.keyframe_insert('rotation_euler', index=0, frame=f1 + 5)


HUMAN = dict(leg_h=1.0, leg_w=0.5, torso_h=1.0, torso_w=1.0, torso_d=0.5, arm_h=1.0, arm_w=0.5, head=(0.78, 0.78, 0.78))
BEAST = dict(leg_h=2.4, leg_w=0.5, torso_h=2.2, torso_w=0.95, torso_d=0.5, arm_h=3.1, arm_w=0.34, head=(0.7, 0.62, 1.0))


def make_maya(cc):
    c = Char('Maya', HUMAN, hex2lin(cc['skin']), hex2lin(cc['hoodie']), hex2lin(cc['trousers']))
    hx, hy, hz = HUMAN['head']
    hair = mat('maya_hair', hex2lin(cc['hair']), 0.8)
    P = c.parts.append
    P(box('maya_hair_top', (hx + 0.1, hy + 0.1, 0.22), (0, 0, hz - 0.06), hair, c.neck, bevel=0.04))
    P(box('maya_hair_back', (hx + 0.1, 0.2, hz * 0.95), (0, -hy / 2 - 0.04, hz * 0.45), hair, c.neck, bevel=0.04))
    P(box('maya_hair_sideL', (0.12, hy * 0.8, hz * 0.55), (-hx / 2 - 0.03, -0.02, hz * 0.62), hair, c.neck, bevel=0.03))
    P(box('maya_hair_sideR', (0.12, hy * 0.8, hz * 0.55), (hx / 2 + 0.03, -0.02, hz * 0.62), hair, c.neck, bevel=0.03))
    P(box('maya_ponytail', (0.2, 0.2, 0.7), (0, -hy / 2 - 0.18, hz * 0.55), hair, c.neck, rot=(rad(15), 0, 0), bevel=0.04))
    hood = mat('maya_hood', hex2lin(cc['hoodie']), 0.85)
    P(box('maya_hood', (0.95, 0.3, 0.45), (0, -0.33, HUMAN['leg_h'] + HUMAN['torso_h'] - 0.1), hood, c.root, bevel=0.05))
    P(box('maya_pocket', (0.6, 0.06, 0.28), (0, 0.27, HUMAN['leg_h'] + 0.3), mat('maya_pocket', hex2lin(cc['hoodie']) , 0.9), c.root, bevel=0.02))
    shoe = mat('shoe_dark', (0.02, 0.02, 0.025), 0.6)
    for piv in (c.leg_l, c.leg_r):
        P(box(piv.name + '_shoe', (0.52, 0.56, 0.16), (0, 0.04, -HUMAN['leg_h'] + 0.08), shoe, piv, bevel=0.02))
    return c


def make_headphones(tag, parent, color, led=(0.1, 1.0, 0.2)):
    hx, hy, hz = HUMAN['head']
    m = mat('hp_' + tag, color, 0.35, metal=0.4)
    pad = mat('hp_pad_' + tag, (0.01, 0.01, 0.012), 0.9)
    parts = []
    parts.append(box('hp%s_band' % tag, (hx + 0.34, 0.14, 0.09), (0, 0, hz + 0.08), m, parent, bevel=0.03))
    for s in (-1, 1):
        parts.append(box('hp%s_arm%d' % (tag, s), (0.09, 0.14, 0.40), (s * (hx / 2 + 0.10), 0, hz - 0.12), m, parent, bevel=0.02))
        parts.append(obj('hp%s_cup%d' % (tag, s), cyl_mesh('cup', 0.24, 0.16, 20, 'X'), pad, (s * (hx / 2 + 0.11), 0, hz * 0.50), parent))
        parts.append(obj('hp%s_cupcap%d' % (tag, s), cyl_mesh('capm', 0.2, 0.04, 20, 'X'), m, (s * (hx / 2 + 0.20), 0, hz * 0.50), parent))
    m_led = mat('led_' + tag, (0.0, 0.0, 0.0), 0.3, emit=led, strength=25.0)
    l = obj('hp%s_led' % tag, sphere_mesh('led', 0.04, 8), m_led, (hx / 2 + 0.25, 0.07, hz * 0.50), parent)
    parts.append(l)
    return parts, l


def make_andy(cc):
    c = Char('Andy', HUMAN, hex2lin(cc['skin']), hex2lin(cc['shirt']), hex2lin(cc['trousers']))
    hx, hy, hz = HUMAN['head']
    hair = mat('andy_hair', hex2lin(cc['hair']), 0.8)
    P = c.parts.append
    P(box('andy_hair_top', (hx + 0.06, hy + 0.06, 0.16), (0, 0, hz - 0.04), hair, c.neck, bevel=0.04))
    P(box('andy_hair_back', (hx + 0.06, 0.12, hz * 0.55), (0, -hy / 2 - 0.02, hz * 0.7), hair, c.neck, bevel=0.03))
    P(box('andy_hair_fringe', (hx * 0.9, 0.1, 0.1), (0, hy / 2 + 0.02, hz - 0.1), hair, c.neck, bevel=0.02))
    shoe = mat('shoe_light', (0.5, 0.5, 0.52), 0.6)
    for piv in (c.leg_l, c.leg_r):
        P(box(piv.name + '_shoe', (0.52, 0.56, 0.16), (0, 0.04, -HUMAN['leg_h'] + 0.08), shoe, piv, bevel=0.02))
    P(box('andy_stripe', (1.0, 0.52, 0.12), (0, 0, HUMAN['leg_h'] + 0.62), mat('andy_stripe', (0.9, 0.9, 0.95), 0.8), c.root))
    c.hp_a, _ = make_headphones('A', c.neck, hex2lin(cc['headphones_a']))
    c.hp_b, c.led_b_green = make_headphones('B', c.neck, hex2lin(cc['headphones_b']))
    # red LED (noise cancelling OFF) - replaces the green one
    m_red = mat('led_red', (0, 0, 0), 0.3, emit=(1.0, 0.1, 0.05), strength=40.0)
    c.led_red = obj('hpB_led_red', sphere_mesh('led', 0.045, 8), m_red, (hx / 2 + 0.25, 0.07, hz * 0.50), c.neck)
    return c


def make_monster(cc):
    c = Char('Monster', BEAST, hex2lin(cc['body']), hex2lin(cc['body']), hex2lin(cc['body']), glow_eyes=hex2lin(cc['eyes']))
    hx, hy, hz = BEAST['head']
    dark = mat('monster_dark', hex2lin(cc['body']), 0.9)
    P = c.parts.append
    for s in (-1, 1):
        P(obj('horn%d' % s, cyl_mesh('horn', 0.1, 0.9, 6, 'Z', r2=0.0), dark, (s * 0.22, 0, hz + 0.3), c.neck, rot=(0, rad(18 * s), 0)))
    P(box('monster_cloak', (1.5, 0.12, 3.0), (0, -0.33, BEAST['leg_h'] + 1.3), dark, c.root, rot=(rad(8), 0, 0)))
    P(box('monster_shoulders', (1.55, 0.6, 0.35), (0, 0, BEAST['leg_h'] + BEAST['torso_h'] - 0.05), dark, c.root, bevel=0.05))
    for piv in (c.arm_l, c.arm_r):  # long claws
        for k in (-1, 0, 1):
            P(obj('claw', cyl_mesh('claw', 0.045, 0.55, 5, 'Z', r2=0.0), dark, (k * 0.09, 0.0, -BEAST['arm_h'] - 0.2), piv, rot=(math.pi, 0, 0)))
    return c


# ---------------------------------------------------------------- world / town
def setup_world(R):
    w = bpy.data.worlds.new('Night')
    C.scene.world = w
    w.use_nodes = True
    nt = w.node_tree
    bg = nt.nodes['Background']
    bg.inputs[0].default_value = (0.010, 0.017, 0.045, 1)
    bg.inputs[1].default_value = 1.0
    if R.get('fog_density', 0) > 0:
        sc = nt.nodes.new('ShaderNodeVolumeScatter')
        sc.inputs['Density'].default_value = R['fog_density']
        sc.inputs['Anisotropy'].default_value = 0.35
        sc.inputs['Color'].default_value = (0.55, 0.65, 0.85, 1)
        nt.links.new(sc.outputs['Volume'], nt.nodes['World Output'].inputs['Volume'])
    # stars
    rnd = random.Random(7)
    star = mat('star', (1, 1, 1), 0.5, emit=(0.9, 0.95, 1.0), strength=40.0)
    star_me = sphere_mesh('star', 0.7, 6)
    for i in range(170):
        th, ph = rnd.uniform(0, 2 * math.pi), rnd.uniform(0.15, 1.3)
        r = 230
        obj('star%d' % i, star_me, star, (r * math.cos(th) * math.cos(ph) * 0.9, r * math.sin(th) * math.cos(ph) * 0.9, r * math.sin(ph) * 0.8 + 10))
    moon_pos = (90.0, 170.0, 120.0)
    obj('moon', sphere_mesh('moon', 9, 24), mat('moon', (0.9, 0.92, 1.0), 0.9, emit=(0.8, 0.88, 1.0), strength=6.0), moon_pos)
    sun = bpy.data.lights.new('MoonLight', 'SUN')
    sun.energy = R.get('moon_strength', 0.35)
    sun.color = (0.55, 0.68, 1.0)
    sun.angle = rad(3)
    so = bpy.data.objects.new('MoonLight', sun)
    link(so)
    from mathutils import Vector
    d = Vector((-moon_pos[0], -moon_pos[1], -moon_pos[2])).normalized()
    so.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()


def lamp_post(x, y, side, power):
    dark = mat('lamp_metal', (0.03, 0.035, 0.04), 0.5, metal=0.6)
    box('pole', (0.18, 0.18, 5.4), (x, y, 2.7), dark)
    arm_y = y + (-0.8 if side > 0 else 0.8) * -1
    box('arm', (0.14, 1.0, 0.14), (x, y + (0.5 if side < 0 else -0.5), 5.35), dark)
    bx, by = x, y + (1.0 if side < 0 else -1.0)
    obj('bulb', box_mesh('bulb', 0.45, 0.45, 0.2), C.lamp_mat, (bx, by, 5.22))
    L = bpy.data.lights.new('lamp', 'POINT')
    L.energy = power
    L.color = (1.0, 0.76, 0.48)
    L.shadow_soft_size = 0.2
    lo = bpy.data.objects.new('lamp', L)
    link(lo)
    lo.location = (bx, by, 5.0)
    C.lamps.append((L, power))


def house(cx, cy, w, d, h, color, front):
    """front=+1 : front faces +Y (south-side houses); front=-1 : faces -Y"""
    rnd = random
    wall = mat('wall_%d_%d' % (int(cx), int(cy)), color, 0.85)
    box('house', (w, d, h), (cx, cy, h / 2), wall, bevel=0.05)
    roofm = mat('roof', (0.16, 0.07, 0.07), 0.8)
    obj('roof', roof_mesh('roof', w + 1.2, d + 1.2, 2.6), roofm, (cx, cy, h + 1.3))
    box('base', (w + 0.2, d + 0.2, 0.4), (cx, cy, 0.2), mat('base', (0.18, 0.18, 0.2), 0.8))
    fy = cy + front * (d / 2 + 0.04)
    box('door', (1.4, 0.15, 2.4), (cx, fy, 1.2), mat('door', (0.18, 0.09, 0.05), 0.7), bevel=0.03)
    box('porch', (3.0, 1.4, 0.2), (cx, cy + front * (d / 2 + 0.7), 0.1), mat('porch', (0.3, 0.3, 0.32), 0.7))
    on = mat('win_on', (1.0, 0.7, 0.35), 0.3, emit=(1.0, 0.72, 0.38), strength=6.0)
    off = mat('win_off', (0.03, 0.05, 0.1), 0.1)
    rows = [3.4] + ([6.1] if h > 6.5 else [])
    xs = [-w / 3.2, w / 3.2] if w < 8 else [-w / 3.0, 0.0, w / 3.0]
    for zi, z in enumerate(rows):
        for xi, xo in enumerate(xs):
            if zi == 0 and abs(xo) < 0.3:
                continue
            m = on if random.random() < 0.5 else off
            wo = box('window', (1.3, 0.14, 1.5), (cx + xo, fy + front * 0.02, z), m)
            frame_m = mat('frame', (0.85, 0.85, 0.85), 0.6)
            box('wframe', (1.55, 0.1, 1.75), (cx + xo, fy, z), frame_m)
            C.windows.append((wo, tuple(wo.location)))


def tree(x, y, s=1.0):
    trunk = mat('trunk', (0.14, 0.07, 0.03), 0.9)
    leaf = mat('leaf', (0.04, 0.2, 0.06), 0.9)
    box('trunk', (0.5 * s, 0.5 * s, 2.4 * s), (x, y, 1.2 * s), trunk)
    box('leaf1', (2.6 * s, 2.6 * s, 2.0 * s), (x, y, 3.2 * s), leaf, bevel=0.25 * s)
    box('leaf2', (1.8 * s, 1.8 * s, 1.6 * s), (x, y, 4.6 * s), leaf, bevel=0.2 * s)


def build_town(R):
    random.seed(11)
    C.windows, C.lamps = [], []
    C.lamp_mat = mat('lamp_glow', (1, 0.8, 0.5), 0.4, emit=(1.0, 0.78, 0.45), strength=12.0)
    # ground, roads, sidewalks
    box('ground', (500, 500, 0.2), (0, 0, -0.1), mat('grass', (0.025, 0.09, 0.035), 0.95))
    asphalt = mat('asphalt', (0.035, 0.035, 0.04), 0.28)
    box('road', (260, 8, 0.1), (0, 0, 0.02), asphalt)
    box('alley_road', (7, 31, 0.1), (14, -22.5, 0.02), asphalt)
    side = mat('sidewalk', (0.30, 0.30, 0.32), 0.7)
    for sy in (-5.5, 5.5):
        box('sidewalk', (260, 3, 0.16), (0, sy, 0.06), side, bevel=0.02)
    yellow = mat('road_line', (0.8, 0.6, 0.08), 0.4, emit=(0.9, 0.65, 0.1), strength=0.4)
    for i in range(-26, 27):
        box('dash', (2.6, 0.2, 0.02), (i * 5.0, 0, 0.09), yellow)
    white = mat('white_paint', (0.7, 0.7, 0.72), 0.4)
    for i in range(7):
        box('zebra', (0.7, 7.4, 0.02), (-8 + i * 1.4, 0, 0.09), white)
    # houses
    palette = [(0.55, 0.22, 0.2), (0.2, 0.34, 0.55), (0.6, 0.5, 0.2), (0.28, 0.45, 0.28), (0.42, 0.28, 0.5), (0.65, 0.65, 0.6)]
    ci = 0
    for x in [-44, -34, -24, -14, -4, 6, 22, 32, 42, 52]:
        house(x, -16.0, 9, 8, random.choice([6.5, 7.5, 8.5]), palette[ci % 6], +1)
        ci += 1
    for x in range(-50, 61, 10):
        house(x, 16.0, 9, 8, random.choice([6.5, 7.5, 8.5]), palette[(ci + 2) % 6], -1)
        ci += 1
    # lamps
    for x in range(-48, 61, 12):
        lamp_post(x, -6.6, -1, R.get('lamp_power', 1200))
        lamp_post(x + 6, 6.6, +1, R.get('lamp_power', 1200))
    # trees
    for x in (-40, -28, -20, 0, 26, 38, 50):
        tree(x, -9.2, 1.0)
    for x in (-45, -30, -12, 8, 24, 40):
        tree(x, 9.5, 1.1)
    # bus stop
    metal = mat('bus_metal', (0.05, 0.2, 0.55), 0.4, metal=0.5)
    wood = mat('bench_wood', (0.28, 0.15, 0.07), 0.7)
    box('bench_seat', (2.2, 0.6, 0.14), (12.2, -6.4, 0.55), wood, bevel=0.02)
    box('bench_back', (2.2, 0.12, 0.7), (12.2, -6.75, 0.95), wood, bevel=0.02)
    for sx in (-0.9, 0.9):
        box('bench_leg', (0.12, 0.5, 0.55), (12.2 + sx, -6.4, 0.27), metal)
    box('bus_pole', (0.14, 0.14, 3.2), (16.4, -5.9, 1.6), metal)
    box('bus_sign', (1.0, 0.1, 0.9), (16.4, -5.9, 3.0), mat('bus_sign', (0.1, 0.35, 0.9), 0.4, emit=(0.1, 0.35, 0.9), strength=1.2))
    # brick wall (Maya hides behind it)
    brick = mat('brick', (0.32, 0.1, 0.07), 0.9)
    box('wall', (4.4, 0.8, 1.7), (19.0, -8.0, 0.85), brick, bevel=0.03)
    box('wall_cap', (4.6, 1.0, 0.18), (19.0, -8.0, 1.78), mat('wall_cap', (0.4, 0.4, 0.4), 0.7))
    # trash can (kicked over)
    can = new_empty('can_pivot', (9.15, -6.3, 0.0))
    obj('can', cyl_mesh('can', 0.35, 1.2, 14), mat('can_m', (0.18, 0.2, 0.22), 0.5, metal=0.6), (-0.35, 0, 0.6), can)
    obj('can_lid', cyl_mesh('lid', 0.38, 0.1, 14), mat('can_lid', (0.1, 0.12, 0.14), 0.5, metal=0.6), (-0.35, 0, 1.25), can)
    # glowing "end of alley" light used for the silhouette shots
    glow = mat('alley_glow', (0.7, 0.8, 1.0), 0.5, emit=(0.65, 0.78, 1.0), strength=5.0)
    C.alley_glow = box('alley_glow', (7.0, 0.2, 10.0), (14, -38.0, 5.0), glow)
    C.alley_light = bpy.data.lights.new('alley_light', 'POINT')
    C.alley_light.energy = 0
    C.alley_light.color = (0.6, 0.75, 1.0)
    C.alley_light.shadow_soft_size = 0.6
    ao = bpy.data.objects.new('alley_light', C.alley_light)
    link(ao)
    ao.location = (14, -35, 3.5)
    # rubber duck (funny object)
    duck_y = mat('duck_y', (1.0, 0.75, 0.05), 0.5)
    duck_o = mat('duck_o', (1.0, 0.3, 0.02), 0.5)
    C.duck = []
    return


def make_duck(maya):
    yel = mat('duck_y', (1.0, 0.75, 0.05), 0.5)
    ora = mat('duck_o', (1.0, 0.3, 0.02), 0.5)
    base = new_empty('duck', (0, 0, -1.35), maya.arm_r)
    parts = [obj('duck_body', sphere_mesh('db', 0.38, 14, 1.0, 1.35, 0.85), yel, (0, 0, 0), base),
             obj('duck_head', sphere_mesh('dh', 0.24, 12), yel, (0, 0.28, 0.32), base),
             obj('duck_beak', box_mesh('beak', 0.2, 0.22, 0.07), ora, (0, 0.5, 0.3), base),
             obj('duck_tail', box_mesh('tail', 0.15, 0.2, 0.15), yel, (0, -0.5, 0.18), base, rot=(rad(-30), 0, 0))]
    eye = mat('duck_eye', (0, 0, 0), 0.4)
    for s in (-1, 1):
        parts.append(obj('duck_eye', sphere_mesh('de', 0.04, 6), eye, (s * 0.1, 0.45, 0.4), base))
    return parts


# ---------------------------------------------------------------- cameras
def shot(t0, t1, a, b, tgt, lens=35.0, shake=0.012, fstop=2.0, name=None):
    f0, f1 = S(t0), S(t1) - 1
    nm = name or 'cam_%d' % f0
    cd = bpy.data.cameras.new(nm)
    cd.lens = lens
    cd.sensor_fit = 'HORIZONTAL'
    cd.sensor_width = 36.0
    cd.clip_start, cd.clip_end = 0.1, 600
    cd.dof.use_dof = True
    cd.dof.aperture_fstop = fstop
    co = bpy.data.objects.new(nm, cd)
    link(co)
    if tgt[0] == 'f':
        ch, dz = tgt[1], tgt[2]
        tg = new_empty(nm + '_tgt', (0, 0, dz), ch.root)
    else:
        tg = new_empty(nm + '_tgt', tgt)
    cd.dof.focus_object = tg
    c = co.constraints.new('TRACK_TO')
    c.target = tg
    c.track_axis = 'TRACK_NEGATIVE_Z'
    c.up_axis = 'UP_Y'
    rnd = random.Random(f0 * 31 + 5)
    n = max(1, f1 - f0)
    frames = list(range(f0, f1 + 1, 3))
    if frames[-1] != f1:
        frames.append(f1)
    set_interp('BEZIER')
    for f in frames:
        u = (f - f0) / n
        ue = 0.5 * u + 0.5 * (u * u * (3 - 2 * u))
        co.location = tuple(a[i] + (b[i] - a[i]) * ue + rnd.uniform(-shake, shake) for i in range(3))
        co.keyframe_insert('location', frame=f)
    m = C.scene.timeline_markers.new(nm, frame=f0)
    m.camera = co
    if C.scene.camera is None:
        C.scene.camera = co
    return co


# ---------------------------------------------------------------- lights / effects
def flicker(t0, t1, seed=1, low=0.06):
    rnd = random.Random(seed)
    sock = C.lamp_mat.node_tree.nodes['Principled BSDF'].inputs['Emission Strength']
    f = S(t0)
    while f < S(t1):
        v = 1.0 if rnd.random() < 0.45 else rnd.uniform(0.0, low)
        for L, e in C.lamps:
            L.energy = e * v
            L.keyframe_insert('energy', frame=f)
        sock.default_value = 12.0 * v
        sock.keyframe_insert('default_value', frame=f)
        f += rnd.randint(2, 5)
    for L, e in C.lamps:
        L.energy = e
        L.keyframe_insert('energy', frame=S(t1))
    sock.default_value = 12.0
    sock.keyframe_insert('default_value', frame=S(t1))


def shake_windows(t0, t1, amp=0.05, near=(14.0, 30.0)):
    rnd = random.Random(3)
    ws = [(o, b) for o, b in C.windows if abs(b[0] - near[0]) < near[1]]
    f1 = S(t1)
    for o, b in ws:
        f = S(t0)
        while f < f1:
            o.location = (b[0] + rnd.uniform(-amp, amp), b[1], b[2] + rnd.uniform(-amp, amp))
            o.keyframe_insert('location', frame=f)
            f += 2
        o.location = b
        o.keyframe_insert('location', frame=f1)


def alley_light(t, on):
    vis(C.alley_glow, t, on)
    C.alley_light.energy = 4500 if on else 0
    C.alley_light.keyframe_insert('energy', frame=S(t))


# ---------------------------------------------------------------- the story
def build_story(cfg):
    cc = cfg['characters']
    maya, andy, mon = make_maya(cc['maya']), make_andy(cc['andy']), make_monster(cc['monster'])
    duck = make_duck(maya)
    pivot = bpy.data.objects['can_pivot']
    set_interp('BEZIER')

    # --- visibility / initial states
    for ch in (maya, andy):
        ch.show(0, False)
        ch.show(6.8, True)
    vis(andy.hp_a, 0, False)
    vis(andy.hp_a, 6.8, True)
    vis(andy.hp_b, 0, False)
    vis(andy.led_red, 0, False)
    vis(duck, 0, False)
    mon.show(0, False)
    mon.show(3.4, True)       # silhouette appears between the buildings
    mon.show(6.6, False)
    mon.show(40.4, True)      # returns from the darkness
    alley_light(0, True)
    alley_light(7.0, False)
    alley_light(51.8, True)

    # --- MONSTER
    mon.path([(0, 14, -14.5, 0), (6.6, 14, -14.5), (39.0, 14, -30.0, 0), (40.4, 14, -30.0), (42.0, 14, -19.0), (43.2, 14, -12.5),
              (44.5, 14, -9.6), (46.2, 14, -8.0), (47.5, 14, -7.4), (50.0, 14, -6.6), (52.0, 14, -6.5), (53.3, 14, -6.0)],
             gait=(48, 0.32))
    mon.head(3.4, z=0.0)
    mon.head(5.0, z=0.25)
    mon.head(6.4, z=-0.2)
    mon.arm_pulse(52.5, 56.0, 1.35, 'both', rise=0.6)

    # --- ANDY
    andy.path([(0, -18, -5, -90), (7.0, -18, -5), (23.0, 14, -5, 0)])
    andy.expr(0, 'smile')
    for t in (9.0, 12.0, 17.0, 20.0):
        andy.blink(t)
    andy.head(7.0, x=0.0)
    andy.nod(23.4, 31.9, 0.52)
    andy.head(32.2, z=0.0)
    andy.head(32.6, z=-0.75)
    andy.head(33.2, z=-0.75)
    andy.head(33.7, z=0.0)
    andy.nod(34.0, 39.2, 0.52)
    for t in (25.8, 30.2, 35.6, 37.0):
        andy.blink(t)
    andy.expr(25.0, 'neutral')
    andy.expr(32.3, 'open')
    andy.expr(33.3, 'smile')
    andy.expr(36.1, 'smile')
    andy.expr(39.0, 'awe')          # world suddenly gets loud
    andy.expr(40.3, 'neutral')
    andy.expr(41.0, 'awe')
    andy.expr(42.3, 'open')
    andy.expr(43.35, 'scream')
    andy.expr(52.7, 'awe')
    andy.turn(42.4, 43.1, 180.0)
    andy.head(41.8, z=0.0)
    andy.head(42.1, z=0.5)
    andy.head(42.7, z=0.0)
    andy.arm_pulse(43.4, 46.5, 2.6, 'both', rise=0.2)
    # headphones swap (Maya's hands behind him) and the noise-cancelling LED
    vis(andy.hp_a, 21.6, False)
    vis(andy.hp_b, 21.6, True)
    vis(andy.led_b_green, 38.8, False)
    vis(andy.led_red, 38.8, True)

    # --- MAYA
    maya.path([(0, -2, -6.6, 90), (16.0, -2, -6.6), (20.0, 6.2, -5.6), (20.8, 8.65, -5.0), (22.2, 11.45, -5.0),
               (22.9, 12.4, -6.8), (24.2, 19.0, -9.2, 0), (29.8, 19.0, -9.2), (30.8, 16.3, -8.8), (31.6, 15.1, -4.9, 90),
               (33.1, 15.1, -4.9), (34.3, 7.6, -6.2, -90), (35.0, 7.6, -6.2), (36.0, 14.0, -2.9, 180),
               (37.4, 14.0, -2.9), (38.2, 15.5, -4.25, 90), (39.6, 15.5, -4.25), (40.4, 17.2, -3.6, 90),
               (46.8, 17.2, -3.6), (50.0, -2.0, -5.5), (53.0, -30.0, -5.5)],
              arms_off=[(21.0, 22.6), (31.7, 33.4), (36.0, 37.4), (38.2, 39.1), (28.0, 29.9)])
    maya.expr(0, 'smile')
    maya.expr(8.3, 'grin')
    maya.expr(15.5, 'smile')
    maya.expr(21.0, 'flat')
    maya.expr(22.4, 'grin')
    maya.expr(28.3, 'open')
    maya.expr(29.5, 'grin')
    maya.expr(31.7, 'smile')
    maya.expr(34.4, 'open')
    maya.expr(35.4, 'grin')
    maya.expr(36.1, 'scream')
    maya.expr(37.0, 'flat')
    maya.expr(37.6, 'sad')
    maya.expr(38.4, 'flat')
    maya.expr(38.9, 'grin')
    maya.expr(39.6, 'awe')
    maya.expr(44.0, 'open')
    for t in (10.0, 14.0, 19.0, 26.0, 31.0):
        maya.blink(t)
    maya.head(0.0, x=0.0)
    # sneaking: both hands up behind Andy's head (swap)
    maya.arm_pulse(21.0, 22.0, 1.92, 'both', rise=0.35)
    # pops up from behind the wall (z hides her below ground level)
    maya.z(24.0, 0.0)
    maya.z(24.5, -1.6)
    maya.z(28.1, -1.6)
    maya.z(28.5, 0.0)
    maya.arm_pulse(28.4, 29.5, 2.6, 'both', rise=0.2)
    # duck
    vis(duck, 31.7, True)
    vis(duck, 33.1, False)
    maya.arm_pulse(31.9, 33.0, 1.75, 'r', rise=0.3)
    # kick the bin
    maya.leg_kick(34.5, 1.5, 'r')
    set_interp('BEZIER')
    for t, v in ((34.4, 0.0), (34.55, 0.15), (34.9, 1.62), (35.05, 1.45), (35.2, 1.57)):
        pivot.rotation_euler[1] = v
        pivot.keyframe_insert('rotation_euler', index=1, frame=S(t))
    for t, v in ((34.4, 9.15), (34.9, 9.6), (35.4, 10.4)):
        pivot.location[0] = v
        pivot.keyframe_insert('location', index=0, frame=S(t))
    # final BOO and then pressing the headphone button
    maya.arm_pulse(36.1, 37.2, 2.7, 'both', rise=0.2)
    maya.arm_pulse(38.3, 39.0, 1.92, 'l', rise=0.35)
    maya.arm_pulse(45.0, 46.6, 2.2, 'both', rise=0.2)

    # --- lighting events
    flicker(3.2, 3.9, seed=1)
    flicker(5.4, 6.6, seed=2)
    flicker(40.0, 51.5, seed=3, low=0.04)
    flicker(52.5, 55.0, seed=4, low=0.02)
    shake_windows(40.5, 52.0, amp=0.05)

    # --- CAMERAS (cinematic cuts, tracking, close-ups, wide shots)
    # Scene 1
    shot(0.0, 3.0, (-30, -34, 14), (-18, -26, 8), (6, -8, 3), lens=26, name='s1a')
    shot(3.0, 5.0, (8, 7, 1.4), (10.5, 5.5, 1.5), (14, -13, 2.8), lens=40, fstop=1.6, name='s1b')
    shot(5.0, 7.0, (14, -5.0, 1.8), (14, -7.5, 2.6), (14, -14.5, 4.4), lens=55, fstop=1.4, shake=0.02, name='s1c')
    # Scene 2
    shot(7.0, 10.0, (-5.4, -8.6, 2.0), (-4.4, -8.0, 2.2), ('f', maya, 2.38), lens=45, fstop=1.8, name='s2a')
    shot(10.0, 12.5, (-14, -10.0, 1.9), (-9, -10.0, 1.9), ('f', andy, 1.7), lens=35, name='s2b')
    shot(12.5, 15.0, (3.0, -5.6, 1.7), (1.0, -5.9, 1.9), ('f', andy, 2.38), lens=55, fstop=1.6, name='s2c')
    # Scene 3
    shot(15.0, 18.0, (-8, -9.5, 2.4), (-4, -9.5, 2.2), ('f', maya, 1.8), lens=35, name='s3a')
    shot(18.0, 20.8, (4, -10, 1.8), (11, -10, 1.8), ('f', maya, 1.6), lens=32, name='s3b')
    shot(20.8, 22.8, (14.2, -6.7, 2.6), (14.2, -6.4, 2.7), ('f', andy, 2.38), lens=60, fstop=1.4, name='s3c')
    shot(22.8, 25.0, (6, -0.5, 2.0), (8, 1.0, 2.2), (14, -5.5, 1.8), lens=30, name='s3d')
    # Scene 4
    shot(25.0, 27.8, (14, -1.2, 1.8), (14, -2.0, 1.7), ('f', andy, 2.0), lens=40, name='s4a')
    shot(27.8, 30.0, (19.5, -4.8, 2.0), (19.5, -5.2, 2.1), (19.0, -8.9, 1.9), lens=38, shake=0.03, name='s4b')
    shot(30.0, 31.5, (14.4, -2.4, 2.3), (14.2, -3.0, 2.3), ('f', andy, 2.38), lens=70, fstop=1.4, name='s4c')
    shot(31.5, 33.5, (12.3, -1.5, 2.2), (12.6, -2.0, 2.2), (14.4, -4.6, 2.3), lens=42, name='s4d')
    shot(33.5, 35.5, (11.5, -2.2, 1.5), (10.3, -2.8, 1.6), (9.4, -6.2, 1.0), lens=30, shake=0.03, name='s4e')
    shot(35.5, 36.0, (14.6, -1.5, 2.2), (14.2, -1.9, 2.2), ('f', andy, 2.38), lens=60, name='s4f')
    shot(36.0, 37.4, (14.0, -7.4, 2.0), (14.0, -6.9, 2.1), ('f', maya, 2.38), lens=40, fstop=1.6, shake=0.03, name='s4g')
    shot(37.4, 39.0, (16.8, -2.6, 2.6), (16.3, -3.0, 2.5), (14.4, -5.0, 2.35), lens=60, fstop=1.4, name='s4h')
    # Scene 5
    shot(39.0, 40.6, (14.0, -2.0, 2.4), (14.0, -2.7, 2.4), ('f', andy, 2.38), lens=65, fstop=1.4, shake=0.03, name='s5a')
    shot(40.6, 42.0, (14.0, -1.4, 1.5), (14.0, -2.0, 1.4), (14, -10, 2.2), lens=32, shake=0.05, name='s5b')
    shot(42.0, 43.0, (11.2, -1.6, 1.9), (11.8, -1.9, 2.0), ('f', andy, 2.38), lens=50, shake=0.06, name='s5c')
    shot(43.0, 43.6, (14.0, -5.4, 2.4), (14.0, -5.8, 2.4), ('f', mon, 4.3), lens=30, shake=0.07, name='s5d')
    shot(43.6, 45.0, (11.8, -7.9, 2.4), (12.6, -6.8, 2.4), ('f', andy, 2.38), lens=55, fstop=1.4, shake=0.08, name='s5e')
    shot(45.0, 47.5, (4.0, -3.0, 0.8), (7.0, -3.6, 1.0), (14, -7.0, 2.5), lens=24, shake=0.05, name='s5f')
    shot(47.5, 50.0, (14.0, -2.5, 0.6), (14.0, -3.0, 0.7), (14, -8.0, 3.2), lens=28, shake=0.04, name='s5g')
    # Scene 6
    shot(50.0, 52.0, (8.0, -1.0, 1.4), (-8.0, -1.0, 1.5), ('f', maya, 1.5), lens=34, shake=0.03, name='s6a')
    shot(52.0, 55.0, (14.0, -1.0, 0.5), (14.0, -1.8, 0.7), (14, -6.5, 2.8), lens=30, fstop=2.2, shake=0.02, name='s6b')


def main_blender():
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument('--config', required=True)
    ap.add_argument('--start', type=int, default=0)
    ap.add_argument('--end', type=int, default=299)
    ap.add_argument('--out', default=os.path.join(HERE, 'renders'))
    a = ap.parse_args(argv)
    cfg = json.load(open(a.config))
    R, V = cfg['render'], cfg['video']

    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    C.scene, C.cfg = sc, cfg
    sc.render.fps = V['fps']
    sc.frame_start, sc.frame_end = a.start, a.end

    setup_world(R)
    build_town(R)
    build_story(cfg)

    # ---- render settings
    sc.render.engine = 'CYCLES'
    sc.render.resolution_x, sc.render.resolution_y = V['width'], V['height']
    sc.render.resolution_percentage = int(R['percent'])
    cy = sc.cycles
    for k, v in (('device', 'CPU'), ('samples', int(R['samples'])), ('use_adaptive_sampling', True),
                 ('adaptive_threshold', 0.05), ('use_denoising', bool(R['denoise'])), ('denoiser', 'OPENIMAGEDENOISE'),
                 ('max_bounces', 4), ('diffuse_bounces', 2), ('glossy_bounces', 3), ('transmission_bounces', 2),
                 ('volume_bounces', 1), ('volume_step_rate', 2.0), ('sample_clamp_indirect', 10.0)):
        try:
            setattr(cy, k, v)
        except Exception as e:
            print('[warn] cycles.%s: %s' % (k, e))
    sc.render.use_motion_blur = bool(R['motion_blur'])
    try:
        sc.render.motion_blur_shutter = R['motion_blur_shutter']
    except Exception:
        pass
    try:
        sc.view_settings.view_transform = 'AgX'
        sc.view_settings.exposure = R['exposure']
    except Exception as e:
        print('[warn] view settings:', e)
    sc.render.use_overwrite = False            # lets an interrupted render resume
    sc.render.use_placeholder = False
    sc.render.image_settings.file_format = 'PNG'
    sc.render.image_settings.color_mode = 'RGB'
    os.makedirs(a.out, exist_ok=True)
    sc.render.filepath = os.path.join(a.out, 'frame_####')
    print('[blender] rendering frames %d-%d  (%dx%d @ %d%%)' % (a.start, a.end, V['width'], V['height'], R['percent']))
    bpy.ops.render.render(animation=True)
    print('[blender] done')



# =====================================================================
#  PART B - PIPELINE (narration, sound design, render, final edit)
# =====================================================================
SR = 44100
BUILD = os.path.join(HERE, 'build')
AUDIO = os.path.join(HERE, 'audio')
RENDERS = os.path.join(HERE, 'renders')
OUTPUT = os.path.join(HERE, 'output')
BLENDER_URLS = [
    'https://download.blender.org/release/Blender4.2/blender-4.2.3-linux-x64.tar.xz',
    'https://mirrors.ocf.berkeley.edu/blender/release/Blender4.2/blender-4.2.3-linux-x64.tar.xz',
]


def log(*a):
    print('[short]', *a, flush=True)


def run(cmd, **kw):
    return subprocess.run(cmd, check=True, **kw)


def load_cfg():
    import yaml
    with open(os.path.join(HERE, 'config.yml')) as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------- narration (TTS)
def parse_narration():
    lines = {}
    for ln in open(os.path.join(HERE, 'narration.txt'), encoding='utf-8'):
        m = re.match(r'^\[(\d+)\]\s*(.+?)\s*$', ln)
        if m:
            lines[int(m.group(1))] = m.group(2)
    return lines


def ffprobe_dur(path):
    out = subprocess.check_output(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', path])
    return float(out.decode().strip())


def tts_edge(text, out, voices, rate, pitch):
    import asyncio
    import edge_tts

    async def go(v):
        c = edge_tts.Communicate(text, v, rate=rate, pitch=pitch)
        await c.save(out)

    for v in voices:
        for attempt in range(2):
            try:
                asyncio.run(go(v))
                if os.path.exists(out) and os.path.getsize(out) > 2000:
                    return v
            except Exception as e:
                log('edge-tts %s failed (%s)' % (v, e))
                time.sleep(1.5)
    return None


def tts_fallback(text, out):
    """offline fallback so the project still produces a video (less natural voice)"""
    exe = shutil.which('espeak-ng') or shutil.which('espeak')
    if not exe:
        return False
    wav = out.rsplit('.', 1)[0] + '.wav'
    run([exe, '-v', 'en-us+m3', '-s', '140', '-p', '35', '-w', wav, text])
    shutil.move(wav, out)
    return True


def make_narration(cfg):
    os.makedirs(AUDIO, exist_ok=True)
    texts = parse_narration()
    N = cfg['narration']
    voices = [N['voice']] + list(N.get('fallback_voices', []))
    items = []
    for ln in N['lines']:
        i = ln['id']
        text = texts[i]
        out = os.path.join(AUDIO, 'vo_%d.mp3' % i)
        spoken = text.replace('...', ', ...').replace(' ... ', ', ')
        v = None
        try:
            v = tts_edge(spoken, out, voices, ln.get('rate', '+0%'), ln.get('pitch', '+0Hz'))
        except ImportError:
            log('edge-tts not installed')
        if v is None:
            log('using offline fallback voice for line %d' % i)
            if not tts_fallback(text.replace('...', ','), out):
                raise SystemExit('No TTS engine available. pip install edge-tts (needs internet) or apt install espeak-ng')
        else:
            log('line %d voiced with %s' % (i, v))
        items.append(dict(id=i, text=text, file=out, cfg=ln, raw=ffprobe_dur(out)))
    # timings
    total = cfg['video']['duration']
    for it in items:
        c = it['cfg']
        it['start'] = c['start'] if 'start' in c else None
    for it in items:
        if it['start'] is None:
            it['start'] = max(0.0, it['cfg']['end_at'] - it['raw'])
    items.sort(key=lambda d: d['start'])
    maxsp = N.get('max_speedup', 1.2)
    for k, it in enumerate(items):
        limit = (items[k + 1]['start'] if k + 1 < len(items) else total - 0.1) - 0.15
        tempo = 1.0
        if it['start'] + it['raw'] > limit:
            tempo = min(maxsp, it['raw'] / max(0.5, limit - it['start']))
        it['tempo'] = tempo
        it['dur'] = it['raw'] / tempo
        if 'end_at' in it['cfg'] and 'start' not in it['cfg']:
            it['start'] = max(0.0, it['cfg']['end_at'] - it['dur'])
    return items


def load_vo(item):
    import numpy as np
    cmd = ['ffmpeg', '-v', 'error', '-i', item['file'], '-ar', str(SR), '-ac', '1']
    if abs(item['tempo'] - 1.0) > 0.01:
        cmd += ['-filter:a', 'atempo=%.4f' % item['tempo']]
    cmd += ['-f', 'f32le', '-']
    return np.frombuffer(subprocess.check_output(cmd), dtype=np.float32).copy()


# ---------------------------------------------------------------- sound design
def build_audio(cfg, vo_items, out_wav):
    import numpy as np
    from scipy.signal import butter, lfilter
    import wave
    A = cfg['audio']
    total = cfg['video']['duration']
    N = int((total + 0.3) * SR)
    rng = np.random.default_rng(5)

    def lp(x, fc, o=2):
        b, a = butter(o, min(fc, SR * 0.45) / (SR / 2), 'low')
        return lfilter(b, a, x)

    def hp(x, fc, o=2):
        b, a = butter(o, fc / (SR / 2), 'high')
        return lfilter(b, a, x)

    def bp(x, lo, hi):
        b, a = butter(2, [lo / (SR / 2), hi / (SR / 2)], 'band')
        return lfilter(b, a, x)

    def T(d):
        return np.arange(int(d * SR)) / SR

    def nz(d):
        return rng.standard_normal(int(d * SR))

    def fade(x, a=0.004, r=0.02):
        n = len(x)
        na, nr = min(n, int(a * SR)), min(n, int(r * SR))
        x = x.copy()
        if na:
            x[:na] *= np.linspace(0, 1, na)
        if nr:
            x[-nr:] *= np.linspace(1, 0, nr)
        return x

    def sweep(f_of_t, t):
        return np.sin(2 * np.pi * np.cumsum(f_of_t) / SR)

    # ---- one-shot sounds (mono arrays)
    def s_foot(heavy):
        if heavy:
            t = T(0.7)
            return lp(nz(0.7), 220) * np.exp(-t / 0.12) * 1.2 + np.sin(2 * np.pi * 46 * t) * np.exp(-t / 0.2)
        t = T(0.22)
        return lp(nz(0.22), 900) * np.exp(-t / 0.03) * 1.5 + np.sin(2 * np.pi * 70 * t) * np.exp(-t / 0.04) * 0.6

    def s_click():
        t = T(0.1)
        return hp(nz(0.1), 3000) * np.exp(-t / 0.006) + np.sin(2 * np.pi * 2300 * t) * np.exp(-t / 0.012) * 0.5

    def s_whoosh(d=0.9):
        t = T(d)
        return bp(nz(d), 250, 3500) * np.sin(np.pi * t / d) ** 2 * 1.6

    def s_crash():
        t = T(1.8)
        x = hp(nz(1.8), 500) * np.exp(-t / 0.35) * 0.9 + lp(nz(1.8), 300) * np.exp(-t / 0.12) * 1.5
        for f in rng.uniform(400, 3800, 9):
            x += np.sin(2 * np.pi * f * t + rng.uniform(0, 6)) * np.exp(-t / rng.uniform(0.12, 0.4)) * 0.12
        return x

    def s_squeak():
        t = T(0.22)
        f = 900 + 1200 * t / 0.22
        return sweep(f * (1 + 0.04 * np.sin(2 * np.pi * 35 * t)), t) * np.sin(np.pi * t / 0.22) ** 0.5 * 0.7

    def s_sting():
        t = T(1.7)
        x = np.zeros_like(t)
        for f in (880, 932, 1319, 1480, 1976):
            x += sweep(f * (1 - 0.12 * t), t) * 0.25
        x = x * np.exp(-t / 0.55) + hp(nz(1.7), 2000) * np.exp(-t / 0.08) * 0.8
        return x

    def s_scream():
        d = 2.0
        t = T(d)
        f = 760 + 950 * (1 - np.exp(-t / 0.25)) + 70 * np.sin(2 * np.pi * 6.5 * t) + 25 * np.sin(2 * np.pi * 37 * t)
        ph = 2 * np.pi * np.cumsum(f) / SR
        x = sum(w * np.sin(k * ph) for k, w in ((1, 1.0), (2, 0.6), (3, 0.45), (4, 0.3), (5, 0.18)))
        x += bp(nz(d), 1500, 5500) * 0.5
        e = np.minimum(1, t / 0.015) * np.exp(-np.maximum(0, t - 0.5) / 0.7)
        return np.tanh(2.2 * x * e * 0.6)

    def s_growl(d):
        t = T(d)
        f0 = 52 + 9 * np.sin(2 * np.pi * 0.7 * t)
        ph = 2 * np.pi * np.cumsum(f0) / SR
        x = sum(np.sin(k * ph) / k for k in range(1, 14))
        x = x * (0.55 + 0.45 * np.sin(2 * np.pi * 23 * t)) + lp(nz(d), 500) * 0.6
        e = np.minimum(1, t / 0.35) * np.minimum(1, (d - t) / 0.7)
        return lp(x, 1000) * e * 0.5

    def s_boom():
        t = T(2.4)
        f = 24 + 70 * np.exp(-t / 0.35)
        return sweep(f, t) * np.exp(-t / 0.8) * 1.4 + lp(nz(2.4), 160) * np.exp(-t / 0.3) * 1.2

    def s_riser(d):
        t = T(d)
        r = (t / d) ** 2
        f = 180 * (2200 / 180) ** (t / d)
        x = sweep(f, t) * 0.35 + bp(nz(d), 800, 7000) * 0.9
        return fade(x * r, 0.01, 0.01)

    def s_heart(d):
        out = np.zeros(int(d * SR) + SR)
        tt, bpm = 0.0, 70.0
        while tt < d:
            for off, g in ((0.0, 1.0), (0.27, 0.6)):
                t = T(0.3)
                th = sweep(55 - 20 * t / 0.3, t) * np.exp(-t / 0.07) * g
                i = int((tt + off) * SR)
                out[i:i + len(th)] += th[:max(0, len(out) - i)]
            bpm = min(120, bpm + 3)
            tt += 60.0 / bpm
        return out[:int(d * SR)] * 1.6

    def s_pdown():
        t = T(0.8)
        return sweep(1500 * np.exp(-t / 0.2) + 110, t) * np.exp(-t / 0.35) * 0.7

    def s_rattle(d):
        out = np.zeros(int(d * SR))
        n = int(d * 16)
        for _ in range(n):
            i = rng.integers(0, len(out) - 3000)
            t = T(0.05)
            c = hp(nz(0.05), 1800) * np.exp(-t / 0.012) * rng.uniform(0.3, 1.0)
            out[i:i + len(c)] += c
        return out * 0.9

    def s_buzz(d):
        t = T(d)
        gate = np.repeat((rng.random(int(d * 12) + 2) > 0.45).astype(float), int(SR / 12))[:len(t)]
        x = (np.sign(np.sin(2 * np.pi * 100 * t)) * 0.4 + np.sin(2 * np.pi * 200 * t) * 0.3 + nz(d) * 0.05)
        return lp(x, 1500) * gate * 0.5

    ONE = {
        'click': lambda p: s_click(), 'whoosh': lambda p: s_whoosh(), 'crash': lambda p: s_crash(),
        'squeak': lambda p: s_squeak(), 'sting': lambda p: s_sting(), 'scream': lambda p: s_scream(),
        'growl': lambda p: s_growl(p.get('dur', 2.0)), 'boom': lambda p: s_boom(),
        'riser': lambda p: s_riser(p.get('dur', 2.0)), 'heartbeat': lambda p: s_heart(p.get('dur', 3.0)),
        'power_down': lambda p: s_pdown(), 'rattle': lambda p: s_rattle(p.get('dur', 5.0)),
        'buzz': lambda p: s_buzz(p.get('dur', 5.0)),
    }

    def new():
        return np.zeros((N, 2))

    def place(buf, sig, t, gain=1.0, pan=0.0):
        i = int(t * SR)
        if i >= N or i < 0:
            return
        n = min(len(sig), N - i)
        gl, gr = np.cos((pan + 1) * np.pi / 4), np.sin((pan + 1) * np.pi / 4)
        buf[i:i + n, 0] += sig[:n] * gain * gl * 1.4142
        buf[i:i + n, 1] += sig[:n] * gain * gr * 1.4142

    # ---- SFX bus
    sfx = new()
    for ev in cfg['sfx']:
        sig = ONE[ev['type']](ev)
        place(sfx, sig, ev['t'], ev.get('gain', 1.0), ev.get('pan', 0.0))
    for fs in cfg['footsteps']:
        t, k = fs['t0'], 0
        heavy = fs['who'] == 'monster'
        while t < fs['t1']:
            place(sfx, s_foot(heavy), t + rng.uniform(-0.01, 0.01), fs['gain'] * rng.uniform(0.8, 1.1),
                  (-0.15 if k % 2 else 0.15))
            t += fs['every']
            k += 1
    sfx *= A['sfx_volume']

    # ---- ambience bus (night wind + crickets), muffled while Andy wears noise cancelling
    t = np.arange(N) / SR
    wind = lp(rng.standard_normal(N), 260) * (0.6 + 0.4 * np.sin(2 * np.pi * t / 9.0)) * 1.8
    wind += lp(rng.standard_normal(N), 900) * 0.12 * (0.5 + 0.5 * np.sin(2 * np.pi * t / 5.3 + 1))
    cr = np.zeros(N)
    for f, rate, ph in ((4300, 13.0, 0.0), (4700, 11.0, 1.7), (3900, 15.0, 3.1)):
        gate = ((np.sin(2 * np.pi * rate * t + ph) > 0.2) & (np.sin(2 * np.pi * (0.8 + ph / 9) * t) > 0.1)).astype(float)
        cr += np.sin(2 * np.pi * f * t) * gate * 0.025
    amb = wind + cr
    muffled = lp(amb, 600) * 1.4
    m_end = A['muffled_until']
    xf = np.clip((t - (m_end - 0.3)) / 0.6, 0, 1)
    amb = muffled * (1 - xf) + amb * xf
    amb *= np.clip((55.05 - t) / 0.1, 0.25, 1)       # almost silent after the cut to black
    amb_s = np.stack([amb, np.roll(amb, 90)], axis=1) * A['ambience_volume']

    # ---- music bus: dark pad + sparse bells + pulse + rising drone
    chords = [(55.0, 82.41, 110.0, 130.81, 164.81), (43.65, 65.41, 87.31, 130.81, 174.61),
              (55.0, 82.41, 110.0, 130.81, 164.81), (36.71, 73.42, 110.0, 146.83, 174.61)]
    pad = np.zeros(N)
    seg = 7.0
    for si in range(int(total / seg) + 2):
        t0 = si * seg
        w = np.clip((t - (t0 - 1.5)) / 1.5, 0, 1) * np.clip(((t0 + seg + 1.5) - t) / 1.5, 0, 1)
        if not w.any():
            continue
        for k, f in enumerate(chords[si % 4]):
            for det in (-0.004, 0.004):
                ff = f * (1 + det)
                pad += w * (np.sin(2 * np.pi * ff * t) + 0.4 * np.sin(4 * np.pi * ff * t) + 0.15 * np.sin(6 * np.pi * ff * t)) * (0.5 / (1 + k * 0.5))
    pad = lp(pad, 1400) * (0.75 + 0.25 * np.sin(2 * np.pi * 0.17 * t))
    mus = pad * 0.13
    notes = [440.0, 523.25, 659.25, 783.99, 880.0]
    tb = 2.0
    while tb < 55.0:
        f = notes[rng.integers(0, len(notes))] * (0.5 if tb < 8 else 1.0)
        tt = T(2.0)
        b = np.sin(2 * np.pi * f * tt) * np.exp(-tt / 0.7) * 0.07 + np.sin(2 * np.pi * f * 2.76 * tt) * np.exp(-tt / 0.25) * 0.02
        i = int(tb * SR)
        mus[i:i + len(b)] += b[:max(0, N - i)]
        tb += rng.uniform(1.1, 2.6) if tb < 38 else rng.uniform(0.5, 1.2)
    tb = 3.0
    while tb < 55.0:
        tt = T(0.35)
        g = 0.10 + 0.25 * min(1.0, tb / 40.0) if tb < 40 else 0.5
        kick = sweep(120 * np.exp(-tt / 0.05) + 38, tt) * np.exp(-tt / 0.13) * g
        i = int(tb * SR)
        mus[i:i + len(kick)] += kick[:max(0, N - i)]
        tb += 1.0 if tb < 40 else 0.5
    ramp = np.clip((t - 38.5) / 14.0, 0, 1) ** 1.5
    drone = (np.sin(2 * np.pi * 55 * t) + np.sin(2 * np.pi * 58.3 * t) + 0.5 * np.sign(np.sin(2 * np.pi * 27.5 * t))) * ramp * 0.18
    mus += lp(drone, 500)
    mus *= np.clip((55.0 - t) / 0.06, 0, 1)
    mus /= max(1e-6, np.max(np.abs(mus))) * 2.0
    mus_s = np.stack([mus, np.roll(mus, 140)], axis=1) * A['music_volume'] * 2.0

    # ---- narration bus
    vo = new()
    vo_mono = np.zeros(N)
    for it in vo_items:
        x = load_vo(it)
        x = x / max(1e-6, np.max(np.abs(x))) * 0.9
        x = hp(x, 70)
        place(vo, x, it['start'], A['vo_volume'])
        i = int(it['start'] * SR)
        vo_mono[i:i + len(x)] += np.abs(x)[:max(0, N - i)]
    env = lp(vo_mono, 4, 1)
    env = np.clip(env / max(1e-6, np.percentile(env[env > 1e-4], 90) if (env > 1e-4).any() else 1.0), 0, 1)
    duck = (1 - A['duck_amount'] * env)[:, None]

    mix = vo + sfx + (mus_s + amb_s) * duck
    mix = np.tanh(1.15 * mix) / np.tanh(1.15)
    mix /= max(1e-6, np.max(np.abs(mix))) / 0.92
    pcm = (np.clip(mix, -1, 1) * 32767).astype(np.int16)
    with wave.open(out_wav, 'wb') as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    log('audio mix written:', out_wav)


# ---------------------------------------------------------------- captions / cards / ffmpeg
def find_font():
    for p in ('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
              '/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf',
              '/usr/share/fonts/TTF/DejaVuSans-Bold.ttf',
              '/Library/Fonts/Arial Bold.ttf', 'C:/Windows/Fonts/arialbd.ttf'):
        if os.path.exists(p):
            return p
    try:
        out = subprocess.check_output(['fc-match', '-f', '%{file}', 'sans:bold']).decode().strip()
        if out:
            return out
    except Exception:
        pass
    return None


def make_captions(cfg, items):
    C_ = cfg['captions']
    caps = []
    n = C_['words_per_chunk']
    for it in items:
        words = it['text'].replace('...', ' ').split()
        chunks = [' '.join(words[i:i + n]) for i in range(0, len(words), n)]
        weights = [max(4, len(c)) for c in chunks]
        tot = float(sum(weights))
        t = it['start'] + 0.05
        span = it['dur'] - 0.1
        for c, w in zip(chunks, weights):
            d = span * w / tot
            caps.append((t, t + d, c.upper()))
            t += d
    return caps


def make_end_card(cfg, path):
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        log('Pillow missing - end card skipped')
        return False
    V = cfg['video']
    W, H = V['width'], V['height']
    img = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    fp = find_font()
    font = ImageFont.truetype(fp, 150) if fp else ImageFont.load_default()
    words = V['final_text'].split(' ')
    lines = [' '.join(words[:2]), ' '.join(words[2:])] if len(words) > 2 else words
    y = H * 0.40
    for ln in lines:
        d.text((W / 2, y), ln, font=font, fill=(255, 224, 40, 255), anchor='mm', stroke_width=10, stroke_fill=(0, 0, 0, 255))
        y += 190
    ey = int(H * 0.40 + 190 * len(lines) + 150)
    for ex in (W / 2 - 150, W / 2 + 150):
        d.ellipse([ex - 105, ey - 130, ex + 105, ey + 130], fill=(255, 255, 255, 255), outline=(0, 0, 0, 255), width=8)
        d.ellipse([ex - 20 - 35, ey - 5 - 55, ex - 20 + 45, ey - 5 + 55], fill=(10, 10, 10, 255))
        d.ellipse([ex - 20 - 5, ey - 5 - 35, ex - 20 + 10, ey - 5 - 15], fill=(255, 255, 255, 255))
    img.save(path)
    return True


def esc_ff(p):
    return p.replace('\\', '/').replace(':', '\\:')


def assemble(cfg, frames_dir, audio_wav, out_path, seconds, caps, n_frames):
    V = cfg['video']
    fps = V['fps']
    font = find_font()
    ff = esc_ff(font) if font else None
    pad = max(0.0, seconds - n_frames / fps)
    os.makedirs(BUILD, exist_ok=True)
    parts = ["[0:v]scale=%d:%d:flags=lanczos,eq=contrast=1.06:saturation=1.1,vignette=PI/4.6,noise=alls=5:allf=t,format=yuv420p" % (V['width'], V['height'])]
    if pad > 0:
        parts[0] += ",tpad=stop_mode=add:stop_duration=%.3f:color=black" % pad
    chain = parts[0] + "[v0]"
    graph = [chain]
    cur = 'v0'
    k = 0

    def dt(textfile, size, y, enable, extra=''):
        nonlocal cur, k
        k += 1
        nxt = 'v%d' % k
        base = "[%s]drawtext=textfile='%s':fontsize=%d:fontcolor=white:borderw=%d:bordercolor=black:x=(w-text_w)/2:y=%s:expansion=none:line_spacing=14:enable='%s'%s" % (
            cur, esc_ff(textfile), size, max(4, size // 12), y, enable, extra)
        if ff:
            base += ":fontfile='%s'" % ff
        graph.append(base + "[%s]" % nxt)
        cur = nxt

    if font:
        tc = V['title_card']
        tf = os.path.join(BUILD, 'title.txt')
        t = V['title']
        words = t.split(' ')
        open(tf, 'w').write('\n'.join([' '.join(words[:3]), ' '.join(words[3:5]), ' '.join(words[5:])]))
        al = "alpha='if(lt(t,%.2f),(t-%.2f)/0.3,if(gt(t,%.2f),(%.2f-t)/0.3,1))'" % (tc['start'] + 0.3, tc['start'], tc['end'] - 0.3, tc['end'])
        dt(tf, 76, 'h*0.10', "between(t,%.2f,%.2f)" % (tc['start'], tc['end']), ':' + al)
        if cfg['captions']['enabled']:
            for i, (a, b, text) in enumerate(caps):
                if a > seconds:
                    continue
                cf = os.path.join(BUILD, 'cap_%03d.txt' % i)
                open(cf, 'w', encoding='utf-8').write(text)
                dt(cf, cfg['captions']['font_size'], 'h*%.2f' % cfg['captions']['y_ratio'], "between(t,%.2f,%.2f)" % (a, b))
    inputs = ['-framerate', str(fps), '-start_number', '0', '-i', os.path.join(frames_dir, 'frame_%04d.png')]
    idx = 1
    card = os.path.join(BUILD, 'end_card.png')
    if seconds > V['final_card']['start'] and make_end_card(cfg, card):
        inputs += ['-loop', '1', '-framerate', str(fps), '-t', '%.2f' % seconds, '-i', card]
        fc = V['final_card']
        graph.append("[%s][%d:v]overlay=0:0:enable='between(t,%.2f,%.2f)'[vout]" % (cur, idx, fc['start'], fc['end']))
        idx += 1
    else:
        graph.append("[%s]null[vout]" % cur)
    inputs += ['-i', audio_wav]
    gf = os.path.join(BUILD, 'filter.txt')
    open(gf, 'w', encoding='utf-8').write(';\n'.join(graph))
    cmd = ['ffmpeg', '-y', '-v', 'error', '-stats'] + inputs + ['-filter_complex_script', gf, '-map', '[vout]', '-map', '%d:a' % idx,
           '-t', '%.2f' % seconds, '-c:v', 'libx264', '-preset', 'medium', '-crf', '18', '-pix_fmt', 'yuv420p', '-r', str(fps),
           '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', out_path]
    run(cmd)
    log('wrote', out_path)


# ---------------------------------------------------------------- Blender
def is_real_blender(exe):
    try:
        out = subprocess.run([exe, '--version'], capture_output=True, text=True, timeout=60).stdout
        return out.strip().startswith('Blender')
    except Exception:
        return False


def ensure_blender(arg):
    cands = [arg, os.environ.get('BLENDER'), os.path.join(HERE, 'blender', 'blender'), shutil.which('blender')]
    for c in cands:
        if c and os.path.exists(c) and is_real_blender(c):
            return c
    if sys.platform.startswith('linux'):
        import urllib.request, tarfile
        tgt = os.path.join(HERE, 'blender_dl')
        for url in BLENDER_URLS:
            try:
                log('downloading Blender from', url)
                fn = os.path.join(BUILD, 'blender.tar.xz')
                urllib.request.urlretrieve(url, fn)
                with tarfile.open(fn) as tf:
                    tf.extractall(tgt)
                exe = os.path.join(tgt, os.listdir(tgt)[0], 'blender')
                if is_real_blender(exe):
                    return exe
            except Exception as e:
                log('download failed:', e)
    raise SystemExit('Blender 4.x not found. Install it from blender.org or pass --blender /path/to/blender')


def render_frames(cfg, blender, start, end, args):
    R = dict(cfg['render'])
    if args.samples:
        R['samples'] = args.samples
    if args.percent:
        R['percent'] = args.percent
    scene = dict(video=cfg['video'], render=R, characters=cfg['characters'])
    sj = os.path.join(BUILD, 'scene.json')
    json.dump(scene, open(sj, 'w'))
    os.makedirs(RENDERS, exist_ok=True)
    cmd = [blender, '--background', '--factory-startup', '-noaudio', '--python', os.path.abspath(__file__), '--',
           '--config', sj, '--start', str(start), '--end', str(end), '--out', RENDERS]
    logf = os.path.join(BUILD, 'blender.log')
    log('rendering frames %d-%d with Blender (this is the slow part)...' % (start, end))
    t0 = time.time()
    with open(logf, 'w') as lf:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        last = 0
        for ln in p.stdout:
            lf.write(ln)
            if ln.startswith('Fra:') and time.time() - last > 30:
                print(ln.strip()[:110], flush=True)
                last = time.time()
            elif ln.startswith(('Traceback', 'Error', 'RuntimeError', 'AttributeError', 'TypeError', 'KeyError', '[warn]', '[blender]')):
                print(ln.rstrip(), flush=True)
        p.wait()
    if p.returncode != 0:
        print(''.join(open(logf).readlines()[-60:]))
        raise SystemExit('Blender failed (see build/blender.log)')
    log('render finished in %.1f min' % ((time.time() - t0) / 60))


def main():
    ap = argparse.ArgumentParser(description='Roblox-style 3D YouTube Short generator')
    ap.add_argument('--mode', choices=['preview', 'full'], default='full')
    ap.add_argument('--blender', default=None)
    ap.add_argument('--samples', type=int, default=0)
    ap.add_argument('--percent', type=int, default=0)
    ap.add_argument('--clean', action='store_true', help='delete old rendered frames first')
    ap.add_argument('--skip-render', action='store_true', help='only (re)do audio + final edit from existing frames')
    a = ap.parse_args()

    for d in (BUILD, AUDIO, RENDERS, OUTPUT, os.path.join(HERE, 'assets')):
        os.makedirs(d, exist_ok=True)
    if a.clean:
        shutil.rmtree(RENDERS, ignore_errors=True)
        os.makedirs(RENDERS)
    for tool in ('ffmpeg', 'ffprobe'):
        if not shutil.which(tool):
            raise SystemExit('%s is required (sudo apt-get install ffmpeg)' % tool)
    cfg = load_cfg()
    V = cfg['video']
    assert V['duration'] < 60, 'Shorts must be under 60 seconds'
    fps = V['fps']

    log('1/4 narration')
    items = make_narration(cfg)
    log('2/4 sound design + mix')
    wav = os.path.join(AUDIO, 'mix.wav')
    build_audio(cfg, items, wav)
    caps = make_captions(cfg, items)

    seconds_prev = V['preview_seconds']
    end_frame = (S(seconds_prev) if a.mode == 'preview' else S(V['render_end'])) - 1
    if not a.skip_render:
        log('3/4 3D render')
        render_frames(cfg, ensure_blender(a.blender), 0, end_frame, a)
    n = len([f for f in os.listdir(RENDERS) if f.startswith('frame_') and f.endswith('.png')])
    if n < end_frame + 1:
        raise SystemExit('only %d of %d frames rendered' % (n, end_frame + 1))

    log('4/4 final edit')
    prev = os.path.join(OUTPUT, 'preview_10_seconds.mp4')
    if a.mode == 'preview':
        assemble(cfg, RENDERS, wav, prev, seconds_prev, caps, seconds_prev * fps)
    else:
        final = os.path.join(OUTPUT, 'roblox_short_final.mp4')
        assemble(cfg, RENDERS, wav, final, V['duration'], caps, end_frame + 1)
        run(['ffmpeg', '-y', '-v', 'error', '-i', final, '-t', str(seconds_prev), '-c:v', 'libx264', '-preset', 'veryfast',
             '-crf', '20', '-c:a', 'aac', '-movflags', '+faststart', prev])
        log('wrote', prev)
    log('DONE ->', OUTPUT)


if __name__ == '__main__':
    if IN_BLENDER:
        main_blender()
    else:
        main()
