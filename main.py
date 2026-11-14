import math
import os
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw

W, H = 540, 960
FPS_RENDER = 12
DURATION = 50
OUT_DIR = Path("output")
OUT_DIR.mkdir(exist_ok=True)

# Story beats: start time, end time, scene id
SCENES = [
    (0, 8, "town"),
    (8, 16, "odyson"),
    (16, 25, "experiment"),
    (25, 34, "fall"),
    (34, 42, "reveal"),
    (42, 50, "lesson"),
]

def clamp(v, lo=0.0, hi=1.0):
    return max(lo, min(hi, v))

def smooth(t):
    t = clamp(t)
    return t * t * (3 - 2 * t)

def lerp(a, b, t):
    return a + (b - a) * t

def draw_gradient(draw, top, bottom):
    for y in range(H):
        q = y / max(1, H - 1)
        c = tuple(int(lerp(top[i], bottom[i], q)) for i in range(3))
        draw.line((0, y, W, y), fill=c)

def rounded(draw, box, radius, fill, outline=None, width=1):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)

def draw_clouds(draw, t):
    for i in range(5):
        x = int((i * 145 + t * 13) % (W + 180) - 90)
        y = 100 + (i % 3) * 75
        col = (255, 255, 255, 150)
        draw.ellipse((x, y, x+90, y+35), fill=(219, 239, 255))
        draw.ellipse((x+25, y-18, x+75, y+38), fill=(232, 246, 255))

def draw_town_bg(img, t, lava=True):
    d = ImageDraw.Draw(img)
    draw_gradient(d, (38, 70, 128), (115, 178, 211))
    draw_clouds(d, t)
    # distant blocky buildings
    for i in range(8):
        x = i * 78 - 15
        bh = 190 + (i * 37) % 130
        y = 650 - bh
        rounded(d, (x, y, x+65, 680), 7, (65 + i*5, 104 + i*3, 157 + i*2))
        for wx in range(x+12, x+58, 22):
            for wy in range(y+25, 630, 45):
                d.rectangle((wx, wy, wx+9, wy+14), fill=(255, 220, 125))
    # ground / lava myth
    if lava:
        d.rectangle((0, 790, W, H), fill=(207, 70, 26))
        for i in range(10):
            x = (i*71 + int(t*25)) % (W+60)-30
            y = 815 + (i%3)*42
            d.ellipse((x, y, x+55, y+18), fill=(255, 170, 35))
        # floating platforms
        for i in range(4):
            x = 25 + i*135
            y = 700 - (i%2)*45
            rounded(d, (x, y, x+100, y+22), 8, (88, 103, 126), (210, 225, 245), 2)
            d.rectangle((x+15, y+22, x+85, y+28), fill=(50, 57, 75))
    else:
        d.rectangle((0, 790, W, H), fill=(103, 139, 91))
        d.rectangle((0, 790, W, 806), fill=(145, 180, 112))

def draw_thruster(draw, x, y, active=True):
    rounded(draw, (x-11, y-3, x+11, y+28), 5, (70, 78, 96), (210, 220, 235), 2)
    if active:
        draw.polygon([(x-8,y+28),(x+8,y+28),(x,y+58)], fill=(255, 133, 35))
        draw.polygon([(x-4,y+28),(x+4,y+28),(x,y+47)], fill=(255, 230, 95))

