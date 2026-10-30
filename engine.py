"""
Stickman & Realistic History Video Engine
Supports Stickman Vector rendering AND Photorealistic character synthesis via free API pipelines.
"""
import asyncio, json, math, os, re, subprocess, tempfile, urllib.error, urllib.request, wave
import numpy as np
from PIL import Image, ImageColor, ImageDraw, ImageFont

SR = 44100
FADE = 0.35
LEAD = 0.4
PAD = 0.45
WPS = 2.5

PROPS = ["fire", "mammoth", "tent", "tree", "snow", "dust", "embers", "stars", "moon"]
CAMERAS = ["pan", "push_in", "pull_out", "static"]
ACTIONS = ["walk", "stand", "wave"]
WEAPONS = ["spear", "sword", "none"]

ERAS = {
    "stone_age": dict(sky=[(0, "#2E2547"), (.38, "#7A4A6E"), (.7, "#E8805A"), (1, "#FAC775")], sun=(.5, .8, "#FFF0C2", .055),
        far="mountains", far_c="#8A5C7A", snow=False, mid="hills", mid_c="#5A3A5E", ground="#1E120D", rim="#E8805A",
        ink="#140B07", part="dust", tint=("#FF9A4A", .07), weapon="spear", beast="#2E1B38"),
    "ice_age": dict(sky=[(0, "#0E1F3A"), (.45, "#3F6C94"), (1, "#CFE6F5")], sun=(.3, .7, "#FFFFFF", .04),
        far="mountains", far_c="#8FAAC2", snow=True, mid="hills", mid_c="#6F8FA8", ground="#BFD3E2", rim="#FFFFFF",
        ink="#0B1622", part="snow", tint=("#7FB5FF", .08), weapon="spear", beast="#2A3442"),
    "ancient_egypt": dict(sky=[(0, "#3B3A7A"), (.35, "#C9677A"), (.7, "#F2A65A"), (1, "#FFD98A")], sun=(.62, .78, "#FFF2C4", .09),
        far="pyramids", far_c="#B8793F", snow=False, mid="dunes", mid_c="#D69A52", ground="#6B4020", rim="#FFD98A",
        ink="#2A1608", part="dust", tint=("#FFB347", .08), weapon="spear", beast="#4A2A12"),
    "ancient_china": dict(sky=[(0, "#2B1B33"), (.4, "#9B3B4A"), (.75, "#F0935A"), (1, "#F8D58B")], sun=(.5, .7, "#FFE9B0", .08),
        far="karst", far_c="#5A4256", snow=False, mid="hills", mid_c="#3F2F3F", ground="#1A0F14", rim="#F8D58B",
        ink="#0D0709", part="dust", tint=("#FF7A59", .06), weapon="sword", beast="#2A1A22"),
    "medieval": dict(sky=[(0, "#1B2A41"), (.5, "#4E6E8E"), (1, "#C9D6DF")], sun=(.7, .7, "#FFFFFF", .045),
        far="castles", far_c="#4A5A6B", snow=False, mid="hills", mid_c="#33414F", ground="#141A20", rim="#AAB8C4",
        ink="#06090C", part="none", tint=("#8FB3D9", .06), weapon="sword", beast="#1A222B"),
    "night": dict(sky=[(0, "#04050E"), (.5, "#0F1838"), (1, "#2A3A66")], sun=None,
        far="mountains", far_c="#1B2542", snow=False, mid="hills", mid_c="#111830", ground="#05070F", rim="#6C82C8",
        ink="#000000", part="none", tint=("#4466CC", .07), weapon="none", beast="#0A0F20", stars=True, moon=True),
}
ASPECTS = {"9:16 vertical (Shorts, TikTok, Reels)": "v", "16:9 horizontal (YouTube)": "h"}
QUALITY = {"480p (fastest)": 480, "720p (recommended)": 720, "1080p (slow)": 1080}

def rgb(c):
    return ImageColor.getrgb(c)[:3]

def dims(aspect, quality):
    s = QUALITY.get(quality, 720)
    big = int(round(s * 16 / 9 / 2) * 2)
    return (s, big) if ASPECTS.get(aspect, "v") == "v" else (big, s)

