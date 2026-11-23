#!/usr/bin/env python3
"""
Procedural Roblox-inspired story animation.
Creates a 90-second 16:9 MP4 using Pillow + FFmpeg + espeak-ng.
No external images, video clips, or paid APIs are required.
"""
from PIL import Image, ImageDraw, ImageFont
import math, os, subprocess, shutil, wave, struct
from pathlib import Path

W, H = 960, 540
FPS = 24
DURATION = 90
OUT = Path("output")
FRAMES = OUT / "frames"
OUT.mkdir(exist_ok=True)
FRAMES.mkdir(exist_ok=True)

# Nine short visual beats, each with narration and a distinct setting/action.
SCENES = [
    ("A small town school", "For years, a quiet student known as Noob was laughed at because his clothes were old and his family had very little money."),
    ("The fee announcement", "One morning, the school owner announced that tuition fees would triple. Many families could no longer afford to keep their children in school."),
    ("Noob speaks up", "Noob stepped forward. He said that a family's income should never decide whether a child gets an education."),
    ("A promise", "Some students laughed again, but Noob stayed calm. He promised that he would find a way to help every student learn."),
    ("The next morning", "The next morning, a line of shining cars arrived outside the school. Everyone stopped and stared."),
    ("The big reveal", "A visitor introduced Noob as the founder of the Bright Future Education Foundation. The students could hardly believe it."),
    ("A new school", "Noob used the foundation to build a bright, modern school. Every student could study there without paying tuition."),
    ("Everything included", "Books, uniforms, classrooms and learning supplies were provided free. No child would be turned away because of money."),
    ("A better ending", "The bullies apologized. Noob forgave them. He had never wanted revenge. He wanted equal opportunities for everyone.")
]

# Palette
SKY=(127,190,235); GRASS=(92,166,93); NAVY=(28,43,67); WHITE=(247,248,250)
GOLD=(255,196,72); BLUE=(57,130,210); RED=(205,75,75); DARK=(43,48,58)
font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
regular_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
def font(sz, bold=True):
    p = font_path if bold else regular_path
    try: return ImageFont.truetype(p, sz)
    except: return ImageFont.load_default()

def rect(d, xy, fill, outline=None, width=1):
    d.rectangle(xy, fill=fill, outline=outline, width=width)

def draw_person(d, x, y, scale=1.0, shirt=BLUE, pants=NAVY, head=(230,185,145),
                hair=(55,42,32), pose="stand", sad=False):
    # x,y is center-bottom. Deliberately blocky toy-like proportions.
    s=scale
    def box(a,b,c,e,col,outline=DARK):
        d.rectangle((int(x+a*s),int(y+b*s),int(x+c*s),int(y+e*s)), fill=col, outline=outline, width=max(1,int(2*s)))
    # legs
    if pose=="walk":
        box(-17, -58, -3, -8, pants); box(4, -58, 18, -8, pants)
        box(-23, -9, -1, -2, DARK); box(3, -9, 25, -2, DARK)
    else:
        box(-17,-58,-3,-7,pants); box(4,-58,18,-7,pants)
        box(-23,-8,-1,-2,DARK); box(3,-8,25,-2,DARK)
    # torso and arms
    box(-23,-112,23,-58,shirt)
    if pose=="raise":
        box(-39,-110,-24,-77,head); box(-39,-140,-24,-105,head)
        box(24,-110,39,-77,head)
    else:
        box(-39,-108,-24,-66,head); box(24,-108,39,-66,head)
    # square head
    box(-25,-158,25,-112,head)
    box(-26,-161,26,-150,hair)
    # face
    d.ellipse((x-13*s,y-142*s,x-8*s,y-137*s), fill=DARK)
    d.ellipse((x+8*s,y-142*s,x+13*s,y-137*s), fill=DARK)
    if sad:
        d.arc((x-8*s,y-132*s,x+8*s,y-121*s), 200, 340, fill=DARK, width=max(1,int(2*s)))
    else:
        d.arc((x-8*s,y-136*s,x+8*s,y-124*s), 15, 165, fill=DARK, width=max(1,int(2*s)))

