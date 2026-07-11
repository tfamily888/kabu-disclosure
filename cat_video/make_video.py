#!/usr/bin/env python3
"""うちの猫たちのSNS向けショート動画ジェネレーター.

写真5枚から 1080x1920 (9:16) / 約18秒のショート動画を生成する。
- Ken Burns (ズーム) エフェクト + クロスフェード
- 日本語字幕 (IPAゴシック) を Pillow で描画して合成
- BGM は numpy でチップチューン風に自動合成

使い方: python3 make_video.py
出力:   neko_short.mp4
"""

import math
import os
import subprocess
import wave

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, "build")
os.makedirs(WORK, exist_ok=True)

FFMPEG = "/usr/local/lib/python3.11/dist-packages/imageio_ffmpeg/binaries/ffmpeg-linux-x86_64-v7.0.2"
if not os.path.exists(FFMPEG):
    FFMPEG = "ffmpeg"

FONT = "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf"

W, H = 1080, 1920          # 出力解像度 (9:16)
SRC_W, SRC_H = 1620, 2880  # zoompan 用に 1.5 倍で下ごしらえ
FPS = 30
SCENE_SEC = 4.0
XFADE_SEC = 0.6

# ---------------------------------------------------------------- scenes ----
# focus: 9:16 に切り出すときの水平方向の注視点 (0.0=左端, 0.5=中央, 1.0=右端)
SCENES = [
    dict(photo="s1_floor.jpg",   focus=0.5, zoom="in",
         badge="猫のいる暮らし ♪",
         caption="うちの猫たちが\n可愛すぎる件"),
    dict(photo="s2_bed.jpg",     focus=0.5, zoom="out",
         caption="シンクロ率\nほぼ100%の兄弟"),
    dict(photo="s3_hammock.jpg", focus=0.5, zoom="in",
         caption="ケンカした5分後が\nこちら"),
    dict(photo="s4_newbie.jpg",  focus=0.45, zoom="out",
         caption="そこへ…\n新入りちゃん登場!"),
    dict(photo="s5_relax.jpg",   focus=0.45, zoom="in",
         caption="一瞬で\n大物の風格♡",
         sub="最後まで見てくれてありがとう ★"),
]


def prepare_photo(path: str, focus: float, out: str) -> None:
    """EXIF 回転を補正し、9:16 に切り出して SRC_W x SRC_H で保存する。"""
    im = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    w, h = im.size
    target = 9 / 16
    if w / h > target:  # 横に余る → 幅を focus 中心に切る
        cw = int(h * target)
        x0 = int(w * focus - cw / 2)
        x0 = max(0, min(w - cw, x0))
        im = im.crop((x0, 0, x0 + cw, h))
    else:               # 縦に余る → 中央を切る
        ch = int(w / target)
        y0 = (h - ch) // 2
        im = im.crop((0, y0, w, y0 + ch))
    im = im.resize((SRC_W, SRC_H), Image.LANCZOS)
    im.save(out, quality=92)


def draw_paw(d: ImageDraw.ImageDraw, cx: int, cy: int, r: int, fill) -> None:
    """シンプルな肉球マークを描く。"""
    d.ellipse((cx - r, cy - r * 0.6, cx + r, cy + r * 1.4), fill=fill)
    for i, ang in enumerate((-55, -18, 18, 55)):
        a = math.radians(ang - 90)
        dist = r * 1.55 if i in (0, 3) else r * 1.85
        px, py = cx + dist * math.cos(a), cy + r * 0.2 + dist * math.sin(a)
        rr = r * 0.42
        d.ellipse((px - rr, py - rr, px + rr, py + rr), fill=fill)


def text_with_outline(d, xy, text, font, fill, outline, ow, anchor="ma"):
    d.text(xy, text, font=font, fill=outline, anchor=anchor,
           stroke_width=ow, stroke_fill=outline)
    d.text(xy, text, font=font, fill=fill, anchor=anchor)