def get_font(size):
    for n in ("DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf", "Arial Bold.ttf", "arialbd.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(n, size)
        except Exception:
            pass
    try:
        return ImageFont.load_default(size)
    except Exception:
        return ImageFont.load_default()

def get_realistic_character(era, style="Realistic Model", h=300):
    prompts = {
        "stone_age": "full body realistic ancient caveman, historical attire, transparent background style",
        "ice_age": "full body realistic prehistoric human in fur coat, photorealistic historical",
        "ancient_egypt": "full body realistic ancient Egyptian warrior Pharaoh, cinematic photorealistic",
        "ancient_china": "full body realistic ancient Chinese dynasty soldier emperor, photorealistic",
        "medieval": "full body realistic medieval knight in iron armor, historical photorealistic",
        "night": "full body realistic shadowy cloak traveler, photorealistic"
    }
    prompt = prompts.get(era, "full body realistic historical human figure")
    encoded = urllib.parse.quote(prompt)
    url = f"https://image.pollinations.ai/prompt/{encoded}?width=400&height=600&nologo=true&seed=42"
    try:
        tmp_img = tempfile.mktemp(suffix=".jpg")
        urllib.request.urlretrieve(url, tmp_img)
        img = Image.open(tmp_img).convert("RGBA")
        img = img.resize((int(h * 0.7), h), Image.LANCZOS)
        return img
    except Exception:
        img = Image.new("RGBA", (int(h*0.7), h), (200, 150, 100, 255))
        return img

KEYWORDS = [("fire", ["fire", "flame", "torch", "burn"]), ("mammoth", ["mammoth", "beast", "hunt", "elephant"]),
            ("tent", ["tent", "camp", "shelter", "cave", "hut", "village"]), ("tree", ["tree", "forest", "wood", "jungle"]),
            ("snow", ["snow", "ice", "cold", "freez", "glacier", "winter"]), ("stars", ["night", "dark", "star", "moon", "dream"]),
            ("dust", ["desert", "dust", "sand", "storm"]) ]

def norm_scene(s, era, i):
    if isinstance(s, str):
        s = {"narration": s}
    text = re.sub(r"\s+", " ", str(s.get("narration", ""))).strip()
    if not text:
        return None
    cam = s.get("camera") if s.get("camera") in CAMERAS else ["pan", "push_in", "pan", "static", "pull_out"][i % 5]
    act = s.get("action") if s.get("action") in ACTIONS else ("walk" if cam == "pan" else "stand")
    props = [p for p in (s.get("props") or []) if p in PROPS]
    e = s.get("era") if s.get("era") in ERAS else era
    try:
        n = max(0, min(5, int(s.get("characters", 1))))
    except Exception:
        n = 1
    wp = s.get("weapon") if s.get("weapon") in WEAPONS else ERAS[e]["weapon"]
    return dict(narration=text, era=e, camera=cam, action=act, props=props, characters=n, weapon=wp,
                label=str(s.get("label", "") or "").strip()[:60])

def plain_to_scenes(text, era):
    sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", text.strip())) if s.strip()]
    blocks, cur, n = [], [], 0
    for s in sents:
        cur.append(s); n += len(s.split())
        if n >= 22:
            blocks.append(" ".join(cur)); cur, n = [], 0
    if cur:
        if blocks and n < 8:
            blocks[-1] += " " + " ".join(cur)
        else:
            blocks.append(" ".join(cur))
    out = []
    for i, b in enumerate(blocks):
        low = b.lower()
        props = [p for p, ks in KEYWORDS if any(k in low for k in ks)]
        chars = 3 if any(k in low for k in ("tribe", "people", "humans", "army", "crowd", "village")) else 1
        out.append(dict(narration=b, props=props, characters=chars))
    return out

def parse_script(text, era="stone_age", title=""):
    text = (text or "").strip()
    if not text:
        raise ValueError("The script is empty.")
    data = None
    if text.startswith("{") or text.startswith("```"):
        try:
            data = json.loads(re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip())
        except Exception as e:
            raise ValueError(f"Script JSON error: {e}")
    if data is None:
        data = {"scenes": plain_to_scenes(text, era)}
    base_era = data.get("era") if data.get("era") in ERAS else era
    scenes = [norm_scene(s, base_era, i) for i, s in enumerate(data.get("scenes", []))]
    scenes = [s for s in scenes if s]
    return dict(title=title or str(data.get("title", "") or ""), scenes=scenes)

def run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()

async def _edge(text, voice, rate, out):
    import edge_tts
    await edge_tts.Communicate(text, voice, rate=rate).save(out)

def ffmpeg(*args):
    r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args], capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(r.stderr[-400:])

def read_wav(p):
    with wave.open(p) as w:
        return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)

def tts(text, voice, rate, base, st):
    mp3, wav = base + ".mp3", base + ".wav"
    ok = False
    if st["edge"]:
        for _ in range(2):
            try:
                run_async(_edge(text, voice, rate, mp3))
                ok = os.path.getsize(mp3) > 800
                if ok: break
            except Exception as e:
                st["err"] = f"edge-tts: {e}"
        if not ok: st["edge"] = False
    if ok:
        try:
            ffmpeg("-i", mp3, "-ar", str(SR), "-ac", "1", "-c:a", "pcm_s16le", wav)
            return read_wav(wav)
        except Exception as e:
            st["err"] = str(e)
    return None

