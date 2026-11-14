#!/usr/bin/env python3
"""
Oddyson render: voice acting + sound design mixer.

    python render.py timeline.json -o out.mp4

Reads a timeline, builds each character voice (your recorded files, or
optional neural TTS if a file is missing), layers SFX / ambience / music,
ducks the music under dialogue, honors "dramatic silence" windows, and
muxes the result onto your video. Never burns subtitles or captions.

Needs: ffmpeg + ffprobe on PATH.  Optional: pip install edge-tts
"""
import argparse
import asyncio
import json
import shutil
import subprocess
import sys
from pathlib import Path

SR = 44100

# ---- character voice looks (pitch factor, gain dB, extra ffmpeg filters) ----
CHARACTERS = {
    "oddyson": {"pitch": 1.04, "gain": 1.0,
                "fx": "equalizer=f=3200:t=q:w=1:g=3,acompressor=threshold=-18dB:ratio=3",
                "tts_voice": "en-US-GuyNeural"},
    "quiet_boy": {"pitch": 1.08, "gain": -2.0,
                  "fx": "lowpass=f=9000,acompressor=threshold=-24dB:ratio=2",
                  "tts_voice": "en-US-AndrewNeural"},
    "narrator": {"pitch": 0.95, "gain": 1.0,
                 "fx": "equalizer=f=120:t=q:w=1:g=3,acompressor=threshold=-20dB:ratio=3.5",
                 "tts_voice": "en-US-ChristopherNeural"},
}

# ---- emotion tweaks layered on top of the character (pitch x, gain dB, filters) ----
EMOTIONS = {
    "neutral": {"pitch": 1.00, "gain": 0.0, "fx": ""},
    "excited": {"pitch": 1.06, "gain": 2.5, "fx": "equalizer=f=4500:t=q:w=1:g=2"},
    "shout": {"pitch": 1.09, "gain": 4.0, "fx": "acompressor=threshold=-14dB:ratio=5"},
    "whisper": {"pitch": 0.98, "gain": -5.0, "fx": "highpass=f=250,equalizer=f=6000:t=q:w=1:g=3"},
    "suspense": {"pitch": 0.94, "gain": -1.0, "fx": "lowpass=f=7000"},
    "funny": {"pitch": 1.05, "gain": 1.0, "fx": ""},
    "sad": {"pitch": 0.96, "gain": -2.0, "fx": "lowpass=f=6500"},
}


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"ffmpeg failed:\n{' '.join(cmd)}\n\n{r.stderr[-2000:]}")
    return r.stdout


def probe_duration(path):
    out = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
               "-of", "default=nw=1:nk=1", str(path)])
    return float(out.strip())


def pitch_filter(factor):
    """Shift pitch without changing speed (asetrate + atempo)."""
    if abs(factor - 1.0) < 0.001:
        return ""
    return f"asetrate={SR * factor:.0f},aresample={SR},atempo={1 / factor:.5f}"


def tts(text, voice, out_path):
    try:
        import edge_tts
    except ImportError:
        return False
    try:
        asyncio.run(edge_tts.Communicate(text, voice).save(str(out_path)))
        return True
    except Exception as e:  # offline, etc.
        print(f"  TTS failed ({e})")
        return False


