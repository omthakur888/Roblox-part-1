# Odyson — The Town Where the Floor Is Lava

A lightweight, pure-2D animated story renderer. It uses Pillow to draw animated block-style characters and FFmpeg to encode the frames.

## What this project does
- Creates a 50-second vertical story video.
- Uses 2D drawings and sprite-like character parts only.
- Renders at a small internal size, then scales to 1080×1920.
- Outputs 24 FPS video.
- Has a 5-second test mode in GitHub Actions.
- Optionally adds your own narration audio.

## Run locally
```bash
python -m pip install -r requirements.txt
python main.py
```
FFmpeg must also be installed and available on your PATH.

## GitHub Actions
1. Upload the contents of this folder to a GitHub repository.
2. Open **Actions**.
3. Select **Render Odyson Lava Story**.
4. Click **Run workflow**.
5. First choose `true` for a 5-second test.
6. After the test succeeds, run again and choose `false`.
7. Download the MP4 from the workflow run's **Artifacts** section.

## Add narration
Record or create a narration track and place it in the repository root as either:
- `narration.wav`
- `narration.mp3`

When the full render runs, the workflow also creates `odyson_floor_is_lava_with_narration.mp4`. If no narration file is supplied, it creates a silent MP4. The narration should be approximately 50 seconds; the final mux is limited to the shorter track.

## Important
This is a lightweight 2D animated-story prototype, not actual Roblox gameplay and not 3D rendering. Review the test video before rendering the full version. Character art is generated procedurally in Python, so no external image assets are needed.
