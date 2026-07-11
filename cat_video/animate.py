#!/usr/bin/env python3
"""切り抜いた猫スプライトを動かすカットアウトアニメ版ショート動画.

「にゃんこ劇場」: 兄弟猫のダンス → 普段の2匹カメオ → 新入り登場 →
3にゃんずフィナーレ(紙吹雪)。1080x1920 / 30fps / 約19.5秒。

使い方: python3 animate.py   →  neko_dance.mp4
"""
import math
import os
import subprocess
import wave

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from scipy import ndimage

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, "build")
os.makedirs(WORK, exist_ok=True)

FFMPEG = "/usr/local/lib/python3.11/dist-packages/imageio_ffmpeg/binaries/ffmpeg-linux-x86_64-v7.0.2"
if not os.path.exists(FFMPEG):
    FFMPEG = "ffmpeg"
FONT = "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf"

W, H = 1080, 1920
FPS = 30
DUR = 19.5
FRAMES = int(DUR * FPS)
BPM = 126
BEAT = 60 / BPM
FLOOR = 1560  # 猫たちの接地ライン

# ------------------------------------------------------------ easing --------
def clamp01(x):
    return max(0.0, min(1.0, x))


def ease_out_back(t, s=1.7):
    t = clamp01(t) - 1
    return 1 + t * t * ((s + 1) * t + s)


def ease_out(t):
    t = clamp01(t)
    return 1 - (1 - t) ** 3


def fade(t, t0, t1, fin=0.25, fout=0.25):
    """t0-t1 の間表示、端でフェード。0-1 を返す。"""
    if t < t0 or t > t1:
        return 0.0
    return min(1.0, (t - t0) / fin, (t1 - t) / fout)


# ------------------------------------------------------- sprite loading -----
def stickerize(path, height, outline=12):
    """スプライトを縮小し、白フチ(ステッカー風)を付ける。"""
    sp = Image.open(path).convert("RGBA")
    sp = sp.resize((int(sp.width * height / sp.height), height), Image.LANCZOS)
    # マッティング残りの薄いもや(半透明の背景)を除去:
    # 本体(高アルファの最大連結成分)の近傍以外はアルファ0にする
    arr = np.array(sp)
    a_np = arr[:, :, 3]
    core = a_np > 120
    lab, n = ndimage.label(core)
    if n:
        sizes = np.bincount(lab.ravel())
        sizes[0] = 0
        keep = ndimage.binary_dilation(lab == sizes.argmax(), iterations=8)
        a_np = np.where(keep, a_np, 0)
    a_np[a_np < 25] = 0
    arr[:, :, 3] = a_np
    sp = Image.fromarray(arr)
    a = sp.getchannel("A")
    grow = a.filter(ImageFilter.MaxFilter(outline * 2 + 1))
    grow = grow.filter(ImageFilter.GaussianBlur(2))
    pad = outline + 6
    base = Image.new("RGBA", (sp.width + pad * 2, sp.height + pad * 2), (0, 0, 0, 0))
    white = Image.new("RGBA", sp.size, (255, 255, 255, 255))
    base.paste(white, (pad, pad), grow)
    base.alpha_composite(sp, (pad, pad))
    return base


SPR = {
    "tora": stickerize(os.path.join(HERE, "sprites", "tora.png"), 520),
    "fuwa": stickerize(os.path.join(HERE, "sprites", "fuwa.png"), 540),
    "kuro": stickerize(os.path.join(HERE, "sprites", "kurobody.png"), 470),
    "duo":  stickerize(os.path.join(HERE, "sprites", "duo.png"), 700),
}

