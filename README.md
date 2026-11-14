# Roblox-style 2.5D story — GitHub renderer

This starter project creates a vertical 720×1280 MP4 using Python, Pillow and FFmpeg.
It does **not** require Blender, a PC, or local rendering. GitHub Actions renders it in the cloud.

## Story: The Town Where Nobody Can Say NO

- Everyone in town is forbidden from saying "NO".
- Steve hears the rule at school.
- A student says "NO" and vanishes.
- A kid discovers the mayor created the rule to control everyone.
- The short ends with: "Would you say NO?"

The project currently renders a 42-second silent animated short with simple original block-cartoon characters, moving limbs, speech cards, town backgrounds and scene changes. It is a 2.5D-style illustration, **not true 3D**.

## Run it using only an Android phone

1. Sign in to GitHub in Chrome.
2. Create a new repository, for example `roblox-story`.
3. Upload `main.py` and the `.github/workflows/render.yml` file, keeping the folders exactly as shown.
   - On GitHub's upload page, create the `.github/workflows` folders first if needed.
4. Open the repository's **Actions** tab.
5. Select **Render Roblox-style story**.
6. Tap **Run workflow**.
7. Wait for the workflow to finish.
8. Open the completed workflow run, scroll to **Artifacts**, and download `roblox-story-mp4`.
9. Extract the ZIP to get `roblox_story.mp4`.

## Change the story

Edit the text in `main.py` inside the `scene_frame()` function. Keep the scene timings unless you also adjust the scene conditions.

## Notes

- Output: `roblox_story.mp4`
- Resolution: 720×1280 (vertical Shorts format)
- Frame rate: 24 FPS
- Duration: 42 seconds
- No music or voiceover is included; add those later in a mobile video editor if desired.