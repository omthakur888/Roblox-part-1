#!/usr/bin/env python3
"""
Story -> 2D video.

    python story2video.py story.json -o final.mp4

Reads story.json (scenes, characters, dialogue, sound effects), then:
  1. makes the voices (your recordings, or natural TTS if edge-tts works),
  2. draws every frame in 2D and encodes a silent video,
  3. makes any missing sound effects / ambience / music,
  4. mixes everything with render.py and gives you final.mp4.
No subtitles or captions are ever drawn.

Needs: ffmpeg, pillow, numpy.  Optional: edge-tts
"""
import argparse
import hashlib
import json
import math
import random
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageColor, ImageDraw

import render  # the audio mixer (render.py, same folder)

ROOT = Path(__file__).resolve().parent
SR = 44100

# ------------------------------------------------------------------ sounds
def _norm(x, peak=0.9):
    m = np.max(np.abs(x)) or 1.0
    return x / m * peak


def _lowpass(x, alpha):
    a = np.full(len(x), alpha) if np.isscalar(alpha) else alpha
    y = np.zeros(len(x))
    acc = 0.0
    for i in range(len(x)):
        acc += a[i] * (x[i] - acc)
        y[i] = acc
    return y


def _t(dur):
    return np.arange(int(dur * SR)) / SR


def _loopable(x, fade=0.5):
    f = int(fade * SR)
    n = len(x) - f
    out = x[:n].copy()
    ramp = np.linspace(0, 1, f)
    out[:f] = x[:f] * ramp + x[n:n + f] * (1 - ramp)
    return out


def s_whoosh():
    tt = _t(1.4)
    p = np.sin(np.pi * tt / 1.4)
    return _norm(_lowpass(np.random.randn(len(tt)), 0.02 + 0.5 * p ** 2) * p ** 2)


def s_riser():
    tt = _t(3.0)
    f = 200 + 1600 * (tt / 3.0) ** 2
    tone = np.sin(2 * np.pi * np.cumsum(f) / SR)
    noise = _lowpass(np.random.randn(len(tt)), 0.1)
    return _norm((0.5 * tone + 0.5 * noise) * (tt / 3.0) ** 2)


def s_thruster():
    tt = _t(3.0)
    rumble = _lowpass(np.random.randn(len(tt)), 0.03) * 3
    crackle = _lowpass(np.random.randn(len(tt)), 0.2) * 0.4
    env = np.clip(tt / 0.3, 0, 1) * np.clip((3.0 - tt) / 0.6, 0, 1)
    return _norm((rumble + crackle + 0.5 * np.sin(2 * np.pi * 55 * tt)) * env)


def s_impact():
    tt = _t(0.7)
    f = 420 * np.exp(-tt * 6) + 90
    tone = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-tt * 7)
    click = np.random.randn(len(tt)) * np.exp(-tt * 120) * 0.6
    return _norm(tone + click)


def s_footsteps():
    out = np.zeros(int(2.4 * SR))
    rnd = np.random.RandomState(3)
    for k in range(6):
        n = int(0.1 * SR)
        step = _lowpass(np.random.randn(n), 0.06) * np.exp(-np.arange(n) / (0.02 * SR))
        s = int(k * 0.4 * SR)
        out[s:s + n] += step * rnd.uniform(0.7, 1.0)
    return _norm(out)


def s_wind():
    tt = _t(10.5)
    x = _lowpass(np.random.randn(len(tt)), 0.04) * (0.7 + 0.3 * np.sin(2 * np.pi * 0.3 * tt))
    return _norm(_loopable(x), 0.8)


def s_hum():
    tt = _t(6.5)
    x = (0.5 * np.sin(2 * np.pi * 80 * tt) + 0.3 * np.sin(2 * np.pi * 160 * tt)
         + 0.15 * np.sin(2 * np.pi * 240 * tt) + 0.2 * _lowpass(np.random.randn(len(tt)), 0.05))
    x *= 0.9 + 0.1 * np.sin(2 * np.pi * 6 * tt)
    return _norm(_loopable(x), 0.8)


def s_pad():
    tt = _t(16.0)
    x = sum(a * np.sin(2 * np.pi * f * tt) for f, a in
            ((55, 0.5), (110, 0.5), (130.8125, 0.35), (164.8125, 0.35), (220, 0.2)))
    x *= 0.7 + 0.3 * np.sin(2 * np.pi * 0.125 * tt)
    return _norm(x, 0.7)