# ------------------------------------------------------------ background ----
def make_background():
    top = np.array([183, 224, 255], float)
    mid = np.array([255, 235, 242], float)
    k = np.clip(np.arange(H) / (H * 0.62), 0, 1)[:, None]
    rows = top[None, :] * (1 - k) + mid[None, :] * k
    arr = np.repeat(rows[:, None, :], W, axis=1).astype(np.uint8)
    bg = Image.fromarray(arr, "RGB")
    d = ImageDraw.Draw(bg, "RGBA")
    # 遠くのパステル丘
    d.ellipse((-350, 1280, 640, 1750), fill=(198, 233, 208, 255))
    d.ellipse((420, 1300, 1420, 1780), fill=(214, 240, 220, 255))
    # 地面
    d.rectangle((0, FLOOR - 30, W, H), fill=(232, 247, 235))
    d.ellipse((-220, FLOOR - 90, W + 220, FLOOR + 90), fill=(232, 247, 235))
    # 太陽
    d.ellipse((868, 172, 1008, 312), fill=(255, 226, 148, 255))
    return bg.convert("RGBA")


BG = make_background()


def make_cloud(w):
    c = Image.new("RGBA", (w, w // 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(c)
    for ex in ((0, w * .18, w * .55, w * .48), (w * .25, 0, w * .75, w * .38),
               (w * .45, w * .15, w, w * .46)):
        d.ellipse(ex, fill=(255, 255, 255, 215))
    return c.filter(ImageFilter.GaussianBlur(6))


CLOUDS = [(make_cloud(360), 0.55, 210, 14), (make_cloud(300), 0.30, 430, -10)]


def paw_stamp(r, color):
    img = Image.new("RGBA", (r * 4, r * 4), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx = cy = r * 2
    d.ellipse((cx - r, cy - r * .6, cx + r, cy + r * 1.4), fill=color)
    for i, ang in enumerate((-55, -18, 18, 55)):
        a = math.radians(ang - 90)
        dist = r * 1.55 if i in (0, 3) else r * 1.85
        px_, py_ = cx + dist * math.cos(a), cy + r * .2 + dist * math.sin(a)
        rr = r * .42
        d.ellipse((px_ - rr, py_ - rr, px_ + rr, py_ + rr), fill=color)
    return img


PAW = paw_stamp(20, (255, 178, 196, 90))


def make_heart(size, color=(255, 108, 138, 235)):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = size
    d.polygon([(s * .5, s * .92), (s * .06, s * .42), (s * .5, s * .3),
               (s * .94, s * .42)], fill=color)
    d.ellipse((s * .03, s * .12, s * .5, s * .58), fill=color)
    d.ellipse((s * .5, s * .12, s * .97, s * .58), fill=color)
    return img


HEART = make_heart(90)
BIGHEART = make_heart(150)


def make_note(size, color):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    f = ImageFont.truetype(FONT, size - 8)
    d.text((size // 2, size // 2), "♪", font=f, fill=color, anchor="mm")
    return img


NOTES = [make_note(84, (120, 150, 255, 235)), make_note(70, (255, 150, 120, 235))]


def make_sparkle(size, color=(255, 220, 120, 240)):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c = size / 2
    for ang in range(0, 360, 90):
        a = math.radians(ang)
        d.polygon([(c + c * .95 * math.cos(a), c + c * .95 * math.sin(a)),
                   (c + c * .22 * math.cos(a + 1.2), c + c * .22 * math.sin(a + 1.2)),
                   (c + c * .22 * math.cos(a - 1.2), c + c * .22 * math.sin(a - 1.2))],
                  fill=color)
    return img


SPARK = make_sparkle(72)

# ------------------------------------------------------------ captions ------
def caption_img(text, size=68, fill=(255, 255, 255), outline=(196, 108, 76),
                band=None):
    f = ImageFont.truetype(FONT, size)
    tmp = Image.new("RGBA", (W, size * 2 + 40), (0, 0, 0, 0))
    d = ImageDraw.Draw(tmp)
    d.text((W / 2, tmp.height / 2), text, font=f, anchor="mm",
           fill=outline, stroke_width=10, stroke_fill=outline)
    d.text((W / 2, tmp.height / 2), text, font=f, anchor="mm", fill=fill)
    if band:
        tw = d.textlength(text, font=f)
        bimg = Image.new("RGBA", tmp.size, (0, 0, 0, 0))
        bd = ImageDraw.Draw(bimg)
        x0 = (W - tw) / 2 - 42
        bd.rounded_rectangle((x0, 8, W - x0, tmp.height - 8),
                             radius=(tmp.height - 16) / 2, fill=band)
        bimg.alpha_composite(tmp)
        return bimg
    return tmp


CAPS = {
    "title": caption_img("にゃんこ劇場 ♪", 96, (255, 255, 255), (233, 122, 90)),
    "dance": caption_img("シンクロ率100%のふたごダンス ♪", 58),
    "usual": caption_img("※ちなみに普段のふたり", 58, (255, 255, 255), (120, 140, 210)),
    "newbie": caption_img("あたらしい仲間、きた!?", 68, (255, 255, 255), (90, 90, 110)),
    "trio": caption_img("きょうから なかよし3にゃんず ★", 58, (255, 255, 255), (233, 122, 90)),
    "end": caption_img("みんな、うちの宝物 ♡", 72, (255, 255, 255), (226, 110, 140)),
    "thanks": caption_img("最後まで見てくれてありがとう", 44, (255, 250, 230), (170, 130, 90)),
}


def make_bubble(text="!?"):
    img = Image.new("RGBA", (300, 240), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((10, 10, 290, 190), fill=(255, 255, 255, 245),
              outline=(90, 90, 110, 255), width=6)
    d.polygon([(100, 175), (60, 235), (150, 185)], fill=(255, 255, 255, 245))
    f = ImageFont.truetype(FONT, 96)
    d.text((150, 100), text, font=f, anchor="mm", fill=(233, 90, 70))
    return img


BUBBLE = make_bubble()


def make_excl():
    img = Image.new("RGBA", (90, 120), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    f = ImageFont.truetype(FONT, 100)
    d.text((45, 60), "!", font=f, anchor="mm",
           fill=(255, 196, 60), stroke_width=8, stroke_fill=(180, 110, 30))
    return img


EXCL = make_excl()

# ------------------------------------------------------------- helpers ------
def blit(canvas, img, cx, cy, scale=1.0, angle=0.0, alpha=1.0, sy=None):
    if scale <= 0.01 or alpha <= 0.01:
        return
    w = max(2, int(img.width * scale))
    h = max(2, int(img.height * (sy if sy else scale)))
    s = img.resize((w, h), Image.BILINEAR)
    if angle:
        s = s.rotate(angle, expand=True, resample=Image.BILINEAR)
    if alpha < 1.0:
        a = s.getchannel("A").point(lambda v: int(v * alpha))
        s.putalpha(a)
    canvas.alpha_composite(s, (int(cx - s.width / 2), int(cy - s.height / 2)))


def shadow(canvas, cx, w, lift):
    """接地影。lift(跳躍高)が大きいほど小さく薄く。"""
    k = clamp01(1 - lift / 260)
    sw = w * (0.42 + 0.18 * k)
    sh = sw * 0.22
    ell = Image.new("RGBA", (int(sw), int(sh)), (0, 0, 0, 0))
    ImageDraw.Draw(ell).ellipse((0, 0, sw - 1, sh - 1),
                                fill=(90, 80, 80, int(70 * k)))
    ell = ell.filter(ImageFilter.GaussianBlur(5))
    canvas.alpha_composite(ell, (int(cx - sw / 2), int(FLOOR - sh / 2 + 14)))


# 紙吹雪 (決定論的に生成)
rng = np.random.default_rng(7)
CONFETTI = [dict(x=float(rng.uniform(30, W - 30)), t0=float(rng.uniform(11.8, 17.5)),
                 spd=float(rng.uniform(240, 420)), ph=float(rng.uniform(0, 6.28)),
                 rot=float(rng.uniform(-240, 240)), size=int(rng.integers(16, 34)),
                 col=tuple(int(v) for v in rng.choice(
                     [(255, 150, 160), (150, 190, 255), (255, 216, 130),
                      (160, 226, 180), (216, 170, 255)])))
            for _ in range(90)]
CONF_IMGS = {}
for c in CONFETTI:
    key = (c["size"], c["col"])
    if key not in CONF_IMGS:
        img = Image.new("RGBA", (c["size"], int(c["size"] * 0.62)), c["col"] + (235,))
        CONF_IMGS[key] = img
    c["img"] = CONF_IMGS[key]

# ---------------------------------------------------------- choreography ----
def dancer_pose(t, x_home, phase, join=0.0):
    """通常ダンスの座標・角度・スクワッシュを返す。"""
    hop_t = (t / BEAT + phase) % 1.0
    lift = abs(math.sin(math.pi * hop_t)) * 52
    sway_x = 34 * math.sin(2 * math.pi * t / (4 * BEAT) + phase * 2.4)
    angle = 7.5 * math.sin(2 * math.pi * t / (2 * BEAT) + phase * 3.1)
    squash = 1.0 - 0.09 * (1 - clamp01(lift / 52))
    return x_home + sway_x, lift, angle, squash


def scene(t):
    """1フレーム描画して RGBA canvas を返す。"""
    cv = BG.copy()
    d = ImageDraw.Draw(cv, "RGBA")

    # 雲と浮遊肉球
    for img, spd, y, amp in CLOUDS:
        x = (t * spd * 18) % (W + img.width) - img.width
        cv.alpha_composite(img, (int(x), int(y + amp * math.sin(t * 0.7))))
    for i in range(5):
        yy = (H - (t * 46 + i * 400) % (H + 200)) - 100
        xx = 80 + (i * 223) % (W - 160) + 26 * math.sin(t * 0.9 + i)
        blit(cv, PAW, xx, yy, scale=0.9 + 0.25 * (i % 3), alpha=0.75)

    # --- 主役たちの配置 ---
    # 参加後の並び位置へスライド (9.6-10.6s)
    j = ease_out((t - 9.6) / 1.0) if t > 9.6 else 0.0
    tora_home = 290 - 100 * j
    fuwa_home = 790 + 80 * j

    startle = fade(t, 8.35, 9.1, 0.08, 0.3)  # びっくりジャンプ

    for name, home, ph, ent0, ent1, side in (
            ("tora", tora_home, 0.0, 0.30, 1.60, -1),
            ("fuwa", fuwa_home, 0.5, 0.55, 1.85, 1)):
        sp = SPR[name]
        x, lift, ang, sq = dancer_pose(t, home, ph)
        # 入場: 画面外から
        if t < ent1:
            k = ease_out((t - ent0) / (ent1 - ent0)) if t >= ent0 else 0.0
            x = (-300 if side < 0 else W + 300) + (x - (-300 if side < 0 else W + 300)) * k
        if startle > 0:
            lift += 120 * startle * abs(math.sin(math.pi * clamp01((t - 8.35) / 0.75)))
            ang += -side * 13 * startle
        y = FLOOR - sp.height * sq / 2 - lift + 26
        shadow(cv, x, sp.width, lift)
        blit(cv, sp, x, y, angle=ang, sy=sq)
        if startle > 0.4:
            blit(cv, EXCL, x + side * 40, y - sp.height / 2 - 70,
                 scale=0.8 + 0.3 * startle, alpha=startle)

    # 新入り (くろ): 8.2s に下からポップ、その後ダンスに参加
    if t > 8.2:
        sp = SPR["kuro"]
        pop = ease_out_back((t - 8.2) / 0.7) if t < 8.9 else 1.0
        if t < 9.6:
            x = 540
            lift = 0.0
            ang = 6 * math.sin((t - 8.2) * 9) * clamp01((t - 8.5) * 2)
            sq = 1.0
        else:
            x, lift, ang, sq = dancer_pose(t, 540, 0.25)
        y_hidden = FLOOR + sp.height * 0.55 + 260
        # 参加後は少し手前(下)に立たせて奥行きを出す
        depth = 60 * (ease_out((t - 9.6) / 1.0) if t > 9.6 else 0.0)
        y_shown = FLOOR - sp.height * sq / 2 - lift + 26 + depth
        y = y_hidden + (y_shown - y_hidden) * pop if t < 9.6 else y_shown
        if t > 8.6:
            shadow(cv, x, sp.width, lift)
        blit(cv, sp, x, y, angle=ang, sy=sq)
        # 吹き出し「!?」
        bs = fade(t, 8.55, 9.9, 0.18, 0.25)
        if bs > 0:
            blit(cv, BUBBLE, x + 300, y - sp.height / 2 - 60,
                 scale=0.55 + 0.45 * ease_out_back(clamp01((t - 8.55) / 0.3)),
                 alpha=bs)

    # 普段のふたり カメオ (6.8-8.25s)
    cameo = fade(t, 6.8, 8.25, 0.3, 0.2)
    if cameo > 0:
        k = ease_out_back(clamp01((t - 6.8) / 0.45))
        blit(cv, SPR["duo"], 540, 900, scale=k * (1 + 0.02 * math.sin(t * 3)),
             angle=4 * math.sin(t * 2.2), alpha=cameo)
        for sx, sy_ in ((250, 700), (830, 720), (300, 1130), (810, 1100)):
            blit(cv, SPARK, sx, sy_, scale=0.7 + 0.4 * math.sin(t * 5 + sx),
                 alpha=cameo)

    # ハート (仲良しシーン)
    for t0, hx, drift in ((2.2, 540, 20), (2.9, 480, -26), (3.4, 610, 14),
                          (13.2, 300, 18), (14.0, 800, -20), (14.8, 540, 24),
                          (16.6, 250, 16), (17.2, 840, -18), (17.8, 545, 20)):
        life = (t - t0) / 1.6
        if 0 < life < 1:
            blit(cv, HEART, hx + drift * life * 3,
                 1150 - 340 * ease_out(life),
                 scale=0.5 + 0.6 * min(1, life * 3), alpha=1 - life ** 2)

    # 音符 (ダンス中)
    if 3.8 < t < 8.2 or 10.5 < t < 18.5:
        for i, t0 in enumerate(np.arange(4.0, 18.5, 0.9)):
            life = (t - t0) / 1.5
            if 0 < life < 1:
                nx = (200 + i * 260) % 800 + 140
                blit(cv, NOTES[i % 2], nx + 30 * math.sin(life * 5 + i),
                     1050 - 380 * life, scale=0.6 + 0.4 * life,
                     alpha=1 - life ** 2)

    # 紙吹雪 (フィナーレ)
    if t > 11.8:
        for c in CONFETTI:
            life = t - c["t0"]
            if life <= 0:
                continue
            y = -40 + c["spd"] * life
            if y > H + 40:
                continue
            x = c["x"] + 46 * math.sin(life * 2.2 + c["ph"])
            blit(cv, c["img"], x, y, angle=(c["rot"] * life) % 360)

    # 字幕
    def cap(key, y, t0, t1, pop=True):
        a = fade(t, t0, t1, 0.22, 0.25)
        if a > 0:
            s = 0.7 + 0.3 * ease_out_back(clamp01((t - t0) / 0.35)) if pop else 1.0
            blit(cv, CAPS[key], W / 2, y, scale=s, alpha=a)

    cap("title", 330, 0.4, 3.6)
    cap("dance", 360, 4.2, 6.6)
    cap("usual", 380, 7.0, 8.2)
    cap("newbie", 360, 8.7, 11.6)
    cap("trio", 360, 12.3, 15.6)
    cap("end", 330, 16.2, 19.4)
    cap("thanks", 450, 16.8, 19.4, pop=False)
    return cv


# ---------------------------------------------------------------- music -----
SR = 44100
NOTES_FREQ = {n: 440.0 * 2 ** ((i - 9) / 12)
              for i, n in enumerate("C C# D D# E F F# G G# A A# B".split())}


def freq(name):
    return NOTES_FREQ[name[:-1]] * 2 ** (int(name[-1]) - 4)


def synth_note(f0, dur, amp=0.22, timbre=(1.0, 0.35, 0.12)):
    n = int(SR * dur)
    t = np.arange(n) / SR
    w = sum(a * np.sin(2 * np.pi * f0 * (i + 1) * t) for i, a in enumerate(timbre))
    env = np.minimum(1, t / 0.012) * np.exp(-t * 3.2)
    return amp * env * w


def make_music(path, total):
    eighth = BEAT / 2
    buf = np.zeros(int(SR * (total + 2)))

    def add(sig, t0):
        i = int(t0 * SR)
        buf[i:i + len(sig)] += sig[:len(buf) - i]

    chords = ["C", "G", "A", "F", "C", "G", "A", "F", "F", "G", "C"]
    melody = [
        "C5 E5 G5 E5 A5 G5 E5 C5", "D5 G5 B5 G5 D6 B5 G5 D5",
        "E5 A5 C6 A5 E5 C5 E5 A5", "F5 A5 C6 A5 F5 C5 A4 F5",
        "G5 E5 C5 E5 G5 A5 G5 E5", "B4 D5 G5 D5 B5 G5 D5 B4",
        "A4 C5 F5 C5 A5 F5 C5 A4", "C5 E5 G5 C6 G5 E5 C5 C5",
    ]
    t = 0.0
    for bar, root in enumerate(chords):
        if t > total:
            break
        for b in (0, 2):
            add(synth_note(freq(root + "2"), BEAT * 0.9, 0.20, (1.0, 0.5, 0.0)),
                t + b * BEAT)
        for iv in (0, 4, 7):
            add(synth_note(freq(root + "3") * 2 ** (iv / 12), BEAT * 3.6, 0.05), t)
        for k, name in enumerate(melody[bar % len(melody)].split()):
            add(synth_note(freq(name), eighth * 1.7, 0.16), t + k * eighth)
        r = np.random.default_rng(bar)
        for k in range(8):
            n = int(SR * 0.03)
            hat = r.standard_normal(n) * np.exp(-np.arange(n) / (SR * 0.006))
            add(0.05 * hat * (1.0 if k % 2 == 0 else 0.6), t + k * eighth)
        t += BEAT * 4

    # SFX: 新入りポップ
    n = int(SR * 0.22)
    tt = np.arange(n) / SR
    sweep = np.sin(2 * np.pi * (320 + 1400 * tt / 0.22) * tt)
    add(0.32 * sweep * np.exp(-tt * 14), 8.25)
    # SFX: フィナーレのきらきらアルペジオ
    for i, nm in enumerate(("C6", "E6", "G6", "C7")):
        add(synth_note(freq(nm), 0.5, 0.16, (1.0, 0.2, 0.0)), 16.2 + i * 0.09)

    buf = buf[:int(SR * total)]
    buf = np.tanh(buf * 1.4) * 0.85
    pcm = (buf * 32767).astype(np.int16)
    with wave.open(path, "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


# ----------------------------------------------------------------- main -----
def main():
    music = os.path.join(WORK, "bgm2.wav")
    make_music(music, DUR)
    print("music done")

    out = os.path.join(HERE, "neko_dance.mp4")
    proc = subprocess.Popen(
        [FFMPEG, "-y",
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
         "-r", str(FPS), "-i", "-",
         "-i", music,
         "-filter_complex",
         f"[0:v]fade=t=out:st={DUR - 0.7}:d=0.7[v];"
         f"[1:a]afade=t=in:st=0:d=0.4,afade=t=out:st={DUR - 1.3}:d=1.3[a]",
         "-map", "[v]", "-map", "[a]",
         "-c:v", "libx264", "-preset", "medium", "-crf", "19",
         "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
         "-movflags", "+faststart", out],
        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL)
    for f in range(FRAMES):
        frame = scene(f / FPS).convert("RGB")
        proc.stdin.write(frame.tobytes())
        if f % 90 == 0:
            print(f"frame {f}/{FRAMES}")
    proc.stdin.close()
    proc.wait()
    print("output:", out, os.path.getsize(out), "bytes")


if __name__ == "__main__":
    main()
