import bpy, sys, os, random, math
from mathutils import Vector

# ---------- settings ----------
FPS, TOTAL = 24, 960            # 40 seconds
RES_X, RES_Y = 720, 1280        # vertical Short
argv = sys.argv
OUT = argv[argv.index("--") + 1] if "--" in argv else "out/roblox_3am_"
OUT = os.path.abspath(OUT)
os.makedirs(os.path.dirname(OUT), exist_ok=True)

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.context.preferences.edit.keyframe_new_interpolation_type = 'LINEAR'
sc = bpy.context.scene
sc.frame_start, sc.frame_end = 1, TOTAL
sc.render.fps = FPS
sc.render.resolution_x, sc.render.resolution_y = RES_X, RES_Y
sc.render.resolution_percentage = 100
sc.render.engine = 'BLENDER_WORKBENCH'
sc.display.shading.light = 'FLAT'
sc.display.shading.color_type = 'MATERIAL'
sc.display.shading.show_object_outline = False
sc.render.image_settings.file_format = 'FFMPEG'
sc.render.ffmpeg.format = 'MPEG4'
sc.render.ffmpeg.codec = 'H264'
sc.render.ffmpeg.constant_rate_factor = 'MEDIUM'
sc.render.filepath = OUT
sc.world = bpy.data.worlds.new("sky")
sc.world.color = (0.01, 0.01, 0.05)

# ---------- helpers ----------
_mats = {}
def mat(color):
    key = tuple(color)
    if key not in _mats:
        m = bpy.data.materials.new("m")
        m.diffuse_color = (*color, 1)
        _mats[key] = m
    return _mats[key]

def link(o):
    sc.collection.objects.link(o)
    return o

def box(size, loc, color, parent=None):
    bpy.ops.mesh.primitive_cube_add(size=1)
    o = bpy.context.object
    o.scale = size
    o.data.materials.append(mat(color))
    if parent:
        o.parent = parent
    o.location = loc
    return o

def show(o, s, e):
    """Visible from frame s up to frame e."""
    keys = [(0, True)] if s > 0 else []
    keys += [(s, False), (e, True)]
    for f, v in keys:
        o.hide_render = v
        o.keyframe_insert("hide_render", frame=f)

def avatar(name, torso, legs, loc, rot_z):
    root = link(bpy.data.objects.new(name, None))
    root.location = loc
    root.rotation_euler = (0, 0, rot_z)
    skin, dark = (0.96, 0.8, 0.2), (0.05, 0.05, 0.05)
    parts = [
        box((1, 1, 2), (-0.5, 0, 1), legs, root),
        box((1, 1, 2), (0.5, 0, 1), legs, root),
        box((2, 1, 2), (0, 0, 3), torso, root),
        box((1, 1, 2), (-1.5, 0, 3), skin, root),
        box((1, 1, 2), (1.5, 0, 3), skin, root),
        box((1, 1, 1), (0, 0, 4.5), skin, root),
        box((0.15, 0.05, 0.25), (-0.22, -0.51, 4.6), dark, root),
        box((0.15, 0.05, 0.25), (0.22, -0.51, 4.6), dark, root),
        box((0.5, 0.05, 0.08), (0, -0.51, 4.25), dark, root),
    ]
    return root, parts

# ---------- world ----------
bpy.ops.mesh.primitive_plane_add(size=300, location=(0, 0, 0))
bpy.context.object.data.materials.append(mat((0.35, 0.35, 0.37)))
random.seed(3)
for i in range(16):
    s = random.uniform(3, 7)
    side = random.choice([-1, 1])
    box((s, s, s * random.uniform(0.6, 2)),
        (side * random.uniform(14, 40), random.uniform(-20, 40), 0),
        (0.2, 0.2, 0.24)).location.z = s * 0.4

# ---------- avatars ----------
ALEX_Y, STOP_Y = 14, 10.5
player, _ = avatar("You", (0.1, 0.3, 0.8), (0.2, 0.6, 0.2), (0, 0, 0), math.pi)
alex, alex_parts = avatar("Alex", (0.12, 0.12, 0.12), (0.03, 0.03, 0.03), (0, ALEX_Y, 0), 0)
for p in alex_parts:
    show(p, 100, TOTAL)

# Player movement: walk toward Alex, stop, turn, walk away
player.location = (0, 0, 0); player.keyframe_insert("location", frame=120)
player.location = (0, STOP_Y, 0); player.keyframe_insert("location", frame=200)
player.keyframe_insert("location", frame=290)
player.location = (0, STOP_Y, 0); player.keyframe_insert("location", frame=306)
player.location = (0, -6, 0); player.keyframe_insert("location", frame=420)
player.rotation_euler = (0, 0, math.pi); player.keyframe_insert("rotation_euler", frame=290)
player.rotation_euler = (0, 0, 0); player.keyframe_insert("rotation_euler", frame=306)

# ---------- camera ----------
cam_data = bpy.data.cameras.new("cam")
cam_data.lens = 50
cam_data.sensor_fit = 'VERTICAL'
cam_data.sensor_height = 36
cam = link(bpy.data.objects.new("cam", cam_data))
sc.camera = cam

def cam_key(frame, loc, target):
    cam.location = loc
    d = Vector(target) - Vector(loc)
    cam.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
    cam.keyframe_insert("location", frame=frame)
    cam.keyframe_insert("rotation_euler", frame=frame)