def draw_school(d, x, y, scale=1, modern=False):
    s=scale
    w,h=(300,190) if not modern else (360,205)
    # building body
    body=(238,225,190) if not modern else (222,241,250)
    roof=(178,65,62) if not modern else (45,111,168)
    rect(d,(x-w*s/2,y-h*s,x+w*s/2,y),body,DARK,2)
    d.polygon([(x-w*s/2-15*s,y-h*s),(x,y-h*s-70*s),(x+w*s/2+15*s,y-h*s)],fill=roof)
    # windows
    for wx in (-.32,-.1,.13,.34):
        rect(d,(x+wx*w*s-18*s,y-h*s+35*s,x+wx*w*s+18*s,y-h*s+78*s),(112,183,222),DARK,2)
    rect(d,(x-28*s,y-75*s,x+28*s,y), (105,75,57), DARK,2)
    if modern:
        rect(d,(x-80*s,y-h*s-48*s,x+80*s,y-h*s-20*s),(255,255,255),BLUE,2)
        d.text((x,y-h*s-34*s),"BRIGHT FUTURE",font=font(int(13*s)),fill=BLUE,anchor="mm")

def draw_car(d,x,y,scale=1,color=RED):
    s=scale
    d.rounded_rectangle((x-65*s,y-35*s,x+65*s,y+5*s),radius=int(10*s),fill=color,outline=DARK,width=2)
    d.polygon([(x-38*s,y-35*s),(x-18*s,y-62*s),(x+30*s,y-62*s),(x+49*s,y-35*s)],fill=color,outline=DARK)
    rect(d,(x-13*s,y-57*s,x+25*s,y-38*s),(160,210,228),DARK,1)
    for xx in (-40,40):
        d.ellipse((x+(xx-14)*s,y-8*s,x+(xx+14)*s,y+20*s),fill=(30,32,38),outline=(220,220,220),width=2)

def background(d, night=False):
    d.rectangle((0,0,W,H),fill=(48,64,103) if night else SKY)
    # soft clouds
    if not night:
        for x,y in [(120,85),(690,105),(830,70)]:
            d.ellipse((x-45,y-18,x+15,y+18),fill=(246,250,255))
            d.ellipse((x-10,y-30,x+48,y+18),fill=(246,250,255))
    d.rectangle((0,390,W,H),fill=GRASS)
    d.rectangle((0,430,W,H),fill=(190,170,130))
    # distant trees
    for x in range(25, W, 130):
        d.rectangle((x-5,335,x+5,405),fill=(105,75,48))
        d.ellipse((x-30,290,x+30,355),fill=(56,135,77))

