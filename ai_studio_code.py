#!/usr/bin/env python3
"""
Complete 3D Roblox-Style YouTube Short Generator (Blender 4.x + Edge TTS + Procedural Audio)
Title: IN THIS TOWN, NOBODY IS ALLOWED TO SCREAM!
"""

import os
import sys
import math
import wave
import struct
import random
import shutil
import asyncio
import argparse
import platform
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DIRS = ["assets", "audio", "renders", "renders/frames_full", "renders/frames_preview", "output"]


def ensure_dirs():
    for d in DIRS:
        (BASE_DIR / d).mkdir(parents=True, exist_ok=True)


DEFAULT_CONFIG = {
    "project": {
        "name": "roblox_short",
        "title": "IN THIS TOWN, NOBODY IS ALLOWED TO SCREAM!",
        "final_video": "roblox_short_final.mp4",
        "preview_video": "preview_10_seconds.mp4",
    },
    "video": {
        "width": 1080,
        "height": 1920,
        "fps": 30,
        "duration_seconds": 57,
        "preview_seconds": 10,
        "engine": "EEVEE",
        "samples": 24,
        "preview_samples": 12,
        "motion_blur": True,
        "motion_blur_shutter": 0.45,
        "use_dof": True,
        "dof_fstop": 2.8,
    },
    "audio": {
        "tts_provider": "edge_tts",
        "edge_voice": "en-US-AndrewNeural",
        "edge_rate": "+4%",
        "edge_pitch": "-2Hz",
        "sample_rate": 44100,
        "music_volume": 0.28,
        "music_duck_volume": 0.12,
        "ambience_volume": 0.22,
        "sfx_volume": 0.85,
        "narration_volume": 1.0,
    },
    "characters": {
        "maya": {
            "skin_color": [0.85, 0.66, 0.52, 1.0],
            "hair_color": [0.16, 0.08, 0.04, 1.0],
            "hoodie_color": [0.36, 0.11, 0.58, 1.0],
            "pants_color": [0.05, 0.05, 0.06, 1.0],
            "shoe_color": [0.85, 0.85, 0.88, 1.0],
        },
        "andy": {
            "skin_color": [0.88, 0.70, 0.56, 1.0],
            "hair_color": [0.10, 0.07, 0.05, 1.0],
            "shirt_color": [0.10, 0.34, 0.78, 1.0],
            "pants_color": [0.08, 0.09, 0.14, 1.0],
            "shoe_color": [0.15, 0.15, 0.16, 1.0],
            "headphone_color": [0.12, 0.12, 0.14, 1.0],
        },
        "monster": {
            "body_color": [0.015, 0.015, 0.02, 1.0],
            "eye_color": [1.0, 0.08, 0.05, 1.0],
            "eye_strength": 22.0,
            "scale": 1.72,
        },
    },
    "scenes": {
        "scene_1": {
            "start": 0.0,
            "end": 7.0,
            "narration": "In this town, nobody was allowed to scream. Because if you screamed... something came for you.",
        },
        "scene_2": {
            "start": 7.0,
            "end": 15.0,
            "narration": "But Maya didn't believe the rule. So she decided to test it on Andy.",
        },
        "scene_3": {
            "start": 15.0,
            "end": 25.0,
            "narration": "Andy couldn't hear much around him. Maya secretly changed his headphones. He didn't even notice.",
        },
        "scene_4": {
            "start": 25.0,
            "end": 40.0,
            "narration": "She tried everything to make him scream. But Andy didn't react. Until Maya switched off his noise cancellation...",
        },
        "scene_5": {
            "start": 40.0,
            "end": 50.0,
            "narration": "Then he heard something behind him... and screamed!",
        },
        "scene_6": {
            "start": 50.0,
            "end": 57.0,
            "narration": "The monster was real. Maya escaped... but Andy was never seen again.",
            "end_card_text": "WOULD YOU SCREAM?",
        },
    },
}


