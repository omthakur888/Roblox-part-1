import math
import os
import subprocess
from PIL import Image, ImageDraw, ImageFont

W, H = 720, 1280
FPS = 24
DURATION = 42
OUT = "roblox_story.mp4"

def font(size, bold=False):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    for p in candidates:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()

FONT = font(31, True)
SMALL = font(23, True)
TITLE = font(48, True)

def rounded(draw, box, radius, fill, outline=None, width=1):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)

def centered(draw, y, text, f=FONT, fill="white", stroke=3):
    box = draw.textbbox((0,0), text, font=f, stroke_width=stroke)
    x = (W - (box[2]-box[0]))//2
    draw.text((x,y), text, font=f, fill=fill, stroke_width=stroke, stroke_fill="#172033")

def background(scene, t):
    im = Image.new("RGB", (W,H), "#8bd7ff")
    d = ImageDraw.Draw(im)
    # sky and soft clouds
    d.rectangle((0,0,W,760), fill="#8bd7ff")
    for x,y in [(80,150),(330,95),(570,190)]:
        d.ellipse((x-55,y-20,x+30,y+35), fill="#f5fbff")
        d.ellipse((x-15,y-42,x+55,y+38), fill="#f5fbff")
        d.ellipse((x+25,y-18,x+95,y+35), fill="#f5fbff")
    # distant blocky town
    for x,w,h,c in [(0,95,260,"#e8a76d"),(100,110,340,"#f3cf77"),(220,100,235,"#f29a8b"),
                    (475,110,320,"#9bcf9a"),(590,130,270,"#f2c47a")]:
        d.rectangle((x,500-h+220,x+w,760), fill=c)
        for wx in range(x+17,x+w-8,35):
            for wy in range(540-h+220,735,55):
                d.rectangle((wx,wy,wx+15,wy+22), fill="#fff0b5")
    # ground
    d.rectangle((0,760,W,H), fill="#61b96d")
    d.polygon([(0,920),(720,840),(720,1120),(0,1190)], fill="#555f72")
    d.polygon([(0,1010),(720,930),(720,1040),(0,1120)], fill="#707b8d")
    # road markings
    for x in range(-40,800,180):
        d.polygon([(x,1040),(x+65,1033),(x+105,1052),(x+40,1060)], fill="#fff2b0")
    # school or town sign
    if scene in ("school","classroom"):
        rounded(d,(215,330,505,520),18,"#f5c65e","#7b4c38",7)
        d.polygon([(190,345),(360,235),(530,345)], fill="#d65c4b")
        d.rectangle((340,420,405,520), fill="#8c5a42")
        centered(d,355,"SCHOOL",SMALL,"#ffffff",2)
    return im

def draw_character(im, x, y, kind="steve", t=0, expression="normal", scale=1.0, facing=1):
    d = ImageDraw.Draw(im)
    # coordinates are bottom-center; body parts are deliberately blocky
    bob = int(math.sin(t*8)*5) if t else 0
    x, y = int(x), int(y+bob)
    if kind == "steve":
        shirt, pants, skin, hair = "#16a6a1", "#26354f", "#e6ad82", "#30251f"
        headw, headh, bodyw, bodyh = 100, 100, 112, 145
    elif kind == "teacher":
        shirt, pants, skin, hair = "#d59a35", "#333b50", "#d99b70", "#493329"
        headw, headh, bodyw, bodyh = 104, 104, 120, 155
    else:
        shirt, pants, skin, hair = "#e34d55", "#315caa", "#e8b68f", "#38251e"
        headw, headh, bodyw, bodyh = 88, 88, 100, 120
    s=scale
    def box(a,b,c,e): return (int(x+a*s),int(y+b*s),int(x+c*s),int(y+e*s))
    # legs alternate while walking
    phase = math.sin(t*9) if t else 0
    legshift = int(phase*12*s)
    # shoes and legs
    d.rectangle(box(-bodyw*.38,-130+legshift, -bodyw*.02, -12), fill=pants)
    d.rectangle(box(bodyw*.02,-130-legshift, bodyw*.38, -12), fill=pants)
    d.rectangle(box(-bodyw*.46,-20,-bodyw*.0,0), fill="#f4f4f4")
    d.rectangle(box(bodyw*.0,-20,bodyw*.46,0), fill="#f4f4f4")
    # torso
    top = -bodyh- headh*.15
    d.rectangle(box(-bodyw/2,top,bodyw/2,0), fill=shirt, outline="#263247", width=max(2,int(3*s)))
    # arms swing
    arm = int(math.sin(t*9+math.pi)*15*s) if t else 0
    d.rectangle(box(-bodyw/2-22,top+8,-bodyw/2+5,-35+arm), fill=shirt, outline="#263247", width=max(2,int(2*s)))
    d.rectangle(box(bodyw/2-5,top+8,bodyw/2+22,-35-arm), fill=shirt, outline="#263247", width=max(2,int(2*s)))
    d.rectangle(box(-bodyw/2-22,-43+arm,-bodyw/2+5,-25+arm), fill=skin)
    d.rectangle(box(bodyw/2-5,-43-arm,bodyw/2+22,-25-arm), fill=skin)
    # head and hair
    hx1, hy1, hx2, hy2 = -headw/2, top-headh, headw/2, top
    d.rectangle(box(hx1,hy1,hx2,hy2), fill=skin, outline="#263247", width=max(2,int(3*s)))
    d.rectangle(box(hx1,hy1,hx2,hy1+22), fill=hair)
    d.rectangle(box(hx1,hy1+10,hx1+18,hy1+42), fill=hair)
    # eyes
    eye_y = hy1+48
    eye_dx = 23
    d.ellipse(box(-eye_dx-7,eye_y-6,-eye_dx+7,eye_y+8), fill="#ffffff")
    d.ellipse(box(eye_dx-7,eye_y-6,eye_dx+7,eye_y+8), fill="#ffffff")
    d.ellipse(box(-eye_dx-2,eye_y-2,-eye_dx+4,eye_y+6), fill="#172033")
    d.ellipse(box(eye_dx-2,eye_y-2,eye_dx+4,eye_y+6), fill="#172033")
    if expression == "scared":
        d.arc(box(-24,hy1+66,24,hy1+100), 0, 180, fill="#6b3030", width=max(3,int(5*s)))
        d.ellipse(box(-8,hy1+72,8,hy1+91), fill="#542d2d")
    elif expression == "happy":
        d.arc(box(-23,hy1+58,23,hy1+91), 0, 180, fill="#6b3030", width=max(3,int(5*s)))
    else:
        d.line(box(-15,hy1+80,15,hy1+80), fill="#6b3030", width=max(3,int(5*s)))
    if kind=="teacher":
        d.rectangle(box(-43,hy1+40,43,hy1+46), outline="#222b3b", width=max(2,int(4*s)))
        d.line(box(0,hy1+43,0,hy1+48), fill="#222b3b", width=max(2,int(3*s)))