def make_caption(scene: dict, out: str) -> None:
    """1080x1920 の透過 PNG に字幕・バッジを描く。"""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # 上部バッジ (シーン1のみ)
    if scene.get("badge"):
        f = ImageFont.truetype(FONT, 46)
        tw = d.textlength(scene["badge"], font=f)
        pad, bh = 38, 78
        x0 = (W - tw) / 2 - pad
        y0 = 200
        d.rounded_rectangle((x0, y0, x0 + tw + pad * 2, y0 + bh),
                            radius=bh / 2, fill=(255, 122, 89, 235))
        d.text((W / 2, y0 + bh / 2), scene["badge"], font=f,
               fill=(255, 255, 255, 255), anchor="mm")

    # メイン字幕 (下部・縁取り付き)
    f = ImageFont.truetype(FONT, 92)
    lines = scene["caption"].split("\n")
    line_h = 118
    base_y = 1450
    # 半透明の帯で可読性を確保
    band_h = line_h * len(lines) + 90
    band = Image.new("RGBA", (W, band_h), (0, 0, 0, 0))
    bd = ImageDraw.Draw(band)
    bd.rounded_rectangle((40, 0, W - 40, band_h), radius=44,
                         fill=(20, 16, 24, 150))
    band = band.filter(ImageFilter.GaussianBlur(1))
    img.alpha_composite(band, (0, base_y - 55))
    for i, line in enumerate(lines):
        text_with_outline(d, (W / 2, base_y + i * line_h), line, f,
                          fill=(255, 255, 255, 255),
                          outline=(35, 25, 45, 255), ow=8)

    # サブ字幕 (エンドカード)
    if scene.get("sub"):
        fs = ImageFont.truetype(FONT, 44)
        text_with_outline(d, (W / 2, base_y + line_h * len(lines) + 70),
                          scene["sub"], fs,
                          fill=(255, 230, 120, 255),
                          outline=(35, 25, 45, 255), ow=6)
        draw_paw(d, 120, base_y + 40, 26, (255, 190, 90, 220))
        draw_paw(d, W - 120, base_y + 40, 26, (255, 190, 90, 220))

    img.save(out)


# ----------------------------------------------------------------- music ----
SR = 44100


def synth_note(freq, dur, amp=0.22, timbre=(1.0, 0.35, 0.12)):
    n = int(SR * dur)
    t = np.arange(n) / SR
    wavef = sum(a * np.sin(2 * np.pi * freq * (i + 1) * t)
                for i, a in enumerate(timbre))
    env = np.minimum(1, t / 0.012) * np.exp(-t * 3.2)
    return amp * env * wavef


NOTES = {n: 440.0 * 2 ** ((i - 9) / 12)
         for i, n in enumerate("C C# D D# E F F# G G# A A# B".split())}


def freq(name):  # "C5" -> Hz
    return NOTES[name[:-1]] * 2 ** (int(name[-1]) - 4)