SYNTH = {"whoosh": s_whoosh, "riser": s_riser, "thruster": s_thruster,
         "comedic_impact": s_impact, "footsteps": s_footsteps,
         "wind": s_wind, "vehicle_hum": s_hum, "pad": s_pad}


def write_wav(path, data):
    pcm = (np.clip(data, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def find_sound(name, base, build):
    """Your file in assets/ wins; otherwise a synthesized one is made."""
    assets = base / "assets"
    if assets.exists():
        for ext in ("wav", "mp3", "ogg", "flac", "m4a"):
            hits = sorted(assets.rglob(f"{name}.{ext}"))
            if hits:
                return hits[0]
    if name not in SYNTH:
        print(f"  unknown sound '{name}' - skipped")
        return None
    out = build / "sfx" / f"{name}.wav"
    if not out.exists():
        np.random.seed(1)
        write_wav(out, SYNTH[name]())
    return out


# ------------------------------------------------------------------ drawing
BGS = {"day": ((90, 170, 255), (205, 235, 255)),
       "sunset": ((255, 120, 90), (255, 215, 150)),
       "night": ((10, 15, 45), (55, 65, 120))}


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def ease(p):
    return p * p * (3 - 2 * p)


def gradient(W, H, top, bot):
    arr = np.zeros((H, W, 3), dtype=np.uint8)
    for c in range(3):
        arr[:, :, c] = np.linspace(top[c], bot[c], H)[:, None]
    return Image.fromarray(arr)


class Scenery:
    def __init__(self, W, H, bg):
        top, bot = BGS.get(bg, BGS["day"])
        self.img = gradient(W, H, top, bot)
        self.night = bg == "night"
        rnd = random.Random(7)
        self.clouds = [(rnd.random(), rnd.uniform(0.08, 0.85), rnd.uniform(0.6, 1.4)) for _ in range(9)]
        self.stars = [(rnd.random() * W, rnd.random() * H * 0.85, rnd.random() * 6.28) for _ in range(80)]


def draw_planet(d, x, y, r):
    for i in range(8, 0, -1):
        rr = r + i * r * 0.09
        d.ellipse((x - rr, y - rr, x + rr, y + rr), fill=lerp((255, 225, 150), (90, 55, 130), i / 8))
    d.ellipse((x - r, y - r, x + r, y + r), fill=(255, 214, 125))
    for dx, dy, k in ((-0.3, -0.2, 0.18), (0.25, 0.1, 0.12), (-0.05, 0.38, 0.1)):
        cr = r * k
        d.ellipse((x + dx * r - cr, y + dy * r - cr, x + dx * r + cr, y + dy * r + cr), fill=(236, 182, 92))


def draw_char(d, x, y, name, spec, speaking, emotion, t):
    hair = ImageColor.getrgb(spec.get("color", "#333333"))
    r = 36
    d.ellipse((x - r, y - r, x + r, y + r), fill=(255, 214, 170))
    style = spec.get("style", "spiky" if name == "oddyson" else "cap")
    if style == "spiky":
        for k in range(-2, 3):
            bx = x + k * 14
            d.polygon([(bx - 9, y - r + 8), (bx, y - r - 20 - (5 if k % 2 == 0 else 0)), (bx + 9, y - r + 8)], fill=hair)
        for sx in (-1, 1):
            gx = x + sx * 15
            d.ellipse((gx - 10, y - r + 2, gx + 10, y - r + 22), fill=(150, 220, 255), outline=(40, 40, 40), width=3)
    else:
        d.chord((x - r - 2, y - r - 2, x + r + 2, y + r + 2), 195, 345, fill=hair)
    blink = (t % 3.2) < 0.12
    for sx in (-1, 1):
        ex, ey = x + sx * 14, y + 5
        if blink:
            d.line((ex - 6, ey, ex + 6, ey), fill=(40, 30, 30), width=3)
        else:
            d.ellipse((ex - 7, ey - 7, ex + 7, ey + 7), fill=(255, 255, 255))
            d.ellipse((ex - 3, ey - 3, ex + 4, ey + 4), fill=(30, 25, 25))
    my = y + 23
    if speaking:
        big = 14 if emotion in ("shout", "excited") else (4 if emotion == "whisper" else 8)
        h = 4 + big * abs(math.sin(t * 16))
        w = 7 if emotion == "whisper" or name == "quiet_boy" else 10
        d.ellipse((x - w, my - h / 2, x + w, my + h / 2), fill=(120, 30, 40))
    else:
        d.line((x - 7, my, x + 7, my), fill=(120, 40, 40), width=3)


def draw_frame(sc, scn, t, D, fi, speaker, emotion, W, H, chars):
    img = scn.img.copy()
    d = ImageDraw.Draw(img)
    action = sc.get("action", "idle")
    speed = {"idle": 40, "fly": 200, "thrust": 800, "reveal": 25}.get(action, 40)
    rnd = random.Random(fi)

    if scn.night:
        for x, y, ph in scn.stars:
            r = 1 + (1 if math.sin(t * 3 + ph) > 0.3 else 0)
            d.ellipse((x - r, y - r, x + r, y + r), fill=(255, 255, 230))
    if action == "reveal":
        draw_planet(d, W * 0.78, H * 0.48, 40 + 330 * ease(min(1, t / max(D, 0.1))))

    cloud_col = (80, 90, 130) if scn.night else (255, 255, 255)
    for cx_, cy_, s in scn.clouds:
        x = (cx_ * (W + 400) - t * speed * s) % (W + 400) - 200
        y = cy_ * H
        w, h = 140 * s, 45 * s
        d.ellipse((x - w, y - h, x + w, y + h), fill=cloud_col)
        d.ellipse((x - w * 0.5, y - h * 1.6, x + w * 0.6, y + h * 0.4), fill=cloud_col)

    if action == "thrust":
        for _ in range(16):
            x, y, L = rnd.uniform(0, W), rnd.uniform(0, H), rnd.uniform(120, 400)
            d.line((x, y, x + L, y), fill=(255, 255, 255), width=2)

    cx, cy = W * 0.5, H * 0.56 + 12 * math.sin(t * 2.0)
    if action == "thrust":
        cx += rnd.uniform(-7, 7)
        cy += rnd.uniform(-7, 7)

    flame = {"idle": 0, "fly": 70, "thrust": 230, "reveal": 40}.get(action, 0)
    if flame:
        L = flame * rnd.uniform(0.8, 1.2)
        d.polygon([(cx - 195, cy - 30), (cx - 195 - L, cy + 8), (cx - 195, cy + 46)], fill=(255, 120, 20))
        d.polygon([(cx - 195, cy - 14), (cx - 195 - L * 0.55, cy + 8), (cx - 195, cy + 30)], fill=(255, 235, 130))
    d.polygon([(cx - 60, cy + 40), (cx - 150, cy + 125), (cx + 20, cy + 70)], fill=(60, 70, 105))
    d.polygon([(cx - 190, cy - 55), (cx - 235, cy - 135), (cx - 125, cy - 55)], fill=(230, 60, 70))

    present = sc.get("present", [])
    xs = [cx] if len(present) == 1 else [cx - 65, cx + 65]
    for name, x in zip(present, xs):
        draw_char(d, x, cy - 88, name, chars.get(name, {}), speaker == name, emotion, t)

    d.rounded_rectangle((cx - 200, cy - 55, cx + 200, cy + 70), radius=60, fill=(236, 236, 246))
    d.ellipse((cx + 120, cy - 55, cx + 260, cy + 70), fill=(236, 236, 246))
    d.rectangle((cx - 150, cy + 20, cx + 190, cy + 38), fill=(230, 60, 70))
    d.ellipse((cx - 135, cy - 155, cx + 135, cy - 40), outline=(170, 220, 255), width=6)

    if action == "reveal" and t < 0.5:
        img = Image.blend(img, Image.new("RGB", (W, H), (255, 255, 255)), 1 - t / 0.5)
    return img


# ------------------------------------------------------------------ voices
def get_voice(ln, chars, base, build):
    """Returns (path or None, duration, is_user_recording)."""
    f = ln.get("file")
    if f and (base / f).exists():
        return base / f, render.probe_duration(base / f), True
    text = ln.get("text", "")
    name = ln.get("character", "")
    voice = (chars.get(name, {}).get("tts_voice")
             or render.CHARACTERS.get(name, {}).get("tts_voice", "en-US-GuyNeural"))
    out = build / "voice" / f"{hashlib.md5((text + voice).encode()).hexdigest()[:10]}.mp3"
    if not (out.exists() and out.stat().st_size > 1000):
        ok = render.tts(text, voice, out)
        if not ok or not out.exists() or out.stat().st_size < 1000:
            if out.exists():
                out.unlink()
            print(f"  no voice for: {text[:40]}... (record it or fix TTS)")
            return None, 0.45 * len(text.split()) + 0.6, False
    return out, render.probe_duration(out), False


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("story")
    ap.add_argument("-o", "--output", default="final.mp4")
    args = ap.parse_args()

    story_path = Path(args.story).resolve()
    base = story_path.parent
    story = json.loads(story_path.read_text(encoding="utf-8"))
    W, H = story.get("size", [1280, 720])
    fps = story.get("fps", 24)
    chars = story.get("characters", {})
    build = base / "build"
    (build / "voice").mkdir(parents=True, exist_ok=True)
    (build / "sfx").mkdir(parents=True, exist_ok=True)
    rel = lambda p: Path(p).resolve().relative_to(base).as_posix()

    # ---- 1. plan the timeline (voices decide how long each scene is)
    print("Making voices...")
    plan, t0 = [], 0.0
    timeline = {"video": "build/silent.mp4", "dialogue": [], "sfx": [],
                "ambience": [], "music": [], "silence": []}
    for si, sc in enumerate(story["scenes"]):
        cur, gap = sc.get("lead_in", 0.6), sc.get("gap", 0.35)
        lines = []
        for ln in sc.get("lines", []):
            path, dur, mine = get_voice(ln, chars, base, build)
            lines.append({**ln, "start": cur, "dur": dur})
            if path:
                entry = {"character": ln["character"], "start": round(t0 + cur, 3),
                         "emotion": ln.get("emotion", "neutral"), "file": rel(path)}
                if mine:
                    entry["recorded_as_is"] = True
                timeline["dialogue"].append(entry)
            cur += dur + gap
        D = max(cur + sc.get("pause_after", 0.4) - gap, sc.get("duration", 0))
        for s in sc.get("sfx", []):
            p = find_sound(s["name"], base, build)
            at = s.get("at", 0)
            at = max(0, D - 1.0) if at == "end" else float(at)
            if p:
                timeline["sfx"].append({"file": rel(p), "start": round(t0 + at, 3), "gain": s.get("gain", -4)})
        if sc.get("silence"):
            timeline["silence"].append([round(t0, 3), round(t0 + D, 3)])
        plan.append({"sc": sc, "lines": lines, "D": D, "t0": t0})
        t0 += D
    total = t0
    for name in story.get("ambience", []):
        p = find_sound(name, base, build)
        if p:
            timeline["ambience"].append({"file": rel(p), "gain": -18})
    if story.get("music"):
        p = find_sound(story["music"], base, build)
        if p:
            timeline["music"].append({"file": rel(p), "gain": -16})
    (base / "build_timeline.json").write_text(json.dumps(timeline, indent=2))

    # ---- 2. draw frames -> silent video
    print(f"Drawing {total:.1f}s of video at {W}x{H}, {fps} fps...")
    silent = build / "silent.mp4"
    ff = subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
         "-s", f"{W}x{H}", "-r", str(fps), "-i", "-", "-c:v", "libx264",
         "-pix_fmt", "yuv420p", "-preset", "veryfast", "-crf", "20", str(silent)],
        stdin=subprocess.PIPE)
    black = Image.new("RGB", (W, H), (0, 0, 0))
    fi = 0
    for p in plan:
        sc, D = p["sc"], p["D"]
        scn = Scenery(W, H, sc.get("bg", "day"))
        for f in range(int(round(D * fps))):
            t = f / fps
            speaker, emotion = None, "neutral"
            for ln in p["lines"]:
                if ln["start"] <= t < ln["start"] + ln["dur"]:
                    speaker, emotion = ln["character"], ln.get("emotion", "neutral")
            img = draw_frame(sc, scn, t, D, fi, speaker, emotion, W, H, chars)
            gt = p["t0"] + t
            fade = 0.0
            if gt < 0.4:
                fade = 1 - gt / 0.4
            elif gt > total - 0.6:
                fade = (gt - (total - 0.6)) / 0.6
            if fade > 0:
                img = Image.blend(img, black, min(1, fade))
            try:
                ff.stdin.write(img.tobytes())
            except BrokenPipeError:
                sys.exit("ffmpeg stopped while encoding the video.")
            fi += 1
    ff.stdin.close()
    if ff.wait() != 0:
        sys.exit("Video encoding failed.")

    # ---- 3. mix sound onto the video
    print("Mixing sound...")
    r = subprocess.run([sys.executable, str(ROOT / "render.py"),
                        str(base / "build_timeline.json"), "-o", args.output])
    if r.returncode != 0:
        sys.exit("Audio mixing failed (see message above).")
    print(f"\nDone: {args.output}")


if __name__ == "__main__":
    main()