def deep_merge(base, override):
    out = dict(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config():
    cfg_path = BASE_DIR / "config.yml"
    if cfg_path.exists():
        try:
            import yaml  # type: ignore
            with open(cfg_path, "r", encoding="utf-8") as f:
                loaded = yaml.safe_load(f)
            return deep_merge(DEFAULT_CONFIG, loaded)
        except Exception:
            pass
    return DEFAULT_CONFIG


# ---------------------------------------------------------------------------
# AUDIO GENERATION (Edge TTS + Offline Fallbacks + Procedural WAV SFX/Music)
# ---------------------------------------------------------------------------

def write_wav_stereo(path: Path, samples_l, samples_r, sr=44100):
    n = min(len(samples_l), len(samples_r))
    with wave.open(str(path), "w") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        frames = bytearray()
        for i in range(n):
            lv = max(-1.0, min(1.0, samples_l[i]))
            rv = max(-1.0, min(1.0, samples_r[i]))
            frames += struct.pack("<hh", int(lv * 32767), int(rv * 32767))
        wf.writeframes(bytes(frames))


def synthesize_audio_assets(cfg):
    sr = int(cfg["audio"]["sample_rate"])
    audio_dir = BASE_DIR / "audio"
    rng = random.Random(42)

    # 1. Suspense background music (57s dark minor drone + pulse + high tension strings)
    music_path = audio_dir / "music_suspense.wav"
    if not music_path.exists():
        dur = float(cfg["video"]["duration_seconds"])
        n = int(dur * sr)
        ml = [0.0] * n
        mr = [0.0] * n
        notes = [55.0, 65.41, 61.74, 58.27]  # A1, C2, B1, Bb1
        for i in range(n):
            t = i / sr
            bar = int(t // 4.0) % len(notes)
            f0 = notes[bar]
            pulse = 0.55 + 0.45 * math.sin(2.0 * math.pi * 1.5 * t)
            sub = 0.36 * math.sin(2.0 * math.pi * f0 * t)
            fifth = 0.18 * math.sin(2.0 * math.pi * (f0 * 1.498) * t + 0.3)
            # Tension rises sharply after t=38s
            tension = max(0.0, min(1.0, (t - 35.0) / 15.0))
            shimmer = tension * 0.20 * math.sin(2.0 * math.pi * (f0 * 8.0 + 3.0 * math.sin(t * 5.0)) * t)
            hb_phase = (t * (1.2 + tension * 1.5)) % 1.0
            heartbeat = (0.30 if hb_phase < 0.08 else 0.0) * math.sin(2.0 * math.pi * 48.0 * hb_phase) * math.exp(-hb_phase * 28.0)
            env = min(1.0, t / 1.5) * min(1.0, (dur - t) / 1.0)
            val = env * (pulse * (sub + fifth) + shimmer + heartbeat)
            ml[i] = val * 0.95
            mr[i] = val * 0.95 + tension * 0.04 * math.sin(2.0 * math.pi * 220.0 * t)
        write_wav_stereo(music_path, ml, mr, sr)

    # 2. Night ambience (filtered wind + crickets)
    amb_path = audio_dir / "ambience_night.wav"
    if not amb_path.exists():
        dur = float(cfg["video"]["duration_seconds"])
        n = int(dur * sr)
        al = [0.0] * n
        ar = [0.0] * n
        lp_l, lp_r = 0.0, 0.0
        for i in range(n):
            t = i / sr
            wl = rng.uniform(-1.0, 1.0)
            wr = rng.uniform(-1.0, 1.0)
            lp_l = lp_l * 0.985 + wl * 0.015
            lp_r = lp_r * 0.985 + wr * 0.015
            wind_mod = 0.5 + 0.5 * math.sin(2.0 * math.pi * 0.17 * t)
            chirp_gate = 1.0 if (t % 2.4) < 0.35 and ((t * 14.0) % 1.0) < 0.45 else 0.0
            cricket = chirp_gate * 0.05 * math.sin(2.0 * math.pi * 4250.0 * t)
            al[i] = lp_l * (1.8 + wind_mod) + cricket * 0.7
            ar[i] = lp_r * (1.8 + wind_mod) + cricket * 1.1
        write_wav_stereo(amb_path, al, ar, sr)

    # 3. Footstep SFX
    step_path = audio_dir / "sfx_footstep.wav"
    if not step_path.exists():
        n = int(0.18 * sr)
        sl = []
        sr_buf = []
        for i in range(n):
            t = i / sr
            env = math.exp(-t * 32.0)
            thud = math.sin(2.0 * math.pi * (95.0 - 45.0 * t) * t)
            grit = rng.uniform(-0.25, 0.25) * math.exp(-t * 45.0)
            v = env * (0.65 * thud + grit)
            sl.append(v)
            sr_buf.append(v)
        write_wav_stereo(step_path, sl, sr_buf, sr)

    # 4. Headphone swap whoosh + soft click
    swap_path = audio_dir / "sfx_swap.wav"
    if not swap_path.exists():
        n = int(0.65 * sr)
        sl, sr_buf = [], []
        lp = 0.0
        for i in range(n):
            t = i / sr
            lp = lp * 0.92 + rng.uniform(-1.0, 1.0) * 0.08
            whoosh = lp * 2.5 * math.sin(math.pi * min(1.0, t / 0.55))
            click = (0.45 * math.sin(2.0 * math.pi * 1600.0 * (t - 0.35)) * math.exp(-(t - 0.35) * 60.0)) if t > 0.35 else 0.0
            sl.append(whoosh * 0.9 + click)
            sr_buf.append(whoosh * 1.1 + click)
        write_wav_stereo(swap_path, sl, sr_buf, sr)

    # 5. Noise-cancellation switch OFF click + low hum drop
    switch_path = audio_dir / "sfx_switch.wav"
    if not switch_path.exists():
        n = int(0.9 * sr)
        sl, sr_buf = [], []
        for i in range(n):
            t = i / sr
            click = 0.8 * math.sin(2.0 * math.pi * 2100.0 * t) * math.exp(-t * 75.0)
            drop = 0.45 * math.sin(2.0 * math.pi * (180.0 * math.exp(-t * 3.0)) * t) * math.exp(-t * 4.0)
            sl.append(click + drop)
            sr_buf.append(click + drop)
        write_wav_stereo(switch_path, sl, sr_buf, sr)

    # 6. Funny trick pop / honk
    honk_path = audio_dir / "sfx_honk.wav"
    if not honk_path.exists():
        n = int(0.45 * sr)
        sl, sr_buf = [], []
        for i in range(n):
            t = i / sr
            env = math.exp(-t * 6.5) * min(1.0, t / 0.015)
            f = 340.0 + 60.0 * math.sin(2.0 * math.pi * 18.0 * t)
            tone = 0.5 * math.sin(2.0 * math.pi * f * t) + 0.25 * math.sin(2.0 * math.pi * f * 2.0 * t)
            sl.append(env * tone)
            sr_buf.append(env * tone)
        write_wav_stereo(honk_path, sl, sr_buf, sr)

    # 7. Loud megaphone blast
    blast_path = audio_dir / "sfx_blast.wav"
    if not blast_path.exists():
        n = int(0.85 * sr)
        sl, sr_buf = [], []
        for i in range(n):
            t = i / sr
            env = min(1.0, t / 0.01) * math.exp(-t * 4.2)
            raw = math.sin(2.0 * math.pi * 520.0 * t) + 0.7 * math.sin(2.0 * math.pi * 780.0 * t)
            clipped = max(-0.7, min(0.7, raw * 1.8))
            sl.append(env * clipped)
            sr_buf.append(env * clipped)
        write_wav_stereo(blast_path, sl, sr_buf, sr)

    # 8. Monster eerie growl + scream + dramatic impact
    roar_path = audio_dir / "sfx_monster_roar.wav"
    if not roar_path.exists():
        n = int(2.6 * sr)
        sl, sr_buf = [], []
        lp = 0.0
        for i in range(n):
            t = i / sr
            lp = lp * 0.94 + rng.uniform(-1.0, 1.0) * 0.06
            env = min(1.0, t / 0.25) * math.exp(-max(0.0, t - 0.8) * 1.4)
            growl = math.sin(2.0 * math.pi * (68.0 + 18.0 * math.sin(t * 9.0)) * t)
            shriek = 0.35 * math.sin(2.0 * math.pi * (420.0 + 210.0 * math.sin(t * 6.0)) * t)
            v = env * (0.55 * growl + shriek + lp * 2.2)
            sl.append(v)
            sr_buf.append(v * 0.95)
        write_wav_stereo(roar_path, sl, sr_buf, sr)

    # 9. Terrified gasp / scream burst
    scream_path = audio_dir / "sfx_scream.wav"
    if not scream_path.exists():
        n = int(1.6 * sr)
        sl, sr_buf = [], []
        for i in range(n):
            t = i / sr
            env = min(1.0, t / 0.06) * math.exp(-max(0.0, t - 0.5) * 2.8)
            f = 580.0 + 240.0 * math.sin(math.pi * min(1.0, t / 0.7)) + 25.0 * math.sin(t * 42.0)
            v = env * (0.55 * math.sin(2.0 * math.pi * f * t) + 0.25 * math.sin(2.0 * math.pi * f * 1.5 * t) + 0.15 * rng.uniform(-1.0, 1.0))
            sl.append(v)
            sr_buf.append(v)
        write_wav_stereo(scream_path, sl, sr_buf, sr)

    # 10. Cinematic sub impact
    impact_path = audio_dir / "sfx_impact.wav"
    if not impact_path.exists():
        n = int(1.8 * sr)
        sl, sr_buf = [], []
        for i in range(n):
            t = i / sr
            boom = math.sin(2.0 * math.pi * (110.0 * math.exp(-t * 3.5) + 32.0) * t) * math.exp(-t * 2.6)
            hit = rng.uniform(-0.8, 0.8) * math.exp(-t * 28.0)
            sl.append(0.85 * boom + hit)
            sr_buf.append(0.85 * boom + hit)
        write_wav_stereo(impact_path, sl, sr_buf, sr)


def _try_edge_tts(lines, cfg):
    try:
        import edge_tts  # type: ignore
    except ImportError:
        return False

    voice = cfg["audio"]["edge_voice"]
    rate = cfg["audio"]["edge_rate"]
    pitch = cfg["audio"]["edge_pitch"]

    async def _gen_all():
        for idx, text, out_mp3 in lines:
            if out_mp3.exists() and out_mp3.stat().st_size > 1000:
                continue
            comm = edge_tts.Communicate(text=text, voice=voice, rate=rate, pitch=pitch)
            await comm.save(str(out_mp3))

    try:
        asyncio.run(_gen_all())
        return all(out_mp3.exists() and out_mp3.stat().st_size > 500 for _, _, out_mp3 in lines)
    except Exception as exc:
        print(f"[Audio] Edge TTS failed ({exc}), trying fallback TTS...")
        return False


def _try_system_tts(lines):
    sys_name = platform.system()
    for idx, text, out_mp3 in lines:
        out_wav = out_mp3.with_suffix(".wav")
        if out_mp3.exists() or out_wav.exists():
            continue
        if sys_name == "Windows":
            ps = (
                "Add-Type -AssemblyName System.Speech; "
                "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                f"$s.SetOutputToWaveFile('{str(out_wav)}'); "
                f"$s.Speak('{text.replace(chr(39), chr(39)*2)}'); "
                "$s.Dispose();"
            )
            subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=False)
        elif sys_name == "Darwin":
            aiff = out_mp3.with_suffix(".aiff")
            subprocess.run(["say", "-o", str(aiff), text], check=False)
            if shutil.which("afconvert") and aiff.exists():
                subprocess.run(["afconvert", "-f", "WAVE", "-d", "LEI16@44100", str(aiff), str(out_wav)], check=False)
        else:
            for bin_name in ("espeak-ng", "espeak"):
                if shutil.which(bin_name):
                    subprocess.run([bin_name, "-s", "155", "-w", str(out_wav), text], check=False)
                    break


def generate_narration_files(cfg):
    audio_dir = BASE_DIR / "audio"
    lines = []
    for i in range(1, 7):
        sc = cfg["scenes"][f"scene_{i}"]
        lines.append((i, sc["narration"], audio_dir / f"narration_{i}.mp3"))

    ok = _try_edge_tts(lines, cfg)
    if not ok:
        # Try invoking external system python if inside Blender Python without edge-tts
        py_bin = shutil.which("python3") or shutil.which("python")
        if py_bin and "blender" in sys.executable.lower():
            cmd = [
                py_bin,
                "-c",
                "import asyncio, edge_tts; "
                + "; ".join(
                    [
                        f"asyncio.run(edge_tts.Communicate({repr(t)}, {repr(cfg['audio']['edge_voice'])}, rate={repr(cfg['audio']['edge_rate'])}, pitch={repr(cfg['audio']['edge_pitch'])}).save({repr(str(p))}))"
                        for _, t, p in lines
                    ]
                ),
            ]
            subprocess.run(cmd, check=False)
            ok = all(p.exists() and p.stat().st_size > 500 for _, _, p in lines)

    if not ok:
        _try_system_tts(lines)

    # Guarantee an existing file path list for every narration line
    resolved = {}
    for i, text, mp3_path in lines:
        wav_path = mp3_path.with_suffix(".wav")
        if mp3_path.exists() and mp3_path.stat().st_size > 500:
            resolved[i] = mp3_path
        elif wav_path.exists() and wav_path.stat().st_size > 500:
            resolved[i] = wav_path
        else:
            # Last-resort placeholder tone cue if completely offline without any OS TTS
            sr = int(cfg["audio"]["sample_rate"])
            n = int(0.4 * sr)
            buf = [0.0] * n
            write_wav_stereo(wav_path, buf, buf, sr)
            resolved[i] = wav_path
    return resolved


# ---------------------------------------------------------------------------
# BLENDER LAUNCHER (when executed via normal `python generate_short.py`)
# ---------------------------------------------------------------------------

def find_blender():
    env_b = os.environ.get("BLENDER_PATH")
    if env_b and Path(env_b).exists():
        return env_b
    w = shutil.which("blender")
    if w:
        return w
    candidates = []
    if platform.system() == "Windows":
        for ver in ("4.4", "4.3", "4.2", "4.1", "4.0"):
            candidates.append(rf"C:\Program Files\Blender Foundation\Blender {ver}\blender.exe")
    elif platform.system() == "Darwin":
        candidates.append("/Applications/Blender.app/Contents/MacOS/Blender")
    else:
        candidates.extend(["/usr/bin/blender", "/usr/local/bin/blender", "/snap/bin/blender"])
    for c in candidates:
        if Path(c).exists():
            return c
    return None


# ---------------------------------------------------------------------------
# BLENDER 3D WORLD, CHARACTERS, ANIMATION & RENDERING
# ---------------------------------------------------------------------------

def run_blender_pipeline(cfg, mode="both"):
    import bpy  # type: ignore
    from mathutils import Euler, Vector  # type: ignore

    fps = int(cfg["video"]["fps"])
    total_frames = int(cfg["video"]["duration_seconds"] * fps)
    preview_frames = int(cfg["video"]["preview_seconds"] * fps)

    narration_paths = generate_narration_files(cfg)
    synthesize_audio_assets(cfg)

    # Reset Blender scene cleanly
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.fps = fps
    scene.frame_start = 1
    scene.frame_end = total_frames
    scene.render.resolution_x = int(cfg["video"]["width"])
    scene.render.resolution_y = int(cfg["video"]["height"])
    scene.render.resolution_percentage = 100

    # Select EEVEE across Blender 4.0-4.5 / 5.x
    engine_ids = [e.identifier for e in scene.render.bl_rna.properties["engine"].enum_items]
    if cfg["video"]["engine"].upper() == "CYCLES":
        scene.render.engine = "CYCLES"
        scene.cycles.samples = int(cfg["video"]["samples"])
    else:
        scene.render.engine = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in engine_ids else "BLENDER_EEVEE"
        if hasattr(scene.eevee, "taa_render_samples"):
            scene.eevee.taa_render_samples = int(cfg["video"]["samples"])

    if hasattr(scene.render, "use_motion_blur"):
        scene.render.use_motion_blur = bool(cfg["video"]["motion_blur"])
        scene.render.motion_blur_shutter = float(cfg["video"]["motion_blur_shutter"])

    # Color management for cinematic night mood
    scene.view_settings.view_transform = "AgX" if "AgX" in [i.identifier for i in scene.view_settings.bl_rna.properties["view_transform"].enum_items] else "Filmic"
    scene.view_settings.exposure = 0.25

    # Compositor Glare (Bloom) compatible with EEVEE Next
    scene.use_nodes = True
    nt = scene.node_tree
    if nt is not None:
        nt.nodes.clear()
        rl = nt.nodes.new("CompositorNodeRLayers")
        glare = nt.nodes.new("CompositorNodeGlare")
        glare.glare_type = "BLOOM" if "BLOOM" in [i.identifier for i in glare.bl_rna.properties["glare_type"].enum_items] else "FOG_GLOW"
        glare.quality = "MEDIUM"
        glare.threshold = 0.85
        glare.size = 7
        comp = nt.nodes.new("CompositorNodeComposite")
        nt.links.new(rl.outputs["Image"], glare.inputs["Image"])
        nt.links.new(glare.outputs["Image"], comp.inputs["Image"])

    # Collections
    col_world = bpy.data.collections.new("Town")
    col_chars = bpy.data.collections.new("Characters")
    col_props = bpy.data.collections.new("Props")
    for c in (col_world, col_chars, col_props):
        scene.collection.children.link(c)

    def link_obj(obj, collection):
        for col in list(obj.users_collection):
            col.objects.unlink(obj)
        collection.objects.link(obj)

    def make_mat(name, color, roughness=0.55, metallic=0.0, emission=None, emission_strength=0.0):
        mat = bpy.data.materials.new(name=name)
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf:
            if "Base Color" in bsdf.inputs:
                bsdf.inputs["Base Color"].default_value = tuple(color)
            if "Roughness" in bsdf.inputs:
                bsdf.inputs["Roughness"].default_value = roughness
            if "Metallic" in bsdf.inputs:
                bsdf.inputs["Metallic"].default_value = metallic
            if emission is not None:
                if "Emission Color" in bsdf.inputs:
                    bsdf.inputs["Emission Color"].default_value = tuple(emission)
                elif "Emission" in bsdf.inputs:
                    bsdf.inputs["Emission"].default_value = tuple(emission)
                if "Emission Strength" in bsdf.inputs:
                    bsdf.inputs["Emission Strength"].default_value = emission_strength
        return mat

    def add_box(name, size, loc, mat, col, bevel=0.02, parent=None):
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=loc)
        obj = bpy.context.active_object
        obj.name = name
        obj.scale = (size[0], size[1], size[2])
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        if bevel > 0.0:
            bev = obj.modifiers.new("Bevel", "BEVEL")
            bev.width = bevel
            bev.segments = 2
        if mat:
            obj.data.materials.append(mat)
        link_obj(obj, col)
        if parent:
            obj.parent = parent
        return obj

    def add_cyl(name, radius, depth, loc, mat, col, rot=(0, 0, 0), parent=None, verts=20):
        bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=radius, depth=depth, location=loc, rotation=rot)
        obj = bpy.context.active_object
        obj.name = name
        if mat:
            obj.data.materials.append(mat)
        link_obj(obj, col)
        if parent:
            obj.parent = parent
        return obj

    def add_empty(name, loc, col, parent=None):
        emp = bpy.data.objects.new(name, None)
        emp.empty_display_size = 0.25
        emp.location = loc
        col.objects.link(emp)
        if parent:
            emp.parent = parent
        return emp

    # -----------------------------------------------------------------------
    # NIGHT WORLD, MOONLIGHT & VOLUMETRIC FOG
    # -----------------------------------------------------------------------
    world = bpy.data.worlds.new("NightWorld")
    scene.world = world
    world.use_nodes = True
    wnodes = world.node_tree.nodes
    wlinks = world.node_tree.links
    wnodes.clear()
    w_bg = wnodes.new("ShaderNodeBackground")
    w_bg.inputs["Color"].default_value = (0.010, 0.015, 0.038, 1.0)
    w_bg.inputs["Strength"].default_value = 0.85
    w_out = wnodes.new("ShaderNodeOutputWorld")
    wlinks.new(w_bg.outputs["Background"], w_out.inputs["Surface"])

    # Moon light
    bpy.ops.object.light_add(type="SUN", location=(12.0, -14.0, 24.0))
    moon_sun = bpy.context.active_object
    moon_sun.name = "MoonLight"
    moon_sun.rotation_euler = (math.radians(52), math.radians(15), math.radians(-30))
    moon_sun.data.color = (0.55, 0.68, 1.0)
    moon_sun.data.energy = 1.65
    link_obj(moon_sun, col_world)

    # Moon disc in the sky
    mat_moon = make_mat("Mat_Moon", (0.9, 0.95, 1.0, 1.0), roughness=0.9, emission=(0.85, 0.92, 1.0, 1.0), emission_strength=6.5)
    bpy.ops.mesh.primitive_uv_sphere_add(radius=3.5, location=(-14.0, 58.0, 26.0))
    moon_orb = bpy.context.active_object
    moon_orb.name = "MoonOrb"
    moon_orb.data.materials.append(mat_moon)
    link_obj(moon_orb, col_world)

    # Volumetric fog box spanning town street
    fog_mat = bpy.data.materials.new("Mat_NightFog")
    fog_mat.use_nodes = True
    fnodes = fog_mat.node_tree.nodes
    flinks = fog_mat.node_tree.links
    fnodes.clear()
    pv = fnodes.new("ShaderNodeVolumePrincipled")
    pv.inputs["Color"].default_value = (0.14, 0.19, 0.34, 1.0)
    pv.inputs["Density"].default_value = 0.014
    pv.inputs["Anisotropy"].default_value = 0.45
    mout = fnodes.new("ShaderNodeOutputMaterial")
    flinks.new(pv.outputs["Volume"], mout.inputs["Volume"])
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0.0, 18.0, 7.0))
    fog_box = bpy.context.active_object
    fog_box.name = "FogVolume"
    fog_box.scale = (46.0, 96.0, 16.0)
    bpy.ops.object.transform_apply(scale=True)
    fog_box.data.materials.append(fog_mat)
    link_obj(fog_box, col_world)

    # -----------------------------------------------------------------------
    # BROOKHAVEN-INSPIRED 3D TOWN ENVIRONMENT
    # -----------------------------------------------------------------------
    mat_road = make_mat("Mat_Road", (0.045, 0.047, 0.055, 1.0), roughness=0.38)
    mat_line = make_mat("Mat_RoadLine", (0.78, 0.65, 0.18, 1.0), roughness=0.6)
    mat_sidewalk = make_mat("Mat_Sidewalk", (0.18, 0.19, 0.21, 1.0), roughness=0.72)
    mat_grass = make_mat("Mat_Grass", (0.04, 0.12, 0.05, 1.0), roughness=0.9)
    mat_pole = make_mat("Mat_Pole", (0.08, 0.09, 0.11, 1.0), roughness=0.35, metallic=0.8)
    mat_lamp_glow = make_mat("Mat_LampGlow", (1.0, 0.85, 0.55, 1.0), emission=(1.0, 0.82, 0.45, 1.0), emission_strength=14.0)
    mat_trunk = make_mat("Mat_Trunk", (0.15, 0.09, 0.05, 1.0), roughness=0.9)
    mat_leaves = make_mat("Mat_Leaves", (0.04, 0.17, 0.07, 1.0), roughness=0.85)
    mat_roof = make_mat("Mat_Roof", (0.09, 0.07, 0.08, 1.0), roughness=0.65)
    mat_door = make_mat("Mat_Door", (0.18, 0.10, 0.06, 1.0), roughness=0.55)
    mat_win_frame = make_mat("Mat_WinFrame", (0.82, 0.84, 0.88, 1.0), roughness=0.4)
    mat_win_glow = make_mat("Mat_WinGlow", (1.0, 0.86, 0.58, 1.0), emission=(1.0, 0.78, 0.40, 1.0), emission_strength=4.5)

    # Road, sidewalks, grass yards
    add_box("Road", (7.0, 90.0, 0.2), (0.0, 18.0, -0.10), mat_road, col_world, bevel=0.01)
    add_box("Sidewalk_L", (3.2, 90.0, 0.26), (-5.1, 18.0, -0.05), mat_sidewalk, col_world, bevel=0.02)
    add_box("Sidewalk_R", (3.2, 90.0, 0.26), (5.1, 18.0, -0.05), mat_sidewalk, col_world, bevel=0.02)
    add_box("Grass_L", (16.0, 90.0, 0.18), (-14.7, 18.0, -0.12), mat_grass, col_world, bevel=0.0)
    add_box("Grass_R", (16.0, 90.0, 0.18), (14.7, 18.0, -0.12), mat_grass, col_world, bevel=0.0)

    for idx, y in enumerate(range(-18, 58, 4)):
        add_box(f"Dash_{idx}", (0.18, 1.8, 0.02), (0.0, float(y), 0.005), mat_line, col_world, bevel=0.0)

    # Houses along both sides (with animated windows for Scene 5 rattle/flicker)
    house_colors = [
        (0.55, 0.58, 0.66, 1.0),
        (0.62, 0.48, 0.42, 1.0),
        (0.45, 0.56, 0.52, 1.0),
        (0.58, 0.55, 0.45, 1.0),
    ]
    animated_windows = []
    house_specs = [
        (-10.2, -4.0, 6.0, 7.0, 5.2, 0),
        (-10.5, 9.5, 6.4, 7.6, 5.6, 1),
        (-10.2, 23.5, 6.0, 7.2, 5.4, 2),
        (-10.6, 37.5, 6.6, 8.0, 6.0, 3),
        (10.2, -2.0, 6.2, 7.2, 5.4, 2),
        (10.4, 12.0, 6.0, 7.0, 5.8, 0),
        (10.3, 26.0, 6.4, 7.4, 5.2, 3),
        (10.6, 39.0, 6.2, 7.8, 5.8, 1),
    ]
    for i, (hx, hy, hw, hd, hh, ci) in enumerate(house_specs):
        h_mat = make_mat(f"Mat_House_{i}", house_colors[ci], roughness=0.7)
        add_box(f"House_{i}_Body", (hw, hd, hh), (hx, hy, hh * 0.5), h_mat, col_world, bevel=0.04)
        add_box(f"House_{i}_Roof", (hw + 0.6, hd + 0.6, 0.7), (hx, hy, hh + 0.35), mat_roof, col_world, bevel=0.05)
        add_box(f"House_{i}_TopRoof", (hw * 0.72, hd * 0.76, 0.9), (hx, hy, hh + 1.05), mat_roof, col_world, bevel=0.05)
        face_x = hx + (hw * 0.5 + 0.04) if hx < 0 else hx - (hw * 0.5 + 0.04)
        add_box(f"House_{i}_Door", (0.12, 1.15, 2.2), (face_x, hy, 1.1), mat_door, col_world, bevel=0.02)
        for wy in (-1.9, 1.9):
            for wz in (1.7, 3.7):
                wf = add_box(f"House_{i}_WinFrame_{wy}_{wz}", (0.14, 1.25, 1.15), (face_x, hy + wy, wz), mat_win_frame, col_world, bevel=0.02)
                wp = add_box(f"House_{i}_WinPane_{wy}_{wz}", (0.16, 1.02, 0.92), (face_x, hy + wy, wz), mat_win_glow, col_world, bevel=0.01)
                animated_windows.append((wf, wp, (face_x, hy + wy, wz)))

    # Alleyway wall where Maya hides in Scene 4
    mat_brick = make_mat("Mat_BrickWall", (0.34, 0.14, 0.12, 1.0), roughness=0.82)
    add_box("Trick_Wall", (1.8, 0.45, 2.6), (-5.2, 16.2, 1.3), mat_brick, col_world, bevel=0.03)

    # Streetlights along sidewalks
    street_lights = []
    for idx, y in enumerate((-6.0, 5.0, 16.0, 27.0, 38.0)):
        side = -1 if idx % 2 == 0 else 1
        px = side * 3.75
        add_cyl(f"Pole_{idx}", 0.09, 4.8, (px, y, 2.4), mat_pole, col_world)
        arm_x = px - side * 0.65
        add_box(f"PoleArm_{idx}", (1.4, 0.12, 0.12), (arm_x, y, 4.75), mat_pole, col_world, bevel=0.02)
        bulb_x = px - side * 1.25
        add_box(f"LampBulb_{idx}", (0.35, 0.28, 0.18), (bulb_x, y, 4.62), mat_lamp_glow, col_world, bevel=0.03)
        bpy.ops.object.light_add(type="SPOT", location=(bulb_x, y, 4.50))
        sp = bpy.context.active_object
        sp.name = f"StreetSpot_{idx}"
        sp.data.color = (1.0, 0.82, 0.48)
        sp.data.energy = 380.0
        sp.data.spot_size = math.radians(108)
        sp.data.spot_blend = 0.55
        link_obj(sp, col_world)
        street_lights.append(sp)

    # Blocky Roblox trees
    for idx, (tx, ty) in enumerate([(-6.9, 2.0), (6.9, 5.5), (-6.9, 19.5), (6.9, 20.5), (-6.9, 32.0), (6.9, 33.5)]):
        add_box(f"TreeTrunk_{idx}", (0.45, 0.45, 2.3), (tx, ty, 1.15), mat_trunk, col_world, bevel=0.02)
        add_box(f"TreeCrownA_{idx}", (2.1, 2.1, 1.5), (tx, ty, 2.85), mat_leaves, col_world, bevel=0.06)
        add_box(f"TreeCrownB_{idx}", (1.5, 1.5, 1.2), (tx, ty, 3.85), mat_leaves, col_world, bevel=0.06)

    # -----------------------------------------------------------------------
    # 3D BLOCKY ROBLOX-INSPIRED CHARACTER RIGS
    # -----------------------------------------------------------------------
    def build_roblox_character(name, palette, hair_style="long", is_monster=False, scale=1.0):
        root = add_empty(f"{name}_Root", (0, 0, 0), col_chars)
        root.scale = (scale, scale, scale)

        mat_skin = make_mat(f"{name}_Skin", palette.get("skin_color", [0.02, 0.02, 0.02, 1.0]), roughness=0.45)
        mat_shirt = make_mat(f"{name}_Shirt", palette.get("hoodie_color", palette.get("shirt_color", [0.015, 0.015, 0.02, 1.0])), roughness=0.65)
        mat_pants = make_mat(f"{name}_Pants", palette.get("pants_color", [0.02, 0.02, 0.025, 1.0]), roughness=0.7)
        mat_shoe = make_mat(f"{name}_Shoes", palette.get("shoe_color", [0.02, 0.02, 0.025, 1.0]), roughness=0.5)
        mat_hair = make_mat(f"{name}_Hair", palette.get("hair_color", [0.02, 0.02, 0.02, 1.0]), roughness=0.6)
        mat_eye_w = make_mat(f"{name}_EyeW", (0.98, 0.98, 0.98, 1.0), roughness=0.2)
        mat_eye_d = make_mat(f"{name}_EyeD", (0.04, 0.04, 0.05, 1.0), roughness=0.15)
        if is_monster:
            mat_eye_d = make_mat(
                f"{name}_GlowEye",
                palette["eye_color"],
                emission=palette["eye_color"],
                emission_strength=float(palette["eye_strength"]),
            )

        hip_pivot = add_empty(f"{name}_BodyPivot", (0, 0, 0.92), col_chars, parent=root)

        # Torso
        torso = add_box(f"{name}_Torso", (0.76, 0.40, 0.88), (0, 0, 0.44), mat_shirt, col_chars, bevel=0.04, parent=hip_pivot)
        if hair_style == "hoodie":
            add_box(f"{name}_HoodBack", (0.62, 0.24, 0.30), (0, -0.22, 0.76), mat_shirt, col_chars, bevel=0.05, parent=hip_pivot)
            add_box(f"{name}_Pocket", (0.48, 0.06, 0.26), (0, 0.21, 0.22), mat_shirt, col_chars, bevel=0.02, parent=hip_pivot)

        # Neck & Head
        head_pivot = add_empty(f"{name}_HeadPivot", (0, 0, 0.90), col_chars, parent=hip_pivot)
        head = add_cyl(f"{name}_Head", 0.31, 0.56, (0, 0, 0.30), mat_skin, col_chars, parent=head_pivot, verts=24)
        bev_h = head.modifiers.new("Bevel", "BEVEL")
        bev_h.width = 0.06
        bev_h.segments = 3

        # 3D Facial features (front is +Y)
        eye_l = add_box(f"{name}_EyeL", (0.10, 0.05, 0.13), (-0.11, 0.295, 0.33), mat_eye_d if is_monster else mat_eye_w, col_chars, bevel=0.01, parent=head_pivot)
        eye_r = add_box(f"{name}_EyeR", (0.10, 0.05, 0.13), (0.11, 0.295, 0.33), mat_eye_d if is_monster else mat_eye_w, col_chars, bevel=0.01, parent=head_pivot)
        if not is_monster:
            add_box(f"{name}_PupilL", (0.055, 0.05, 0.075), (-0.11, 0.305, 0.33), mat_eye_d, col_chars, bevel=0.008, parent=head_pivot)
            add_box(f"{name}_PupilR", (0.055, 0.05, 0.075), (0.11, 0.305, 0.33), mat_eye_d, col_chars, bevel=0.008, parent=head_pivot)
            brow_l = add_box(f"{name}_BrowL", (0.12, 0.04, 0.03), (-0.11, 0.305, 0.43), mat_hair, col_chars, bevel=0.005, parent=head_pivot)
            brow_r = add_box(f"{name}_BrowR", (0.12, 0.04, 0.03), (0.11, 0.305, 0.43), mat_hair, col_chars, bevel=0.005, parent=head_pivot)
            mouth = add_box(f"{name}_Mouth", (0.15, 0.04, 0.045), (0, 0.305, 0.18), mat_eye_d, col_chars, bevel=0.01, parent=head_pivot)
        else:
            brow_l = brow_r = mouth = None
            add_box(f"{name}_MonsterJaw", (0.28, 0.06, 0.10), (0, 0.295, 0.14), mat_eye_d, col_chars, bevel=0.01, parent=head_pivot)

        # Hair
        if not is_monster:
            add_box(f"{name}_HairTop", (0.64, 0.64, 0.16), (0, -0.02, 0.56), mat_hair, col_chars, bevel=0.04, parent=head_pivot)
            add_box(f"{name}_HairBack", (0.64, 0.18, 0.48), (0, -0.26, 0.34), mat_hair, col_chars, bevel=0.04, parent=head_pivot)
            if hair_style == "hoodie":  # Maya long brown hair
                add_box(f"{name}_HairSideL", (0.14, 0.38, 0.58), (-0.31, -0.08, 0.22), mat_hair, col_chars, bevel=0.03, parent=head_pivot)
                add_box(f"{name}_HairSideR", (0.14, 0.38, 0.58), (0.31, -0.08, 0.22), mat_hair, col_chars, bevel=0.03, parent=head_pivot)
                add_box(f"{name}_HairLongBack", (0.62, 0.16, 0.52), (0, -0.29, 0.02), mat_hair, col_chars, bevel=0.03, parent=head_pivot)
            else:  # Andy short neat hair
                add_box(f"{name}_HairFront", (0.58, 0.18, 0.14), (0, 0.20, 0.53), mat_hair, col_chars, bevel=0.03, parent=head_pivot)

        # Arms pivoted at shoulders
        arm_l_piv = add_empty(f"{name}_ArmLPivot", (-0.54, 0, 0.80), col_chars, parent=hip_pivot)
        arm_r_piv = add_empty(f"{name}_ArmRPivot", (0.54, 0, 0.80), col_chars, parent=hip_pivot)
        arm_len = 1.08 if is_monster else 0.82
        add_box(f"{name}_ArmL", (0.30, 0.30, arm_len), (0, 0, -arm_len * 0.45), mat_shirt, col_chars, bevel=0.03, parent=arm_l_piv)
        add_box(f"{name}_HandL", (0.28, 0.28, 0.18), (0, 0, -arm_len * 0.92), mat_skin, col_chars, bevel=0.03, parent=arm_l_piv)
        add_box(f"{name}_ArmR", (0.30, 0.30, arm_len), (0, 0, -arm_len * 0.45), mat_shirt, col_chars, bevel=0.03, parent=arm_r_piv)
        add_box(f"{name}_HandR", (0.28, 0.28, 0.18), (0, 0, -arm_len * 0.92), mat_skin, col_chars, bevel=0.03, parent=arm_r_piv)

        # Legs pivoted at hips
        leg_l_piv = add_empty(f"{name}_LegLPivot", (-0.19, 0, 0.92), col_chars, parent=root)
        leg_r_piv = add_empty(f"{name}_LegRPivot", (0.19, 0, 0.92), col_chars, parent=root)
        add_box(f"{name}_LegL", (0.34, 0.36, 0.80), (0, 0, -0.40), mat_pants, col_chars, bevel=0.03, parent=leg_l_piv)
        add_box(f"{name}_ShoeL", (0.35, 0.44, 0.16), (0, 0.04, -0.84), mat_shoe, col_chars, bevel=0.03, parent=leg_l_piv)
        add_box(f"{name}_LegR", (0.34, 0.36, 0.80), (0, 0, -0.40), mat_pants, col_chars, bevel=0.03, parent=leg_r_piv)
        add_box(f"{name}_ShoeR", (0.35, 0.44, 0.16), (0, 0.04, -0.84), mat_shoe, col_chars, bevel=0.03, parent=leg_r_piv)

        return {
            "root": root,
            "body": hip_pivot,
            "head": head_pivot,
            "arm_l": arm_l_piv,
            "arm_r": arm_r_piv,
            "leg_l": leg_l_piv,
            "leg_r": leg_r_piv,
            "eye_l": eye_l,
            "eye_r": eye_r,
            "brow_l": brow_l,
            "brow_r": brow_r,
            "mouth": mouth,
            "torso": torso,
        }

    maya = build_roblox_character("Maya", cfg["characters"]["maya"], hair_style="hoodie", scale=0.98)
    andy = build_roblox_character("Andy", cfg["characters"]["andy"], hair_style="short", scale=0.96)
    monster = build_roblox_character("Monster", cfg["characters"]["monster"], hair_style="none", is_monster=True, scale=float(cfg["characters"]["monster"]["scale"]))

    # Monster aura light for dramatic silhouette
    bpy.ops.object.light_add(type="POINT", location=(0, -0.8, 2.2))
    monster_light = bpy.context.active_object
    monster_light.name = "MonsterAura"
    monster_light.data.color = (1.0, 0.10, 0.08)
    monster_light.data.energy = 60.0
    link_obj(monster_light, col_chars)
    monster_light.parent = monster["root"]

    # -----------------------------------------------------------------------
    # 3D PROPS (HEADPHONES, DECOY HEADPHONES, RUBBER DUCK, MEGAPHONE)
    # -----------------------------------------------------------------------
    def build_headphones(name, body_color, led_color, parent=None):
        hp_root = add_empty(name, (0, 0, 0.35), col_props, parent=parent)
        m_hp = make_mat(f"{name}_Mat", body_color, roughness=0.35, metallic=0.25)
        m_pad = make_mat(f"{name}_Pad", (0.03, 0.03, 0.035, 1.0), roughness=0.8)
        m_led = make_mat(f"{name}_LED", led_color, emission=led_color, emission_strength=8.0)
        add_box(f"{name}_BandTop", (0.72, 0.12, 0.08), (0, 0, 0.30), m_hp, col_props, bevel=0.02, parent=hp_root)
        add_box(f"{name}_BandL", (0.08, 0.12, 0.30), (-0.34, 0, 0.14), m_hp, col_props, bevel=0.02, parent=hp_root)
        add_box(f"{name}_BandR", (0.08, 0.12, 0.30), (0.34, 0, 0.14), m_hp, col_props, bevel=0.02, parent=hp_root)
        add_cyl(f"{name}_CupL", 0.16, 0.11, (-0.36, 0, -0.02), m_hp, col_props, rot=(0, math.radians(90), 0), parent=hp_root)
        add_cyl(f"{name}_PadL", 0.14, 0.06, (-0.31, 0, -0.02), m_pad, col_props, rot=(0, math.radians(90), 0), parent=hp_root)
        add_cyl(f"{name}_CupR", 0.16, 0.11, (0.36, 0, -0.02), m_hp, col_props, rot=(0, math.radians(90), 0), parent=hp_root)
        add_cyl(f"{name}_PadR", 0.14, 0.06, (0.31, 0, -0.02), m_pad, col_props, rot=(0, math.radians(90), 0), parent=hp_root)
        led = add_box(f"{name}_LED", (0.03, 0.05, 0.05), (0.42, 0.05, -0.02), m_led, col_props, bevel=0.005, parent=hp_root)
        return hp_root, m_led

    hp_real, _ = build_headphones("Headphones_Real", [0.14, 0.14, 0.16, 1.0], [0.15, 0.75, 1.0, 1.0], parent=andy["head"])
    hp_decoy, decoy_led_mat = build_headphones("Headphones_Decoy", [0.12, 0.12, 0.15, 1.0], [0.25, 1.0, 0.45, 1.0])

    # Funny blocky yellow rubber duck prop (Scene 4 Trick 2)
    m_duck = make_mat("Mat_Duck", (1.0, 0.82, 0.05, 1.0), roughness=0.3)
    m_beak = make_mat("Mat_Beak", (1.0, 0.35, 0.02, 1.0), roughness=0.4)
    duck_root = add_empty("Prop_Duck", (-5.0, 18.0, -5.0), col_props)
    add_box("Duck_Body", (0.42, 0.55, 0.32), (0, 0, 0), m_duck, col_props, bevel=0.06, parent=duck_root)
    add_box("Duck_Head", (0.28, 0.28, 0.28), (0, 0.16, 0.26), m_duck, col_props, bevel=0.05, parent=duck_root)
    add_box("Duck_Beak", (0.18, 0.18, 0.08), (0, 0.35, 0.22), m_beak, col_props, bevel=0.02, parent=duck_root)

    # Megaphone prop + shockwave ring (Scene 4 Trick 3)
    m_mega = make_mat("Mat_Mega", (0.88, 0.12, 0.12, 1.0), roughness=0.35)
    m_ring = make_mat("Mat_Ring", (1.0, 0.9, 0.2, 1.0), emission=(1.0, 0.85, 0.1, 1.0), emission_strength=10.0)
    mega_root = add_empty("Prop_Megaphone", (-5.0, 22.0, -5.0), col_props)
    add_cyl("Mega_Cone", 0.22, 0.55, (0, 0, 0), m_mega, col_props, rot=(math.radians(90), 0, 0), parent=mega_root)
    bpy.ops.mesh.primitive_torus_add(major_radius=0.35, minor_radius=0.035, location=(0, 0.45, 0), rotation=(math.radians(90), 0, 0))
    ring_obj = bpy.context.active_object
    ring_obj.name = "Mega_Wave"
    ring_obj.data.materials.append(m_ring)
    link_obj(ring_obj, col_props)
    ring_obj.parent = mega_root

    # -----------------------------------------------------------------------
    # ANIMATION HELPERS
    # -----------------------------------------------------------------------
    def kf(obj, attr, val, frame, interp="BEZIER"):
        setattr(obj, attr, val)
        obj.keyframe_insert(data_path=attr, frame=int(frame))
        if obj.animation_data and obj.animation_data.action:
            for fc in obj.animation_data.action.fcurves:
                if fc.data_path == attr:
                    for kp in fc.keyframe_points:
                        if int(round(kp.co.x)) == int(frame):
                            kp.interpolation = interp

    def animate_walk(char, f_start, f_end, speed=1.0, amp=0.55):
        step_frames = max(6, int(12 / speed))
        toggle = 1
        for f in range(f_start, f_end + 1, step_frames):
            swing = toggle * amp
            kf(char["leg_l"], "rotation_euler", (swing, 0, 0), f)
            kf(char["leg_r"], "rotation_euler", (-swing, 0, 0), f)
            kf(char["arm_l"], "rotation_euler", (-swing * 0.8, 0, 0), f)
            kf(char["arm_r"], "rotation_euler", (swing * 0.8, 0, 0), f)
            kf(char["body"], "location", (0, 0, 0.92 + 0.04 * abs(toggle)), f)
            toggle *= -1
        kf(char["leg_l"], "rotation_euler", (0, 0, 0), f_end + 2)
        kf(char["leg_r"], "rotation_euler", (0, 0, 0), f_end + 2)
        kf(char["arm_l"], "rotation_euler", (0, 0, 0), f_end + 2)
        kf(char["arm_r"], "rotation_euler", (0, 0, 0), f_end + 2)
        kf(char["body"], "location", (0, 0, 0.92), f_end + 2)

    # -----------------------------------------------------------------------
    # CAMERA + TRACKING TARGET
    # -----------------------------------------------------------------------
    bpy.ops.object.camera_add(location=(0.0, -7.5, 2.5))
    cam = bpy.context.active_object
    cam.name = "MainCamera"
    cam.data.lens = 30.0
    cam.data.clip_end = 250.0
    link_obj(cam, scene.collection)
    scene.camera = cam

    cam_target = add_empty("CamTarget", (0.0, 12.0, 2.0), scene.collection)
    track = cam.constraints.new(type="TRACK_TO")
    track.target = cam_target
    track.track_axis = "TRACK_NEGATIVE_Z"
    track.up_axis = "UP_Y"

    if cfg["video"]["use_dof"]:
        cam.data.dof.use_dof = True
        cam.data.dof.focus_object = cam_target
        cam.data.dof.aperture_fstop = float(cfg["video"]["dof_fstop"])

    # -----------------------------------------------------------------------
    # SCENE-BY-SCENE CHOREOGRAPHY (Frames 1..1710)
    # -----------------------------------------------------------------------
    # SCENE 1 (0-7s, frames 1-210): Empty town at night, monster silhouette emerges
    kf(maya["root"], "location", (-6.2, 4.0, 0.0), 1)
    kf(maya["root"], "rotation_euler", (0, 0, math.radians(-110)), 1)
    kf(andy["root"], "location", (-4.8, -1.5, 0.0), 1)
    kf(andy["root"], "rotation_euler", (0, 0, 0), 1)
    kf(hp_decoy, "location", (-6.2, 3.6, 1.3), 1)
    kf(hp_decoy, "scale", (0.001, 0.001, 0.001), 1)

    kf(monster["root"], "location", (1.2, 30.0, 0.0), 1)
    kf(monster["root"], "rotation_euler", (0, 0, math.radians(180)), 1)
    kf(monster["root"], "location", (0.2, 23.0, 0.0), 200)
    kf(monster["head"], "rotation_euler", (math.radians(8), 0, math.radians(-10)), 90)
    kf(monster["head"], "rotation_euler", (math.radians(4), 0, math.radians(12)), 200)

    kf(cam, "location", (0.0, -7.0, 2.6), 1)
    kf(cam, "location", (0.3, 4.5, 2.0), 210)
    kf(cam_target, "location", (0.2, 22.0, 2.2), 1)
    kf(cam_target, "location", (0.2, 22.0, 2.3), 210)
    cam.data.lens = 28.0
    cam.data.keyframe_insert(data_path="lens", frame=1)

    # SCENE 2 (7-15s, frames 211-450): Introduce Maya & Andy
    kf(monster["root"], "location", (16.0, 35.0, -8.0), 211, "CONSTANT")  # hide offstage
    kf(maya["root"], "location", (-5.8, 6.2, 0.0), 211, "CONSTANT")
    kf(maya["root"], "rotation_euler", (0, 0, math.radians(-150)), 211, "CONSTANT")
    kf(andy["root"], "location", (-4.6, 0.5, 0.0), 211, "CONSTANT")
    kf(andy["root"], "location", (-4.6, 8.5, 0.0), 450)
    animate_walk(andy, 212, 448, speed=0.85, amp=0.45)

    # Cut to Maya looking curious -> over-the-shoulder toward Andy
    kf(cam, "location", (-4.1, 4.3, 1.85), 211, "CONSTANT")
    kf(cam_target, "location", (-5.6, 6.2, 1.55), 211, "CONSTANT")
    cam.data.lens = 45.0
    cam.data.keyframe_insert(data_path="lens", frame=211)
    kf(maya["brow_l"], "rotation_euler", (0, math.radians(12), 0), 220)
    kf(maya["brow_r"], "rotation_euler", (0, math.radians(-8), 0), 220)
    kf(maya["head"], "rotation_euler", (0, 0, math.radians(-22)), 250)
    kf(maya["head"], "rotation_euler", (0, 0, math.radians(-35)), 310)

    kf(cam, "location", (-6.2, 7.6, 1.8), 320, "CONSTANT")
    kf(cam_target, "location", (-4.6, 4.8, 1.4), 320, "CONSTANT")
    kf(cam, "location", (-5.6, 9.8, 1.7), 450)
    kf(cam_target, "location", (-4.6, 8.2, 1.45), 450)

    # SCENE 3 (15-25s, frames 451-750): Andy walks peacefully, Maya swaps headphones
    kf(andy["root"], "location", (-4.6, 8.5, 0.0), 451)
    kf(andy["root"], "location", (-4.6, 14.8, 0.0), 750)
    animate_walk(andy, 452, 748, speed=0.85, amp=0.45)

    # Maya sneaks right behind Andy
    kf(maya["root"], "location", (-5.5, 6.6, 0.0), 451)
    kf(maya["root"], "rotation_euler", (0, 0, 0), 470)
    kf(maya["root"], "location", (-4.6, 11.1, 0.0), 590)
    kf(maya["root"], "location", (-4.6, 13.8, 0.0), 690)
    kf(maya["root"], "location", (-5.5, 13.6, 0.0), 748)
    animate_walk(maya, 470, 585, speed=1.2, amp=0.45)

    # Maya's arms reach up and swap headphones around frame 600-660
    kf(maya["arm_l"], "rotation_euler", (0, 0, 0), 580)
    kf(maya["arm_r"], "rotation_euler", (0, 0, 0), 580)
    kf(maya["arm_l"], "rotation_euler", (math.radians(-85), 0, math.radians(10)), 615)
    kf(maya["arm_r"], "rotation_euler", (math.radians(-85), 0, math.radians(-10)), 615)
    kf(maya["arm_l"], "rotation_euler", (0, 0, 0), 665)
    kf(maya["arm_r"], "rotation_euler", (0, 0, 0), 665)

    # Swap visibility/scale of real vs decoy headphones smoothly at frame 625
    kf(hp_real, "scale", (1.0, 1.0, 1.0), 620, "CONSTANT")
    kf(hp_real, "scale", (0.001, 0.001, 0.001), 625, "CONSTANT")
    kf(hp_decoy, "scale", (0.001, 0.001, 0.001), 620, "CONSTANT")
    kf(hp_decoy, "scale", (1.0, 1.0, 1.0), 625, "CONSTANT")
    for f in range(625, 1201, 4):
        # Track Andy's head position closely (Andy walks along x=-4.6, head z~1.82+0.35=2.17)
        t_frac = (f - 451) / (750 - 451) if f <= 750 else 1.0
        ay = 8.5 + t_frac * (14.8 - 8.5)
        if 750 < f <= 1110:
            ay = 14.8 + ((f - 750) / (1110 - 750)) * (22.5 - 14.8)
        elif f > 1110:
            ay = 22.5
        kf(hp_decoy, "location", (-4.6, ay, 2.12), f)

    # Camera close-up on swap
    kf(cam, "location", (-3.1, 10.6, 2.0), 451, "CONSTANT")
    kf(cam_target, "location", (-4.6, 9.6, 1.5), 451, "CONSTANT")
    kf(cam, "location", (-3.4, 13.8, 2.15), 620)
    kf(cam_target, "location", (-4.6, 12.2, 1.9), 620)
    cam.data.lens = 50.0
    cam.data.keyframe_insert(data_path="lens", frame=600)

    # SCENE 4 (25-40s, frames 751-1200): 4 Tricks Montage + Switch OFF
    kf(andy["root"], "location", (-4.6, 14.8, 0.0), 751)
    kf(andy["root"], "location", (-4.6, 22.5, 0.0), 1110)
    kf(andy["root"], "location", (-4.6, 22.5, 0.0), 1200)
    animate_walk(andy, 752, 1108, speed=0.85, amp=0.45)

    # Trick 1 (751-855): Jump out from behind brick wall at y=16.2
    kf(maya["root"], "location", (-5.7, 15.7, 0.0), 751, "CONSTANT")
    kf(maya["root"], "rotation_euler", (0, 0, math.radians(-90)), 751, "CONSTANT")
    kf(maya["root"], "location", (-4.1, 16.9, 0.0), 788)
    kf(maya["arm_l"], "rotation_euler", (math.radians(-125), 0, math.radians(-20)), 788)
    kf(maya["arm_r"], "rotation_euler", (math.radians(-125), 0, math.radians(20)), 788)
    kf(cam, "location", (-3.2, 18.8, 1.65), 751, "CONSTANT")
    kf(cam_target, "location", (-4.6, 16.4, 1.55), 751, "CONSTANT")
    cam.data.lens = 35.0
    cam.data.keyframe_insert(data_path="lens", frame=751)

    # Trick 2 (856-960): Funny rubber duck thrust in front of Andy
    kf(maya["root"], "location", (-3.7, 18.6, 0.0), 856, "CONSTANT")
    kf(maya["root"], "rotation_euler", (0, 0, math.radians(105)), 856, "CONSTANT")
    kf(maya["arm_l"], "rotation_euler", (math.radians(-80), 0, 0), 875)
    kf(duck_root, "location", (-4.55, 18.2, 1.75), 860, "CONSTANT")
    kf(duck_root, "rotation_euler", (0, 0, math.radians(180)), 860)
    kf(duck_root, "rotation_euler", (math.radians(15), 0, math.radians(160)), 910)
    kf(duck_root, "location", (-4.55, 18.2, -5.0), 960, "CONSTANT")
    kf(cam, "location", (-5.8, 19.8, 1.75), 856, "CONSTANT")
    kf(cam_target, "location", (-4.5, 18.0, 1.65), 856, "CONSTANT")
    cam.data.lens = 55.0
    cam.data.keyframe_insert(data_path="lens", frame=856)

    # Trick 3 (961-1080): Megaphone blast right next to Andy's ear
    kf(maya["root"], "location", (-3.7, 20.5, 0.0), 961, "CONSTANT")
    kf(maya["root"], "rotation_euler", (0, 0, math.radians(95)), 961, "CONSTANT")
    kf(mega_root, "location", (-4.0, 20.5, 1.72), 962, "CONSTANT")
    kf(mega_root, "rotation_euler", (0, 0, math.radians(90)), 962)
    kf(ring_obj, "scale", (0.4, 0.4, 0.4), 980)
    kf(ring_obj, "scale", (2.8, 2.8, 2.8), 1030)
    kf(mega_root, "location", (-4.0, 20.5, -5.0), 1080, "CONSTANT")
    kf(cam, "location", (-3.2, 22.2, 1.8), 961, "CONSTANT")
    kf(cam_target, "location", (-4.3, 20.3, 1.65), 961, "CONSTANT")
    cam.data.lens = 42.0
    cam.data.keyframe_insert(data_path="lens", frame=961)

    # Trick 4 (1081-1200): Maya frowns & switches off Andy's noise cancellation!
    kf(maya["root"], "location", (-4.6, 21.5, 0.0), 1081, "CONSTANT")
    kf(maya["root"], "rotation_euler", (0, 0, 0), 1081, "CONSTANT")
    kf(maya["brow_l"], "rotation_euler", (0, math.radians(-18), 0), 1090)
    kf(maya["brow_r"], "rotation_euler", (0, math.radians(18), 0), 1090)
    kf(maya["arm_r"], "rotation_euler", (0, 0, 0), 1100)
    kf(maya["arm_r"], "rotation_euler", (math.radians(-92), 0, math.radians(12)), 1145)
    kf(maya["arm_r"], "rotation_euler", (0, 0, 0), 1185)
    kf(cam, "location", (-3.4, 22.8, 2.05), 1081, "CONSTANT")
    kf(cam_target, "location", (-4.6, 22.1, 1.85), 1081, "CONSTANT")
    cam.data.lens = 68.0
    cam.data.keyframe_insert(data_path="lens", frame=1081)

    # Switch decoy headphone LED from green to red at frame 1148
    if decoy_led_mat and decoy_led_mat.node_tree:
        bsdf_led = decoy_led_mat.node_tree.nodes.get("Principled BSDF")
        if bsdf_led and "Emission Color" in bsdf_led.inputs:
            bsdf_led.inputs["Emission Color"].default_value = (0.25, 1.0, 0.45, 1.0)
            bsdf_led.inputs["Emission Color"].keyframe_insert(data_path="default_value", frame=1145)
            bsdf_led.inputs["Emission Color"].default_value = (1.0, 0.08, 0.05, 1.0)
            bsdf_led.inputs["Emission Color"].keyframe_insert(data_path="default_value", frame=1150)

    # SCENE 5 (40-50s, frames 1201-1500): Andy hears noise, turns around, SCREAMS; lights flicker, windows rattle, monster emerges
    kf(andy["root"], "location", (-4.6, 22.5, 0.0), 1201)
    kf(maya["root"], "location", (-5.6, 21.8, 0.0), 1201)
    kf(maya["root"], "rotation_euler", (0, 0, math.radians(-30)), 1201)

    # Andy freezes, slowly turns head & body toward -Y (looking back down street)
    kf(andy["head"], "rotation_euler", (0, 0, 0), 1210)
    kf(andy["head"], "rotation_euler", (0, 0, math.radians(150)), 1270)
    kf(andy["root"], "rotation_euler", (0, 0, 0), 1245)
    kf(andy["root"], "rotation_euler", (0, 0, math.radians(175)), 1295)

    # Terrified expression: wide eyes, raised brows, mouth opens into huge O-scream!
    kf(andy["mouth"], "scale", (1.0, 1.0, 1.0), 1290)
    kf(andy["mouth"], "scale", (1.45, 1.2, 3.8), 1315)
    kf(andy["eye_l"], "scale", (1.0, 1.0, 1.0), 1290)
    kf(andy["eye_l"], "scale", (1.35, 1.0, 1.45), 1315)
    kf(andy["eye_r"], "scale", (1.0, 1.0, 1.0), 1290)
    kf(andy["eye_r"], "scale", (1.35, 1.0, 1.45), 1315)
    kf(andy["arm_l"], "rotation_euler", (math.radians(-65), 0, math.radians(-35)), 1320)
    kf(andy["arm_r"], "rotation_euler", (math.radians(-65), 0, math.radians(35)), 1320)

    # Close-up on Andy's scream -> whip cut to Monster emerging from darkness
    kf(cam, "location", (-4.4, 21.1, 1.90), 1201, "CONSTANT")
    kf(cam_target, "location", (-4.6, 22.5, 1.85), 1201, "CONSTANT")
    cam.data.lens = 58.0
    cam.data.keyframe_insert(data_path="lens", frame=1201)
    kf(cam, "location", (-4.55, 21.45, 1.85), 1340)
    cam.data.lens = 72.0
    cam.data.keyframe_insert(data_path="lens", frame=1340)

    # Monster emerges behind Andy (from street darkness at y=11 -> y=16.5)
    kf(monster["root"], "location", (-3.8, 9.0, 0.0), 1345, "CONSTANT")
    kf(monster["root"], "rotation_euler", (0, 0, 0), 1345, "CONSTANT")
    kf(monster["root"], "location", (-4.3, 17.5, 0.0), 1495)
    animate_walk(monster, 1346, 1495, speed=0.75, amp=0.38)
    kf(monster["arm_l"], "rotation_euler", (math.radians(-50), 0, math.radians(-12)), 1380)
    kf(monster["arm_r"], "rotation_euler", (math.radians(-50), 0, math.radians(12)), 1380)

    kf(cam, "location", (-3.0, 24.4, 1.6), 1355, "CONSTANT")
    kf(cam_target, "location", (-4.3, 16.5, 2.3), 1355, "CONSTANT")
    cam.data.lens = 32.0
    cam.data.keyframe_insert(data_path="lens", frame=1355)

    # Flickering streetlights & rattling windows (frames 1300-1520)
    flick_rng = random.Random(77)
    for sp in street_lights:
        kf(sp.data, "energy", 380.0, 1295)
        for f in range(1300, 1525, 4):
            e = flick_rng.choice([20.0, 60.0, 420.0, 15.0, 390.0])
            kf(sp.data, "energy", e, f, "CONSTANT")
        kf(sp.data, "energy", 380.0, 1535)

    for idx_w, (wf, wp, base_loc) in enumerate(animated_windows[:16]):
        kf(wf, "location", base_loc, 1300)
        kf(wp, "location", base_loc, 1300)
        for f in range(1306, 1490, 5):
            jit = (0.04 if (f + idx_w) % 2 == 0 else -0.04)
            loc_j = (base_loc[0], base_loc[1] + jit, base_loc[2] + jit * 0.5)
            kf(wf, "location", loc_j, f, "CONSTANT")
            kf(wp, "location", loc_j, f, "CONSTANT")
        kf(wf, "location", base_loc, 1500)
        kf(wp, "location", base_loc, 1500)

    # SCENE 6 (50-57s, frames 1501-1710): Maya runs away, silhouette of Monster approaching Andy, cut to black
    # 50-53s (1501-1590): Maya sprints down street
    kf(maya["root"], "location", (-5.6, 22.0, 0.0), 1501)
    kf(maya["root"], "rotation_euler", (0, 0, 0), 1501)
    kf(maya["root"], "location", (-5.0, 34.5, 0.0), 1590)
    animate_walk(maya, 1502, 1588, speed=2.2, amp=0.85)
    kf(cam, "location", (-3.2, 27.5, 1.75), 1501, "CONSTANT")
    kf(cam_target, "location", (-5.2, 24.5, 1.4), 1501, "CONSTANT")
    kf(cam, "location", (-3.6, 36.0, 1.85), 1588)
    kf(cam_target, "location", (-5.0, 32.0, 1.5), 1588)

    # 53-54.3s (1591-1630): Dramatic silhouette of Monster reaching toward frozen Andy
    kf(andy["root"], "location", (-4.6, 22.5, 0.0), 1591, "CONSTANT")
    kf(monster["root"], "location", (-4.4, 19.3, 0.0), 1591, "CONSTANT")
    kf(monster["root"], "location", (-4.5, 21.1, 0.0), 1630)
    kf(monster["arm_l"], "rotation_euler", (math.radians(-95), 0, 0), 1625)
    kf(monster["arm_r"], "rotation_euler", (math.radians(-95), 0, 0), 1625)
    kf(cam, "location", (-4.5, 25.8, 1.25), 1591, "CONSTANT")
    kf(cam_target, "location", (-4.5, 21.0, 2.0), 1591, "CONSTANT")
    cam.data.lens = 38.0
    cam.data.keyframe_insert(data_path="lens", frame=1591)

    # -----------------------------------------------------------------------
    # VIDEO SEQUENCE EDITOR: AUDIO LAYERS + CUT TO BLACK + END TEXT
    # -----------------------------------------------------------------------
    if not scene.sequence_editor:
        scene.sequence_editor_create()
    seq = scene.sequence_editor

    # Place 3D Scene strip on Channel 1 (stops at frame 1630 for sharp cut to black!)
    scene_strip = seq.sequences.new_scene("Main3DScene", scene, channel=1, frame_start=1)
    scene_strip.frame_final_end = 1630

    # Black background color strip for 1631..1710
    black_strip = seq.sequences.new_effect("CutToBlack", "COLOR", channel=1, frame_start=1631, frame_end=total_frames)
    black_strip.color = (0.0, 0.0, 0.0)

    # Final on-screen text ("WOULD YOU SCREAM?") + stylized eyes graphic in VSE
    end_txt = seq.sequences.new_effect("EndText", "TEXT", channel=2, frame_start=1633, frame_end=total_frames)
    end_txt.text = cfg["scenes"]["scene_6"]["end_card_text"]
    end_txt.font_size = 76
    end_txt.location = (0.5, 0.54)
    end_txt.color = (1.0, 1.0, 1.0, 1.0)
    end_txt.use_shadow = True
    end_txt.blend_type = "ALPHA_OVER"

    eyes_txt = seq.sequences.new_effect("EndEyes", "TEXT", channel=3, frame_start=1638, frame_end=total_frames)
    eyes_txt.text = "(  O   O  )"
    eyes_txt.font_size = 90
    eyes_txt.location = (0.5, 0.42)
    eyes_txt.color = (1.0, 0.15, 0.12, 1.0)
    eyes_txt.blend_type = "ALPHA_OVER"

    # Audio channels
    audio_dir = BASE_DIR / "audio"
    music_strip = seq.sequences.new_sound("BG_Music", str(audio_dir / "music_suspense.wav"), channel=4, frame_start=1)
    music_strip.volume = float(cfg["audio"]["music_volume"])

    amb_strip = seq.sequences.new_sound("Night_Ambience", str(audio_dir / "ambience_night.wav"), channel=5, frame_start=1)
    amb_strip.volume = float(cfg["audio"]["ambience_volume"])

    # Narration strips synced to scene timestamps
    narration_starts = {1: 8, 2: 218, 3: 458, 4: 758, 5: 1206, 6: 1506}
    for idx_n, f_start in narration_starts.items():
        n_strip = seq.sequences.new_sound(f"Narr_{idx_n}", str(narration_paths[idx_n]), channel=6, frame_start=f_start)
        n_strip.volume = float(cfg["audio"]["narration_volume"])
        # Duck background music cleanly while narrator speaks
        dur_f = max(30, int(n_strip.frame_final_duration))
        music_strip.volume = float(cfg["audio"]["music_volume"])
        music_strip.keyframe_insert(data_path="volume", frame=max(1, f_start - 5))
        music_strip.volume = float(cfg["audio"]["music_duck_volume"])
        music_strip.keyframe_insert(data_path="volume", frame=f_start + 3)
        music_strip.keyframe_insert(data_path="volume", frame=f_start + dur_f - 4)
        music_strip.volume = float(cfg["audio"]["music_volume"])
        music_strip.keyframe_insert(data_path="volume", frame=f_start + dur_f + 6)

    # Synchronized SFX strips
    sfx_events = [
        ("sfx_footstep.wav", 7, 230, 0.45),
        ("sfx_footstep.wav", 7, 260, 0.45),
        ("sfx_footstep.wav", 7, 480, 0.50),
        ("sfx_swap.wav", 8, 610, 0.90),
        ("sfx_honk.wav", 7, 865, 0.85),
        ("sfx_blast.wav", 8, 975, 0.90),
        ("sfx_switch.wav", 9, 1146, 0.95),
        ("sfx_monster_roar.wav", 7, 1212, 0.85),
        ("sfx_scream.wav", 8, 1308, 0.95),
        ("sfx_impact.wav", 9, 1352, 0.95),
        ("sfx_footstep.wav", 7, 1515, 0.65),
        ("sfx_footstep.wav", 7, 1530, 0.65),
        ("sfx_footstep.wav", 7, 1545, 0.65),
        ("sfx_impact.wav", 9, 1628, 1.00),
    ]
    for idx_s, (fname, ch, f_st, vol) in enumerate(sfx_events):
        p = audio_dir / fname
        if p.exists():
            st = seq.sequences.new_sound(f"SFX_{idx_s}_{fname}", str(p), channel=ch, frame_start=f_st)
            st.volume = vol * float(cfg["audio"]["sfx_volume"])

    # Enable VSE compositing
    scene.render.use_sequencer = True

    def configure_mp4_output(out_path: Path):
        if hasattr(scene.render.image_settings, "media_type"):
            scene.render.image_settings.media_type = "VIDEO"
        scene.render.image_settings.file_format = "FFMPEG"
        scene.render.ffmpeg.format = "MPEG4"
        scene.render.ffmpeg.codec = "H264"
        scene.render.ffmpeg.constant_rate_factor = "HIGH"
        scene.render.ffmpeg.ffmpeg_preset = "GOOD"
        scene.render.ffmpeg.audio_codec = "AAC"
        scene.render.ffmpeg.audio_bitrate = 192
        scene.render.filepath = str(out_path)

    # Save .blend project for inspection/re-use
    bpy.ops.wm.save_as_mainfile(filepath=str(BASE_DIR / "assets" / "roblox_short_scene.blend"))

    # Render 10-second preview
    if mode in ("both", "preview"):
        print(f"[Render] Rendering 10-second preview ({preview_frames} frames)...")
        if hasattr(scene.eevee, "taa_render_samples"):
            scene.eevee.taa_render_samples = int(cfg["video"]["preview_samples"])
        scene.frame_start = 1
        scene.frame_end = preview_frames
        prev_out = BASE_DIR / "output" / cfg["project"]["preview_video"]
        configure_mp4_output(prev_out)
        bpy.ops.render.render(animation=True)
        shutil.copy2(prev_out, BASE_DIR / cfg["project"]["preview_video"])
        print(f"[Done] Saved preview: {prev_out}")

    # Render full 57-second Short
    if mode in ("both", "full"):
        print(f"[Render] Rendering full Short ({total_frames} frames)...")
        if hasattr(scene.eevee, "taa_render_samples"):
            scene.eevee.taa_render_samples = int(cfg["video"]["samples"])
        scene.frame_start = 1
        scene.frame_end = total_frames
        final_out = BASE_DIR / "output" / cfg["project"]["final_video"]
        configure_mp4_output(final_out)
        bpy.ops.render.render(animation=True)
        shutil.copy2(final_out, BASE_DIR / cfg["project"]["final_video"])
        print(f"[Done] Saved final video: {final_out}")