def resolve_audio(item, base, cache):
    """Return a Path to the audio file for a clip, or None to skip it."""
    f = item.get("file")
    if f and (base / f).exists():
        return base / f
    text = item.get("text")
    if text:
        char = CHARACTERS.get(item.get("character", ""), {})
        voice = item.get("tts_voice") or char.get("tts_voice", "en-US-GuyNeural")
        out = cache / f"tts_{abs(hash((text, voice)))}.mp3"
        if out.exists() or tts(text, voice, out):
            return out
    print(f"  skipped (no file, no TTS): {f or text}")
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("timeline")
    ap.add_argument("-o", "--output", default="out.mp4")
    args = ap.parse_args()

    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        sys.exit("Install ffmpeg first: https://ffmpeg.org/download.html")

    tl_path = Path(args.timeline).resolve()
    tl = json.loads(tl_path.read_text())
    base = tl_path.parent
    cache = base / ".cache"
    cache.mkdir(exist_ok=True)

    video = base / tl["video"] if tl.get("video") else None
    if video and not video.exists():
        sys.exit(f"Video not found: {video}")
    dur = probe_duration(video) if video else float(tl.get("duration", 30))

    inputs = []      # ffmpeg -i args
    fc = []          # filter_complex lines
    buses = {"voice": [], "sfx": [], "bed": []}

    if video:
        inputs += ["-i", str(video)]
    n_in = len(inputs) // 2

    def add(path, loop=False):
        nonlocal n_in
        if loop:
            inputs.extend(["-stream_loop", "-1"])
        inputs.extend(["-i", str(path)])
        n_in += 1
        return n_in - 1

    def finish(idx, label, bus, start, gain_db, chain):
        ms = int(max(0, start) * 1000)
        parts = [f"aresample={SR}", "aformat=channel_layouts=stereo"]
        parts += [c for c in chain if c]
        parts += [f"volume={gain_db}dB", f"adelay={ms}|{ms}", f"atrim=0:{dur}"]
        fc.append(f"[{idx}:a]{','.join(parts)}[{label}]")
        buses[bus].append(label)

    # --- dialogue ---
    for i, c in enumerate(tl.get("dialogue", [])):
        print(f"dialogue {i}: {c.get('character')} @ {c.get('start')}s")
        p = resolve_audio(c, base, cache)
        if not p:
            continue
        ch = CHARACTERS.get(c.get("character", ""), {"pitch": 1, "gain": 0, "fx": ""})
        em = EMOTIONS.get(c.get("emotion", "neutral"), EMOTIONS["neutral"])
        pitch = ch["pitch"] * em["pitch"] * c.get("pitch", 1.0)
        if c.get("recorded_as_is"):   # your real recording already has the voice you want
            pitch, ch, em = 1.0, {"gain": 0, "fx": ""}, {"gain": 0, "fx": ""}
        chain = [pitch_filter(pitch), ch["fx"], em["fx"]]
        gain = ch["gain"] + em["gain"] + c.get("gain", 0)
        finish(add(p), f"d{i}", "voice", c["start"], gain, chain)

    # --- sfx ---
    for i, s in enumerate(tl.get("sfx", [])):
        print(f"sfx {i}: {s.get('file')} @ {s.get('start')}s")
        p = base / s["file"]
        if not p.exists():
            print("  skipped (missing file)")
            continue
        chain = [pitch_filter(s.get("pitch", 1.0))]
        finish(add(p), f"s{i}", "sfx", s["start"], s.get("gain", 0), chain)

    # --- ambience + music (the "bed", ducked under voices) ---
    for kind, key in (("amb", "ambience"), ("mus", "music")):
        for i, a in enumerate(tl.get(key, [])):
            print(f"{key} {i}: {a.get('file')}")
            p = base / a["file"]
            if not p.exists():
                print("  skipped (missing file)")
                continue
            start = a.get("start", 0)
            fade_in, fade_out = a.get("fade_in", 1.0), a.get("fade_out", 2.0)
            end = a.get("end", dur)
            chain = [f"afade=t=in:st={start}:d={fade_in}",
                     f"afade=t=out:st={max(start, end - fade_out)}:d={fade_out}"]
            finish(add(p, loop=a.get("loop", True)), f"{kind}{i}", "bed",
                   start, a.get("gain", -14 if kind == "mus" else -18), chain)

    def mix(labels, out):
        if not labels:
            fc.append(f"anullsrc=r={SR}:cl=stereo,atrim=0:{dur}[{out}]")
        elif len(labels) == 1:
            fc.append(f"[{labels[0]}]anull[{out}]")
        else:
            ins = "".join(f"[{l}]" for l in labels)
            fc.append(f"{ins}amix=inputs={len(labels)}:normalize=0:duration=longest[{out}]")

    mix(buses["voice"], "voicebus")
    mix(buses["sfx"], "sfxbus")
    mix(buses["bed"], "bedbus")

    # dramatic silence: mute the bed (and optionally sfx) in these windows
    bed = "bedbus"
    for j, (a, b) in enumerate(tl.get("silence", [])):
        fc.append(f"[{bed}]volume=enable='between(t,{a},{b})':volume=0[bedsil{j}]")
        bed = f"bedsil{j}"

    # duck the bed under dialogue
    fc.append("[voicebus]asplit=2[vfinal][vkey]")
    fc.append(f"[{bed}][vkey]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=450[ducked]")
    fc.append("[vfinal][sfxbus][ducked]amix=inputs=3:normalize=0:duration=longest[premix]")
    fc.append(f"[premix]loudnorm=I=-16:TP=-1.5:LRA=11,atrim=0:{dur},aresample={SR}[outa]")

    cmd = ["ffmpeg", "-y", *inputs, "-filter_complex", ";".join(fc)]
    out = Path(args.output)
    if video:
        cmd += ["-map", "0:v:0", "-map", "[outa]", "-c:v", "copy",
                "-c:a", "aac", "-b:a", "192k", "-sn", "-shortest"]
    else:
        cmd += ["-map", "[outa]"]
    cmd.append(str(out))

    print("\nRendering...")
    run(cmd)
    print(f"Done: {out.resolve()}")


if __name__ == "__main__":
    main()