cam_key(1, (0, -6, 3.2), (0, 8, 2.5))
cam_key(119, (0, -6, 3.2), (0, 8, 2.5))
cam_key(120, (0, -6, 3.2), (0, 8, 2.5))
cam_key(200, (0, STOP_Y - 6, 3.2), (0, STOP_Y + 8, 2.5))
cam_key(229, (0, STOP_Y - 6, 3.2), (0, STOP_Y + 8, 2.5))
cam_key(230, (3.5, 7, 3.6), (0, ALEX_Y, 4.4))      # slow zoom on Alex
cam_key(289, (3.2, 11, 3.6), (0, ALEX_Y, 4.4))
cam_key(290, (18, 12, 4), (0, 12, 3))              # wide side shot
cam_key(480, (16, 12, 3.8), (0, 12, 3))

# ---------- HUD (children of the camera) ----------
DIST = 6.0
VH = DIST * 36 / 50
VW = VH * RES_X / RES_Y

def hud_text(body, x, y, size, color, s, e, d=5.9, align='CENTER'):
    cu = bpy.data.curves.new("t", 'FONT')
    cu.body, cu.size, cu.align_x, cu.align_y = body, size, align, 'CENTER'
    cu.materials.append(mat(color))
    o = link(bpy.data.objects.new("t", cu))
    o.parent = cam
    o.location = (x * VW / 2, y * VH / 2, -d)
    show(o, s, e)
    return o

def hud_panel(color, x, y, w, h, s, e, d=6.0):
    bpy.ops.mesh.primitive_plane_add(size=1)
    o = bpy.context.object
    o.data.materials.append(mat(color))
    o.parent = cam
    o.scale = (w * VW, h * VH, 1)
    o.location = (x * VW / 2, y * VH / 2, -d)
    show(o, s, e)
    return o

WHITE, RED, GREEN = (1, 1, 1), (0.9, 0.05, 0.05), (0.1, 0.8, 0.3)

# Scene 1: time stamp
hud_text("3:00 AM", 0, 0.1, 0.55, WHITE, 1, 110)
# Roblox player list (top right) and chat (top left)
hud_text("YOU", 0.85, 0.93, 0.09, WHITE, 1, 480, align='RIGHT')
hud_text("Alex", 0.85, 0.88, 0.09, WHITE, 110, 480, align='RIGHT')
hud_text("[You]: Hey! Are you AFK?", -0.92, 0.93, 0.085, WHITE, 200, 480, align='LEFT')
hud_text("[Alex]: DON'T LEAVE ME ALONE.", -0.92, 0.88, 0.085, RED, 360, 480, align='LEFT')
# Big scary caption
hud_text("DON'T LEAVE\nME ALONE.", 0, -0.3, 0.3, RED, 360, 440)

# Scene 4: profile screen
hud_panel((0.1, 0.1, 0.12), 0, 0, 1.1, 1.1, 480, 648)
hud_panel((0.96, 0.8, 0.2), 0, 0.35, 0.35, 0.2, 480, 648, d=5.95)
hud_text("Alex", 0, 0.05, 0.4, WHITE, 480, 648)
hud_text("Last online:", 0, -0.2, 0.2, (0.7, 0.7, 0.7), 540, 648)
hud_text("2020", 0, -0.38, 0.5, RED, 570, 648)

# Scene 5: home page after leaving
hud_panel((0.14, 0.15, 0.18), 0, 0, 1.1, 1.1, 648, 912)
hud_text("You left the game.", 0, 0.1, 0.17, WHITE, 648, 912)
hud_text("Home", 0, 0.8, 0.15, (0.7, 0.7, 0.7), 648, 912)

# Scene 6: friend request popup
hud_panel((0.22, 0.23, 0.27), 0, 0.55, 0.95, 0.22, 800, 912, d=5.95)
hud_text("Alex sent you\na friend request.", 0, 0.58, 0.14, WHITE, 800, 912)
hud_panel(GREEN, 0, 0.42, 0.4, 0.07, 800, 912, d=5.93)
hud_text("Accept", 0, 0.42, 0.1, WHITE, 800, 912, d=5.9)

# End card
hud_panel((0, 0, 0), 0, 0, 1.1, 1.1, 912, TOTAL, d=5.8)
hud_text("TO BE\nCONTINUED...", 0, 0, 0.35, WHITE, 928, TOTAL, d=5.7)

# ---------- Alex name tag + glitch ----------
tag_cu = bpy.data.curves.new("tag", 'FONT')
tag_cu.body, tag_cu.size, tag_cu.align_x = "Alex", 0.9, 'CENTER'
tag_cu.materials.append(mat(WHITE))
tag = link(bpy.data.objects.new("tag", tag_cu))
tag.location = (0, ALEX_Y, 6.4)
c = tag.constraints.new('TRACK_TO')
c.target, c.track_axis, c.up_axis = cam, 'TRACK_Z', 'UP_Y'
show(tag, 100, 480)

random.seed(7)
for f in range(360, 480, 3):
    alex.location = (random.uniform(-0.25, 0.25), ALEX_Y, 0)
    alex.keyframe_insert("location", frame=f)
    s = random.uniform(0.7, 1.4)
    tag.scale = (s, s, s)
    tag.keyframe_insert("scale", frame=f)
alex.location = (0, ALEX_Y, 0); alex.keyframe_insert("location", frame=480)
tag.scale = (1, 1, 1); tag.keyframe_insert("scale", frame=480)

bpy.ops.render.render(animation=True)