def make_sky(W, H, gy, era, moon):
    stops = era["sky"]
    t = np.linspace(0, 1, H, dtype=np.float32)[:, None] * (H / gy)
    t = np.clip(t, 0, 1)
    pos = [s[0] for s in stops]
    arr = np.empty((H, W, 3), dtype=np.float32)
    for c in range(3):
        arr[:, :, c] = np.interp(t, pos, [rgb(s[1])[c] for s in stops])
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")

class Pen:
    def __init__(self, w, h, top, bot, ss, col):
        self.ss, self.w, self.h, self.top, self.col = ss, w, h, top, col
        self.im = Image.new("RGBA", (w * ss, (h + top + bot) * ss), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.im)
    def P(self, x, y):
        return (self.w * self.ss / 2 + x * self.h * self.ss, (y * self.h + self.top) * self.ss)
    def seg(self, a, b, wd):
        wd = max(1, int(wd * self.ss))
        self.d.line([a, b], fill=self.col, width=wd)
    def done(self):
        return self.im.resize((self.w, self.im.height // self.ss), Image.LANCZOS)

def make_char(h, phase, action, weapon, ink):
    p = Pen(int(h * .95), h, int(h * .42), int(h * .05), 4, rgb(ink) + (255,))
    lw = max(3, h * .055)
    p.d.ellipse([*p.P(-.085, .015), *p.P(.085, .185)], fill=p.col)
    p.seg(p.P(0, .185), p.P(0, .55), lw)
    p.seg(p.P(0, .55), p.P(.2, .95), lw)
    p.seg(p.P(0, .55), p.P(-.2, .95), lw)
    return p.done()

class Renderer:
    def __init__(self, W, H, bars, fade, captions, character_style="2D Stickman"):
        self.W, self.H, self.bars, self.fade, self.captions = W, H, bars, fade, captions
        self.char_style = character_style
        self.land = W > H
        self.gy = int(H * (.76 if self.land else .70))
        self.ch = int((.26 if self.land else .14) * H)

    def frame(self, sc, t, g, total):
        W, H, gy, era = self.W, self.H, self.gy, ERAS[sc["era"]]
        fr = make_sky(W, H, gy, era, False)
        d = ImageDraw.Draw(fr)
        d.rectangle([0, gy, W, H], fill=rgb(era["ground"]))
        if self.char_style == "Realistic Model":
            char_img = get_realistic_character(sc["era"], h=self.ch)
            fr.paste(char_img, (int(W/2 - char_img.width/2), int(gy - char_img.height)), char_img)
        else:
            s = make_char(self.ch, t, sc["action"], sc["weapon"], era["ink"])
            fr.paste(s, (int(W/2 - s.width/2), int(gy - self.ch)), s)
        return fr

def render(script_text, era, aspect, quality, fps, voice, speed, music_mode, music_file, music_vol,
           bars, fade, captions, title, outro, character_style, preview, progress):
    script = parse_script(script_text, era, title)
    scenes = script["scenes"]
    W, H = dims(aspect, quality)
    fps = int(fps)
    tmp = tempfile.mkdtemp(prefix="video_")
    st = {"edge": True, "err": ""}
    voices = []
    for i, sc in enumerate(scenes):
        a = tts(sc["narration"], voice, "+0%", os.path.join(tmp, f"v{i}"), st)
        if a is None: a = np.zeros(SR * 2, dtype=np.int16)
        voices.append(a)
    track = []
    for i, (sc, a) in enumerate(zip(scenes, voices)):
        vd = len(a) / SR
        sc["dur"] = max(2.5, vd + 0.8)
        seg = np.concatenate([a, np.zeros(int(PAD * SR), dtype=np.int16)])
        track.append(seg)
    audio_path = os.path.join(tmp, "audio.wav")
    voice_all = np.concatenate(track)
    with wave.open(audio_path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes(voice_all.tobytes())
    R = Renderer(W, H, bars, fade, captions, character_style)
    out = os.path.join(tmp, "output.mp4")
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(fps), "-i", "-",
           "-i", audio_path, "-c:a", "aac", "-c:v", "libx264", "-pix_fmt", "yuv420p", out]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for sc in scenes:
        nframes = int(round(sc["dur"] * fps))
        for f in range(nframes):
            t = f / fps
            proc.stdin.write(R.frame(sc, t, 0, 0).tobytes())
    proc.stdin.close()
    proc.wait()
    return out, "Success"