def speech(im, text, y=170, color="#ffffff"):
    d=ImageDraw.Draw(im)
    rounded(d,(45,y,675,y+105),24,color,"#1d2940",5)
    # wrap to max 33 chars
    words=text.split()
    lines=[]; line=""
    for word in words:
        test=(line+" "+word).strip()
        if len(test)> thirty_three:
            lines.append(line); line=word
        else: line=test
    if line: lines.append(line)
    for i,line in enumerate(lines[:2]):
        centered(d,y+13+i*38,line,SMALL,"#172033",0)

thirty_three=33

def scene_frame(frame):
    t=frame/FPS
    if t < 7:
        scene="town"; local=t
    elif t < 15:
        scene="school"; local=t-7
    elif t < 25:
        scene="school"; local=t-15
    elif t < 34:
        scene="town"; local=t-25
    else:
        scene="town"; local=t-34
    im=background(scene,t)
    d=ImageDraw.Draw(im)
    if t < 7:
        centered(d,65,"THE TOWN WITH ONE RULE",TITLE)
        speech(im,"In this town, nobody is allowed to say NO!",175)
        draw_character(im,360,1040,"steve",t, "happy",1.15)
        centered(d,1120,"ONE WORD CAN CHANGE EVERYTHING",SMALL)
    elif t < 15:
        centered(d,65,"MONDAY MORNING",TITLE)
        speech(im,"Steve arrived at school. The teacher announced the rule.",175)
        draw_character(im,250,1050,"steve",t,"normal",1.0)
        draw_character(im,500,1040,"teacher",t,"normal",1.0)
    elif t < 25:
        centered(d,65,"THE BIG MISTAKE",TITLE)
        speech(im,"A student shouted: NO! Then he vanished in a flash!",175)
        draw_character(im,245,1050,"teacher",t,"scared",1.0)
        # teleport sparkle / empty spot
        if t < 21:
            draw_character(im,500,1050,"kid",t,"scared",1.0)
        else:
            for i in range(12):
                a=i*math.pi/6
                xx=500+math.cos(a)*70; yy=920+math.sin(a)*70
                d.line((xx-12,yy-12,xx+12,yy+12),fill="#fff36b",width=7)
                d.line((xx-12,yy+12,xx+12,yy-12),fill="#fff36b",width=7)
        centered(d,1120,"POOF! GONE!",TITLE,"#fff36b")
    elif t < 34:
        centered(d,65,"THE SECRET",TITLE)
        speech(im,"A little kid discovered the truth: the mayor made the rule!",175)
        draw_character(im,265,1050,"kid",t,"happy",1.05)
        # mayor silhouette / sign
        rounded(d,(430,770,650,1010),16,"#6b587e","#263247",5)
        d.rectangle((485,700,595,820),fill="#d9a27e",outline="#263247",width=4)
        d.rectangle((485,700,595,728),fill="#33252a")
        centered(d,820,"MAYOR",SMALL)
    else:
        centered(d,65,"THE REAL TWIST",TITLE)
        speech(im,"The mayor feared the word NO because it could end his control!",175)
        draw_character(im,360,1050,"kid",t,"scared",1.2)
        centered(d,1120,"WOULD YOU SAY NO?",TITLE,"#fff36b")
    # subtle vignette-like bottom caption bar
    d.rectangle((0,H-62,W,H), fill="#172033")
    centered(d,H-55,"ROBLOX-STYLE STORY  •  PART 1",SMALL,"#ffffff",0)
    return im

def main():
    cmd = [
        "ffmpeg","-y","-f","rawvideo","-vcodec","rawvideo",
        "-pix_fmt","rgb24","-s",f"{W}x{H}","-r",str(FPS),
        "-i","-","-an","-c:v","libx264","-preset","ultrafast",
        "-crf","23","-pix_fmt","yuv420p","-movflags","+faststart",OUT
    ]
    proc=subprocess.Popen(cmd, stdin=subprocess.PIPE)
    total=FPS*DURATION
    try:
        for i in range(total):
            frame=scene_frame(i)
            proc.stdin.write(frame.tobytes())
            if i % (FPS*5)==0:
                print(f"Rendered {i//FPS}/{DURATION} seconds")
    finally:
        proc.stdin.close()
    code=proc.wait()
    if code != 0:
        raise RuntimeError("FFmpeg failed. Check the GitHub Actions log.")
    print(f"Finished: {OUT}")

if __name__=="__main__":
    main()