def parse_args(argv):
    if "--" in argv:
        argv = argv[argv.index("--") + 1 :]
    else:
        argv = argv[1:]
    parser = argparse.ArgumentParser(description="Roblox-Style 3D YouTube Short Generator")
    parser.add_argument("--preview-only", action="store_true", help="Render only preview_10_seconds.mp4")
    parser.add_argument("--full-only", action="store_true", help="Render only roblox_short_final.mp4")
    return parser.parse_args(argv)


def main():
    ensure_dirs()
    cfg = load_config()
    args = parse_args(sys.argv)
    mode = "preview" if args.preview_only else ("full" if args.full_only else "both")

    try:
        import bpy  # type: ignore  # noqa: F401
        in_blender = True
    except ImportError:
        in_blender = False

    if in_blender:
        run_blender_pipeline(cfg, mode=mode)
    else:
        # Running from standard Python: generate TTS + procedural SFX first, then launch Blender headless
        generate_narration_files(cfg)
        synthesize_audio_assets(cfg)
        blender_bin = find_blender()
        if not blender_bin:
            raise RuntimeError(
                "Blender 4.x executable not found. Install Blender 4.x and add it to PATH or set BLENDER_PATH."
            )
        cmd = [blender_bin, "-b", "-P", str(Path(__file__).resolve()), "--"]
        if mode == "preview":
            cmd.append("--preview-only")
        elif mode == "full":
            cmd.append("--full-only")
        print("[Launch]", " ".join(cmd))
        subprocess.run(cmd, check=True)


if __name__ == "__main__":
    main()