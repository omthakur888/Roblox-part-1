ROBLOX-STYLE 3D YOUTUBE SHORT GENERATOR
Title: IN THIS TOWN, NOBODY IS ALLOWED TO SCREAM!

REQUIREMENTS
- Blender 4.x (4.0, 4.1, 4.2 LTS, 4.3, or 4.4+) installed on your system
- Python 3.10+ (for running outside Blender and Edge TTS)
- Internet connection (for Edge TTS natural neural narration; automatic offline fallback included)

QUICK START
1. Put all project files in one folder (e.g., roblox_short/).
2. Install Python dependencies:
   pip install -r requirements.txt
3. Run the automated pipeline (builds audio, 3D world, characters, renders preview + final MP4):
   python generate_short.py

OPTIONS
- Render only the 10-second preview first:
  python generate_short.py --preview-only
- Render only the full 57-second Short:
  python generate_short.py --full-only
- Specify Blender path manually if not in PATH:
  BLENDER_PATH="C:\Program Files\Blender Foundation\Blender 4.2\blender.exe" python generate_short.py
- Or invoke Blender directly:
  blender -b -P generate_short.py

OUTPUTS
- output/preview_10_seconds.mp4  (and ./preview_10_seconds.mp4)
- output/roblox_short_final.mp4  (and ./roblox_short_final.mp4)