def centered_text(d, text, y, size=24, color=WHITE):
    d.text((W//2,y),text,font=font(size),fill=color,anchor="mm",stroke_width=2,stroke_fill=(20,30,45))

def wrap_words(text, max_chars=65):
    words=text.split(); lines=[]; line=""
    for word in words:
        if len(line)+len(word)+1 > max_chars:
            lines.append(line); line=word
        else: line=(line+" "+word).strip()
    if line: lines.append(line)
    return lines

def draw_frame(t, scene_idx):
    im=Image.new("RGB",(W,H),SKY); d=ImageDraw.Draw(im)
    background(d)
    local=t-scene_idx*10
    # gentle camera drift
    drift=int(7*math.sin(local*.55))
    if scene_idx in (0,1,2,3):
        draw_school(d, 480+drift, 390, .95, False)
    elif scene_idx in (6,7,8):
        draw_school(d, 480+drift, 390, 1.0, True)

    # Scene-specific storytelling
    if scene_idx==0:
        draw_person(d,280,440,1.0,shirt=(105,111,123),pants=(55,63,83),sad=True)
        draw_person(d,590,440,.95,shirt=(230,170,55),pants=(55,63,83))
        draw_person(d,700,440,.95,shirt=(100,175,115),pants=(55,63,83))
        centered_text(d,"A SCHOOL WHERE NOOB NEVER FIT IN",42,23)
    elif scene_idx==1:
        draw_person(d,300,440,1.0,shirt=(105,111,123),sad=True)
        rect(d,(610,105,875,245),(250,247,230),DARK,3)
        centered_text(d,"NEW SCHOOL FEES",130,19,NAVY)
        centered_text(d,"3x HIGHER",184,32,RED)
        centered_text(d,"Families are worried",222,15,NAVY)
    elif scene_idx==2:
        draw_person(d,320,440,1.05,shirt=(105,111,123),pose="raise")
        draw_person(d,610,440,1.0,shirt=(120,135,155))
        centered_text(d,"EDUCATION IS FOR EVERYONE",48,24)
        rect(d,(525,105,865,190),(255,255,255),DARK,2)
        centered_text(d,"NO CHILD LEFT BEHIND",148,18,BLUE)
    elif scene_idx==3:
        draw_person(d,480,440,1.1,shirt=(105,111,123),pose="raise")
        for x in (220,740): draw_person(d,x,440,.9,shirt=(125,145,175))
        centered_text(d,"A PROMISE TO EVERY STUDENT",45,24)
        d.ellipse((535,105,665,235),fill=(255,255,255),outline=GOLD,width=5)
        centered_text(d,"★",170,65,GOLD)
    elif scene_idx==4:
        # convoy arriving
        for i,x in enumerate((180,480,780)):
            draw_car(d,x+int(10*math.sin(local)),415,.95,[BLUE,(35,42,55),GOLD][i])
        draw_person(d,480,340,1.0,shirt=(105,111,123))
        centered_text(d,"THE NEXT MORNING...",48,29)
    elif scene_idx==5:
        for i,x in enumerate((210,480,750)):
            draw_car(d,x,420,.8,[BLUE,(35,42,55),GOLD][i])
        draw_person(d,480,440,1.1,shirt=(105,111,123))
        rect(d,(310,90,650,180),(255,255,255),GOLD,4)
        centered_text(d,"FOUNDER: NOOB",125,25,BLUE)
        centered_text(d,"BRIGHT FUTURE FOUNDATION",155,13,NAVY)
    elif scene_idx==6:
        draw_person(d,300,440,1.0,shirt=(105,111,123))
        draw_person(d,650,440,.95,shirt=(80,155,110))
        centered_text(d,"A BRAND-NEW SCHOOL",42,26)
    elif scene_idx==7:
        draw_person(d,250,440,.9,shirt=(105,111,123))
        draw_person(d,480,440,.9,shirt=(75,145,205))
        draw_person(d,710,440,.9,shirt=(185,115,165))
        # books and uniform icons
        for x in (350,610):
            rect(d,(x-28,265,x+28,330),GOLD,DARK,2)
            d.line((x,267,x,328),fill=DARK,width=2)
        centered_text(d,"FREE BOOKS  •  FREE UNIFORMS",48,23)
    else:
        draw_person(d,330,440,1.0,shirt=(105,111,123))
        draw_person(d,610,440,.95,shirt=(230,170,55))
        draw_person(d,730,440,.95,shirt=(100,175,115))
        centered_text(d,"EQUAL CHANCES. A BETTER FUTURE.",45,22)
        d.ellipse((430,110,530,210),fill=GOLD,outline=WHITE,width=4)
        centered_text(d,"★",160,48,WHITE)

    # Small unobtrusive scene marker, no subtitles/captions.
    d.rounded_rectangle((18,18,145,48),radius=9,fill=(22,35,54))
    d.text((30,24),f"STORY  {scene_idx+1}/9",font=font(15),fill=WHITE)
    # fade at beat boundaries
    fade=min(1.0, local/0.5, (10-local)/0.5)
    if fade<1:
        overlay=Image.new("RGB",(W,H),(8,12,22))
        im=Image.blend(im,overlay,max(0,1-fade))
    return im

def run(cmd):
    subprocess.run(cmd, check=True)

def make_audio():
    narration=OUT/"narration.wav"
    espeak=shutil.which("espeak-ng") or shutil.which("espeak")
    if not espeak:
        raise RuntimeError("espeak-ng/espeak not found. Install espeak-ng before rendering.")
    # Make each narration segment with a small pause; combine via ffmpeg concat.
    wavs=[]
    for i,(_,line) in enumerate(SCENES):
        p=OUT/f"voice_{i:02d}.wav"
        run([espeak,"-v","en-us+f3","-s","148","-a","175","-w",str(p),line])
        wavs.append(p)
    concat=OUT/"voice_list.txt"
    concat.write_text("".join(f"file '{p.resolve()}'\n" for p in wavs))
    run(["ffmpeg","-y","-f","concat","-safe","0","-i",str(concat),"-ac","2","-ar","44100",str(narration)])
    # Pad narration to full 90 seconds; synthesize a gentle original ambient music bed.
    import numpy as np
    sr=44100
    n=sr*DURATION
    tt=np.arange(n)/sr
    # Original, soft instrumental-style synthesized bed; no copyrighted recording.
    chord=np.zeros(n,dtype=np.float32)
    chords=[(220.00,261.63,329.63),(196.00,246.94,293.66),(174.61,220.00,261.63),(196.00,246.94,293.66)]
    for k in range(4):
        mask=(tt>=k*22.5)&(tt<(k+1)*22.5)
        local=tt[mask]-k*22.5
        for f in chords[k%4]:
            chord[mask]+=0.035*np.sin(2*np.pi*f*local)
    # Gentle pulse, fade in/out
    env=np.minimum(1,tt/2)*np.minimum(1,(DURATION-tt)/3)
    music=(chord*env).clip(-.15,.15)
    raw=OUT/"music.wav"
    stereo=np.column_stack([music,music])
    with wave.open(str(raw),"wb") as wf:
        wf.setnchannels(2); wf.setsampwidth(2); wf.setframerate(sr)
        wf.writeframes((stereo*32767).astype("<i2").tobytes())
    # Mix voice with music, pad to duration.
    run(["ffmpeg","-y","-i",str(narration),"-i",str(raw),"-filter_complex",
         "[0:a]apad,atrim=0:90,volume=1.0[v];[1:a]volume=0.22[m];[v][m]amix=inputs=2:duration=longest,alimiter=limit=0.95[a]",
         "-map","[a]","-t","90","-ar","44100","-ac","2",str(OUT/"final_audio.wav")])

def main():
    if not shutil.which("ffmpeg"):
        raise RuntimeError("FFmpeg is required. Install FFmpeg and retry.")
    # Remove stale frames from a previous run.
    for p in FRAMES.glob("*.png"): p.unlink()
    total=DURATION*FPS
    for frame in range(total):
        t=frame/FPS
        idx=min(8,int(t//10))
        im=draw_frame(t,idx)
        im.save(FRAMES/f"{frame:05d}.png",compress_level=1)
        if frame % 240 == 0: print(f"Rendered {frame}/{total} frames",flush=True)
    make_audio()
    out_file=OUT/"roblox_story.mp4"
    run(["ffmpeg","-y","-framerate",str(FPS),"-i",str(FRAMES/"%05d.png"),
         "-i",str(OUT/"final_audio.wav"),"-vf","scale=1920:1080:flags=lanczos,format=yuv420p",
         "-r","30","-c:v","libx264","-preset","medium","-crf","20",
         "-c:a","aac","-b:a","192k","-shortest","-movflags","+faststart",str(out_file)])
    print(f"SUCCESS: {out_file.resolve()}")

if __name__=="__main__":
    main()