def draw_character(draw, x, y, name="odyson", scale=1.0, pose="stand", t=0, shocked=False):
    # coordinates are top-left; body proportions are deliberately blocky / game-like
    s = scale
    bob = math.sin(t*5) * 3 if pose in ("stand", "walk") else 0
    x, y = int(x), int(y+bob)
    skin = (242, 184, 137)
    if name == "odyson":
        shirt, pants, hair = (36, 151, 225), (39, 51, 83), (54, 35, 25)
    elif name == "maggit":
        shirt, pants, hair = (120, 205, 135), (48, 67, 94), (45, 38, 34)
    else:
        shirt, pants, hair = (236, 171, 63), (55, 66, 91), (65, 43, 28)
    # limbs, animated swing
    swing = math.sin(t*8) * 10 if pose == "walk" else 0
    if pose == "fall":
        swing = 22
    # legs
    leg_y = y + int(80*s)
    draw.line((x+int(20*s), leg_y, x+int((14+swing/3)*s), y+int(124*s)), fill=pants, width=max(5,int(13*s)))
    draw.line((x+int(43*s), leg_y, x+int((51-swing/3)*s), y+int(124*s)), fill=pants, width=max(5,int(13*s)))
    # shoes
    rounded(draw, (x+int(2*s), y+int(119*s), x+int(27*s), y+int(130*s)), 4, (30, 34, 45))
    rounded(draw, (x+int(42*s), y+int(119*s), x+int(67*s), y+int(130*s)), 4, (30, 34, 45))
    # torso
    rounded(draw, (x+int(5*s), y+int(39*s), x+int(60*s), y+int(91*s)), 7, shirt, (20, 30, 48), 2)
    # arms
    arm_color = skin
    if pose == "fall":
        draw.line((x+int(8*s), y+int(48*s), x-int(17*s), y+int(25*s)), fill=arm_color, width=max(5,int(12*s)))
        draw.line((x+int(57*s), y+int(48*s), x+int(82*s), y+int(23*s)), fill=arm_color, width=max(5,int(12*s)))
    else:
        draw.line((x+int(8*s), y+int(49*s), x+int((swing/2)*s), y+int(82*s)), fill=arm_color, width=max(5,int(12*s)))
        draw.line((x+int(57*s), y+int(49*s), x+int((68-swing/2)*s), y+int(82*s)), fill=arm_color, width=max(5,int(12*s)))
    # head
    rounded(draw, (x+int(7*s), y, x+int(59*s), y+int(45*s)), 10, skin, (55, 43, 40), 2)
    # hair
    rounded(draw, (x+int(5*s), y-int(4*s), x+int(61*s), y+int(14*s)), 8, hair)
    # face
    eye_y = y + int(21*s)
    if shocked:
        draw.ellipse((x+int(19*s), eye_y-int(4*s), x+int(26*s), eye_y+int(4*s)), fill=(255,255,255))
        draw.ellipse((x+int(42*s), eye_y-int(4*s), x+int(49*s), eye_y+int(4*s)), fill=(255,255,255))
        draw.ellipse((x+int(21*s), eye_y-int(1*s), x+int(24*s), eye_y+int(3*s)), fill=(20,25,35))
        draw.ellipse((x+int(44*s), eye_y-int(1*s), x+int(47*s), eye_y+int(3*s)), fill=(20,25,35))
        draw.ellipse((x+int(31*s), y+int(30*s), x+int(40*s), y+int(40*s)), fill=(80,35,35))
    else:
        draw.ellipse((x+int(19*s), eye_y, x+int(25*s), eye_y+int(6*s)), fill=(25,30,40))
        draw.ellipse((x+int(42*s), eye_y, x+int(48*s), eye_y+int(6*s)), fill=(25,30,40))
        draw.line((x+int(29*s), y+int(35*s), x+int(39*s), y+int(35*s)), fill=(120,55,55), width=max(1,int(2*s)))
    # Maggit's emergency pack
    if name == "maggit":
        rounded(draw, (x+int(47*s), y+int(48*s), x+int(69*s), y+int(79*s)), 5, (70, 78, 96), (220,225,235), 2)
        if pose == "fly":
            draw_thruster(draw, x+int(57*s), y+int(76*s), True)

def draw_bed(draw, x, y, t):
    bob = math.sin(t*2.5)*7
    y = int(y+bob)
    rounded(draw, (x, y, x+170, y+28), 10, (112, 67, 160), (230,220,255), 3)
    rounded(draw, (x+12, y-25, x+75, y+4), 9, (245,245,255))
    for xx in (x+28, x+142):
        draw_thruster(draw, xx, y+20, True)

def draw_bike(draw, x, y, t):
    y += int(math.sin(t*4)*8)
    draw.ellipse((x, y+25, x+45, y+70), outline=(28,36,54), width=5)
    draw.ellipse((x+90, y+25, x+135, y+70), outline=(28,36,54), width=5)
    draw.line((x+22,y+48,x+65,y+12,x+112,y+48), fill=(65,210,240), width=8)
    draw.line((x+65,y+12,x+82,y+45), fill=(65,210,240), width=7)
    draw_thruster(draw, x+70, y+48, True)

