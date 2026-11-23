# Roblox-inspired Noob Story Video

A fully procedural, asset-free animated story project. It creates blocky toy-like characters, school environments, cars, simple motion, English narration, and an original synthesized background music bed.

## Output
- `output/roblox_story.mp4`
- 90 seconds
- 16:9 landscape
- 1920×1080
- H.264 video, AAC audio, 30 fps output

The artwork is a 2D procedural Roblox-inspired animation, not captured Roblox gameplay or a photorealistic 3D render. No external images, paid APIs, or user-provided assets are needed.

## Run locally

Requirements: Python 3.10+, FFmpeg, and espeak-ng.

### Ubuntu / Debian
```bash
sudo apt-get update
sudo apt-get install -y ffmpeg espeak-ng fonts-dejavu-core
python -m pip install -r requirements.txt
python render.py
```

The finished MP4 will be in `output/roblox_story.mp4`.

## Run on GitHub Actions
1. Create a new GitHub repository.
2. Upload all files and folders from this project.
3. Open the **Actions** tab.
4. Select **Render Roblox-inspired story**.
5. Click **Run workflow** (or push to `main`).
6. When it finishes, open the run and download the `roblox-noob-story-mp4` artifact.

The workflow installs FFmpeg and espeak-ng, renders the MP4, checks that it exists, and uploads it as an artifact.

## Customize
Edit the `SCENES` list near the top of `render.py` to change narration. The scene drawing functions below it control the visuals. The renderer intentionally avoids burned-in subtitles so you can add your own text during editing.
