# Oddyson Render

One-command voice acting + sound design mixer. Drop in your video, voice recordings and sound effects, edit `timeline.json`, and render.

## Setup

1. Install [ffmpeg](https://ffmpeg.org/download.html) (must include `ffprobe`).
2. Python 3.8+. No packages required.
3. Optional neural TTS fallback: `pip install edge-tts` (needs internet).

## Folder layout

```
render.py
timeline.json
assets/
  video.mp4          your silent or rough video
  voice/             recorded dialogue (wav/mp3)
  sfx/               whoosh, thruster, impact, footsteps, riser...
  amb/               wind, flying vehicle loops
  music/             background music
```

## Run

```
python render.py timeline.json -o final.mp4
```

No video? Remove `"video"` from the timeline, set `"duration"`, and use `-o final.wav`.

## How voices work

- **Your recordings win.** If a clip's `file` exists it is used. Record each character separately.
- If the file is missing and `text` is set, `edge-tts` generates a natural neural voice (only if installed).
- Characters: `oddyson`, `quiet_boy`, `narrator`. Each gets its own pitch, tone and compression (edit `CHARACTERS` in `render.py`).
- Emotions per line: `neutral`, `excited`, `shout`, `whisper`, `suspense`, `funny`, `sad`.
- Already performed the voice the way you want it? Add `"recorded_as_is": true` to skip the character processing.
- Per-clip overrides: `"pitch": 1.1`, `"gain": 3`.

## Timing and sync

Every clip has a `start` time in seconds. Match it to the frame where the action happens (frame number / fps). Re-render is fast because the video stream is copied, not re-encoded.

## Mixing

- Music and ambience are automatically ducked under dialogue.
- `"silence": [[36, 39]]` mutes music and ambience for the dramatic pause before the reveal. Keep SFX out of that window for true silence.
- Output is loudness-normalized (-16 LUFS) with a true-peak limit.
- Subtitles and captions are never added (`-sn`).

## Tips

- Free SFX sources: freesound.org, pixabay.com/sound-effects, zapsplat.com (check each license).
- Keep clips as separate files; the mixer handles overlap.