def frame_at(t):
    img = Image.new("RGB", (W, H), (30, 50, 80))
    scene = next(s[2] for s in SCENES if s[0] <= t < s[1])
    lava = scene != "lesson" and scene != "reveal"
    draw_town_bg(img, t, lava=lava)
    d = ImageDraw.Draw(img)

    if scene == "town":
        # floating school chair and residents
        rounded(d, (210, 610, 330, 635), 8, (74, 85, 110), (230,230,245), 2)
        draw_thruster(d, 230, 625, True)
        draw_thruster(d, 310, 625, True)
        draw_character(d, 235, 475, "extra", 1.0, "stand", t)
        draw_bed(d, 25, 390, t)
        draw_bike(d, 330, 330, t)
        draw_character(d, 100, 660, "extra", .72, "stand", t)
    elif scene == "odyson":
        draw_bed(d, 40, 370, t)
        draw_character(d, 90, 260, "odyson", 1.45, "stand", t)
        draw_bike(d, 300, 500, t)
        # school chair
        rounded(d, (190, 675, 350, 700), 8, (70,80,110), (230,230,245), 2)
        draw_thruster(d, 215, 690, True)
        draw_thruster(d, 325, 690, True)
    elif scene == "experiment":
        draw_character(d, 125, 555, "odyson", 1.25, "stand", t)
        draw_character(d, 330, 555, "maggit", 1.25, "stand", t, shocked=False)
        # nervous marks
        d.arc((355, 525, 395, 555), 190, 330, fill=(255,255,255), width=3)
        # Odyson reaches toward Maggit
        d.line((210, 620, 295, 600), fill=(242,184,137), width=13)
    elif scene == "fall":
        q = smooth((t-25)/9)
        oy = int(390 + q*365)
        mx = 340
        draw_character(d, 120, oy, "odyson", 1.2, "fall", t, shocked=True)
        draw_character(d, mx, int(520-q*120), "maggit", 1.15, "fly", t, shocked=True)
        # crowd watching
        for i in range(4):
            draw_character(d, 15+i*130, 715, "extra", .62, "stand", t, shocked=True)
        # motion streaks
        for i in range(4):
            d.line((165+i*18, oy-70, 150+i*18, oy-120), fill=(255,255,255), width=3)
    elif scene == "reveal":
        # ordinary grass floor, Odyson safe
        draw_character(d, 205, 665, "odyson", 1.45, "stand", t, shocked=True)
        draw_character(d, 55, 635, "maggit", 1.0, "stand", t)
        for i in range(4):
            draw_character(d, 355, 650-i*4, "extra", .62, "stand", t, shocked=True)
        d.ellipse((190, 805, 360, 830), fill=(70,100,65))
        # reveal rays
        for a in range(0, 360, 45):
            cx, cy = 275, 570
            ex = cx + int(math.cos(math.radians(a))*100)
            ey = cy + int(math.sin(math.radians(a))*100)
            d.line((cx,cy,ex,ey), fill=(255,235,120), width=4)
    elif scene == "lesson":
        draw_character(d, 65, 650, "odyson", 1.1, "stand", t)
        draw_character(d, 225, 650, "maggit", 1.1, "stand", t)
        for i in range(3):
            draw_character(d, 380, 660, "extra", .7, "walk", t+i)
        # grass and path
        d.rectangle((0, 790, W, 960), fill=(103,139,91))
        d.rectangle((0, 850, W, 960), fill=(173,150,112))
        for i in range(8):
            x = (i*83 + int(t*12)) % W
            d.ellipse((x, 760-(i%3)*18, x+8, 768-(i%3)*18), fill=(255,230,120))

    # subtle vignette
    overlay = Image.new("RGBA", (W,H), (0,0,0,0))
    od = ImageDraw.Draw(overlay)
    for i in range(18):
        alpha = int(2 + i*1.2)
        od.rectangle((i*8, i*8, W-i*8, H-i*8), outline=(0,0,0,alpha), width=8)
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    return img

def main():
    ffmpeg = os.environ.get("FFMPEG", "ffmpeg")
    check = subprocess.run([ffmpeg, "-version"], capture_output=True, text=True)
    if check.returncode != 0:
        raise RuntimeError("FFmpeg was not found. Install FFmpeg and try again.")

    sample = os.environ.get("SAMPLE", "0") == "1"
    duration = 5 if sample else DURATION
    total = duration * FPS_RENDER
    out = OUT_DIR / ("sample.mp4" if sample else "odyson_floor_is_lava.mp4")

    cmd = [
        ffmpeg, "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
        "-s", f"{W}x{H}", "-r", str(FPS_RENDER), "-i", "-",
        "-an", "-c:v", "libx264", "-preset", "ultrafast",
        "-crf", "24", "-pix_fmt", "yuv420p",
        "-vf", "scale=1080:1920:flags=fast_bilinear,fps=24",
        "-movflags", "+faststart", str(out)
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    try:
        for i in range(total):
            t = i / FPS_RENDER
            frame = frame_at(t)
            proc.stdin.write(frame.tobytes())
            if i % (FPS_RENDER * 5) == 0:
                print(f"Rendered {i}/{total} frames ({100*i/max(1,total):.1f}%)", flush=True)
        proc.stdin.close()
        code = proc.wait()
        if code != 0:
            raise RuntimeError(f"FFmpeg exited with code {code}")
    except Exception:
        proc.kill()
        raise

    # Optional narration: place a narration.wav or narration.mp3 in the project root.
    narration = next((p for p in (Path("narration.wav"), Path("narration.mp3")) if p.exists()), None)
    if narration and not sample:
        muxed = OUT_DIR / "odyson_floor_is_lava_with_narration.mp4"
        subprocess.run([
            ffmpeg, "-y", "-i", str(out), "-i", str(narration),
            "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
            "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags",
            "+faststart", str(muxed)
        ], check=True)
        print(f"Created {muxed}")
    else:
        print(f"Created {out}")
        if not sample:
            print("No narration file found. Add narration.wav or narration.mp3 to include voiceover.")

if __name__ == "__main__":
    main()