def make_music(path: str, total: float) -> None:
    bpm = 126
    beat = 60 / bpm
    eighth = beat / 2
    buf = np.zeros(int(SR * (total + 2)))

    def add(sig, t0):
        i = int(t0 * SR)
        buf[i:i + len(sig)] += sig[:len(buf) - i]

    # コード進行: C - G - Am - F を2周 (王道ポップ進行)
    chords = ["C", "G", "A", "F", "C", "G", "F", "C"]
    # 1小節 = 8分音符 x 8 のメロディ (ペンタトニック中心)
    melody = [
        "C5 E5 G5 E5 A5 G5 E5 C5", "D5 G5 B5 G5 D6 B5 G5 D5",
        "E5 A5 C6 A5 E5 C5 E5 A5", "F5 A5 C6 A5 F5 C5 A4 F5",
        "G5 E5 C5 E5 G5 A5 G5 E5", "B4 D5 G5 D5 B5 G5 D5 B4",
        "A4 C5 F5 C5 A5 F5 C5 A4", "C5 E5 G5 C6 G5 E5 C5 C5",
    ]
    t = 0.0
    for bar in range(len(chords)):
        root = chords[bar]
        # ベース (1・3拍)
        for b in (0, 2):
            add(synth_note(freq(root + "2"), beat * 0.9, 0.20,
                           (1.0, 0.5, 0.0)), t + b * beat)
        # コードパッド (小節頭)
        for iv in (0, 4, 7):
            f0 = freq(root + "3") * 2 ** (iv / 12)
            add(synth_note(f0, beat * 3.6, 0.05), t)
        # メロディ
        for k, name in enumerate(melody[bar].split()):
            add(synth_note(freq(name), eighth * 1.7, 0.16), t + k * eighth)
        # ハイハット (8分)
        rng = np.random.default_rng(bar)
        for k in range(8):
            n = int(SR * 0.03)
            hat = rng.standard_normal(n) * np.exp(-np.arange(n) / (SR * 0.006))
            add(0.05 * hat * (1.0 if k % 2 == 0 else 0.6), t + k * eighth)
        t += beat * 4

    buf = buf[:int(SR * total)]
    buf = np.tanh(buf * 1.4) * 0.85  # soft clip
    pcm = (buf * 32767).astype(np.int16)
    with wave.open(path, "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


# ------------------------------------------------------------------ video ---
def run(cmd):
    subprocess.run(cmd, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main():
    frames = int(SCENE_SEC * FPS)
    scene_files = []
    for i, sc in enumerate(SCENES, 1):
        photo = os.path.join(WORK, f"photo{i}.jpg")
        cap = os.path.join(WORK, f"cap{i}.png")
        clip = os.path.join(WORK, f"scene{i}.mp4")
        prepare_photo(os.path.join(HERE, "photos", sc["photo"]),
                      sc["focus"], photo)
        make_caption(sc, cap)

        if sc["zoom"] == "in":
            z = f"1+0.11*on/{frames - 1}"
        else:
            z = f"1.11-0.11*on/{frames - 1}"
        zp = (f"zoompan=z='{z}':x='iw/2-(iw/zoom)/2':y='ih/2-(ih/zoom)/2'"
              f":d=1:s={W}x{H}:fps={FPS}")
        run([FFMPEG, "-y",
             "-loop", "1", "-framerate", str(FPS), "-t", str(SCENE_SEC), "-i", photo,
             "-loop", "1", "-framerate", str(FPS), "-t", str(SCENE_SEC), "-i", cap,
             "-filter_complex",
             f"[0:v]{zp}[bg];"
             f"[1:v]format=rgba,fade=t=in:st=0.35:d=0.4:alpha=1[c];"
             f"[bg][c]overlay=0:0,format=yuv420p",
             "-c:v", "libx264", "-preset", "medium", "-crf", "19",
             "-r", str(FPS), clip])
        scene_files.append(clip)
        print(f"scene {i} done")

    n = len(scene_files)
    total = SCENE_SEC * n - XFADE_SEC * (n - 1)
    music = os.path.join(WORK, "bgm.wav")
    make_music(music, total)
    print("music done")

    transitions = ["fade", "slideleft", "smoothup", "fade"]
    inputs = []
    for f in scene_files:
        inputs += ["-i", f]
    fc, prev = [], "[0:v]"
    for i in range(1, n):
        off = SCENE_SEC * i - XFADE_SEC * i
        label = f"[v{i}]" if i < n - 1 else "[vout]"
        fc.append(f"{prev}[{i}:v]xfade=transition={transitions[i - 1]}"
                  f":duration={XFADE_SEC}:offset={off:.3f}{label}")
        prev = f"[v{i}]"
    fc.append(f"[{n}:a]afade=t=in:st=0:d=0.5,"
              f"afade=t=out:st={total - 1.4:.2f}:d=1.4[aout]")

    out = os.path.join(HERE, "neko_short.mp4")
    run([FFMPEG, "-y", *inputs, "-i", music,
         "-filter_complex", ";".join(fc),
         "-map", "[vout]", "-map", "[aout]",
         "-c:v", "libx264", "-preset", "medium", "-crf", "19",
         "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "160k",
         "-movflags", "+faststart", "-shortest", out])
    print("output:", out, os.path.getsize(out), "bytes")


if __name__ == "__main__":
    main()
