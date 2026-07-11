#!/usr/bin/env python3
"""うちの猫たちのLINEスタンプジェネレーター(アニメ風).

切り抜きスプライトをセル画調(バイラテラル平滑 + 減色 + 線画)に変換し、
LINEスタンプ規格 (370x320 透過PNG、main 240x240、tab 96x74) で出力する。

使い方: python3 make_stamps.py  →  stamps/ に出力 + stamps_preview.png
"""
import math
import os

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
SPRITES = os.path.join(HERE, "sprites")
OUT = os.path.join(HERE, "stamps")
os.makedirs(OUT, exist_ok=True)

FONT = "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf"
STAMP_W, STAMP_H = 370, 320


# ---------------------------------------------------------- cartoonify ------
def cartoonify(sprite: Image.Image, max_side=760) -> Image.Image:
    """写真をアニメ(セル画)風に変換する。"""
    sp = sprite.convert("RGBA")
    sp.thumbnail((max_side, max_side), Image.LANCZOS)
    arr = np.array(sp)
    rgb, alpha = arr[:, :, :3], arr[:, :, 3]

    # 1) エッジを保ちつつ平滑化 (セル画の塗り面)
    smooth = rgb.copy()
    for _ in range(3):
        smooth = cv2.bilateralFilter(smooth, d=9, sigmaColor=55, sigmaSpace=9)

    # 2) 彩度・明度をアニメ寄りにブースト
    hsv = cv2.cvtColor(smooth, cv2.COLOR_RGB2HSV).astype(np.float32)
    hsv[:, :, 1] = np.clip(hsv[:, :, 1] * 1.3 + 6, 0, 255)
    hsv[:, :, 2] = np.clip(hsv[:, :, 2] * 1.16 + 22, 0, 255)
    smooth = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2RGB)

    # 3) 減色 (k-means) でフラットな色面に
    h, w = smooth.shape[:2]
    data = smooth.reshape(-1, 3).astype(np.float32)
    sel = alpha.reshape(-1) > 40  # 猫本体の色だけでパレットを学習
    sample = data[sel][:: max(1, sel.sum() // 12000)]
    K = 14
    _, _, centers = cv2.kmeans(
        sample, K, None,
        (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 12, 1.0),
        2, cv2.KMEANS_PP_CENTERS)
    dists = ((data[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2)
    quant = centers[dists.argmin(axis=1)].reshape(h, w, 3).astype(np.uint8)
    # 塗り面をわずかに平滑化してカクつきを抑える
    quant = cv2.medianBlur(quant, 5)

    # 4) 線画 (輪郭線): 平滑化後の画像から抽出し、毛のノイズを拾わない
    gray = cv2.cvtColor(smooth, cv2.COLOR_RGB2GRAY)
    gray = cv2.medianBlur(gray, 5)
    edges = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C,
                                  cv2.THRESH_BINARY, 15, 6)
    mask = (255 - edges) > 0
    # 小さな線ゴミを除去
    nlab, lab, stats, _ = cv2.connectedComponentsWithStats(
        mask.astype(np.uint8), connectivity=8)
    keep = np.zeros_like(mask)
    for i in range(1, nlab):
        if stats[i, cv2.CC_STAT_AREA] >= 40:
            keep |= lab == i
    line = keep.astype(np.float32)
    line = cv2.GaussianBlur(line, (3, 3), 0) * 0.6  # 少し柔らかく

    ink = np.array([84, 58, 52], np.float32)  # こげ茶の線
    out = quant.astype(np.float32) * (1 - line[:, :, None]) \
        + ink[None, None, :] * line[:, :, None]
    out = np.clip(out, 0, 255).astype(np.uint8)

    return Image.fromarray(np.dstack([out, alpha]))


def add_outline(sp: Image.Image, width=9, color=(255, 255, 255, 255)):
    """ステッカー風の白フチ。"""
    a = sp.getchannel("A").point(lambda v: 0 if v < 30 else v)
    sp = sp.copy()
    sp.putalpha(a)
    grow = a.filter(ImageFilter.MaxFilter(width * 2 + 1))
    grow = grow.filter(ImageFilter.GaussianBlur(1.2))
    pad = width + 5
    base = Image.new("RGBA", (sp.width + pad * 2, sp.height + pad * 2), (0, 0, 0, 0))
    fill = Image.new("RGBA", sp.size, color)
    base.paste(fill, (pad, pad), grow)
    base.alpha_composite(sp, (pad, pad))
    return base


# ------------------------------------------------------------- text ---------
def draw_text(d, xy, text, size, fill, stroke=(255, 255, 255, 255), sw=9,
              anchor="mm", max_w=336):
    f = ImageFont.truetype(FONT, size)
    while size > 20 and d.textlength(text, font=f) + sw * 2 > max_w:
        size -= 2
        f = ImageFont.truetype(FONT, size)
    d.text(xy, text, font=f, anchor=anchor, fill=stroke,
           stroke_width=sw, stroke_fill=stroke)
    d.text(xy, text, font=f, anchor=anchor, fill=fill)


def draw_vtext(d, x, y0, text, size, fill, stroke=(255, 255, 255, 255), sw=8,
               max_h=300):
    """縦書き(1文字ずつ積む)。"""
    while size > 18 and y0 + len(text) * size * 1.06 > y0 + max_h:
        size -= 2
    f = ImageFont.truetype(FONT, size)
    y = y0
    for ch in text:
        d.text((x, y), ch, font=f, anchor="ma", fill=stroke,
               stroke_width=sw, stroke_fill=stroke)
        d.text((x, y), ch, font=f, anchor="ma", fill=fill)
        y += int(size * 1.06)


def paw(d, cx, cy, r, color):
    d.ellipse((cx - r, cy - r * .6, cx + r, cy + r * 1.4), fill=color)
    for i, ang in enumerate((-55, -18, 18, 55)):
        a = math.radians(ang - 90)
        dist = r * 1.55 if i in (0, 3) else r * 1.85
        px, py = cx + dist * math.cos(a), cy + r * .2 + dist * math.sin(a)
        rr = r * .42
        d.ellipse((px - rr, py - rr, px + rr, py + rr), fill=color)


def heart(d, cx, cy, s, color):
    d.polygon([(cx, cy + s * .45), (cx - s * .48, cy - s * .1),
               (cx, cy - s * .22), (cx + s * .48, cy - s * .1)], fill=color)
    d.ellipse((cx - s * .5, cy - s * .42, cx, cy + s * .08), fill=color)
    d.ellipse((cx, cy - s * .42, cx + s * .5, cy + s * .08), fill=color)


# ------------------------------------------------------------ stamps --------
# name: (sprite, text, text色, 配置指定)
STAMPS = [
    dict(name="01_nani",    sprite="bowl",     text="なにしてるの?",
         color=(235, 120, 40), pos="top"),
    dict(name="02_asobo",   sprite="upside",   text="あそぼ!",
         color=(240, 95, 135), pos="top"),
    dict(name="03_sotto",   sprite="boxcurl",  text="そっとしといて…",
         color=(90, 120, 190), pos="top"),
    dict(name="04_oyasumi", sprite="sleep",    text="おやすみ",
         color=(120, 95, 190), pos="top", zzz=True),
    dict(name="05_itera",   sprite="perch",    text="いってらっしゃい",
         color=(70, 150, 120), pos="left-v"),
    dict(name="06_ohayo",   sprite="fuwa",     text="おはよう!",
         color=(235, 160, 40), pos="top", sun=True),
    dict(name="07_yoroshiku", sprite="kurobody", text="よろしくね!",
         color=(90, 160, 80), pos="top"),
    dict(name="08_daisuki", sprite="duo",      text="だいすき♡",
         color=(235, 90, 130), pos="top", hearts=True),
]


def compose(st, toon):
    cv = Image.new("RGBA", (STAMP_W, STAMP_H), (0, 0, 0, 0))
    d = ImageDraw.Draw(cv)

    if st["pos"] == "left-v":
        text_h = 0
        area = (10, 10, STAMP_W - 10, STAMP_H - 10)
        sp_max_w, sp_max_h = 240, 290
        sp_cx, sp_cy = 240, 168
    else:
        text_h = 66
        sp_max_w, sp_max_h = 336, STAMP_H - text_h - 16
        sp_cx, sp_cy = STAMP_W // 2, text_h + (STAMP_H - text_h) // 2 - 4

    s = min(sp_max_w / toon.width, sp_max_h / toon.height)
    sp = toon.resize((int(toon.width * s), int(toon.height * s)), Image.LANCZOS)
    cv.alpha_composite(sp, (sp_cx - sp.width // 2, sp_cy - sp.height // 2))

    if st.get("zzz"):
        f = ImageFont.truetype(FONT, 44)
        for i, (zx, zy, zs) in enumerate(((300, 96, 46), (330, 62, 34), (350, 36, 26))):
            fz = ImageFont.truetype(FONT, zs)
            d.text((zx, zy), "z", font=fz, anchor="mm",
                   fill=(120, 95, 190), stroke_width=6, stroke_fill=(255, 255, 255))
    if st.get("hearts"):
        for hx, hy, hs in ((46, 120, 34), (330, 100, 40), (60, 230, 26), (320, 220, 30)):
            heart(d, hx, hy, hs, (250, 140, 170, 235))
    if st.get("sun"):
        sx, sy = 48, 82
        d.ellipse((sx - 22, sy - 22, sx + 22, sy + 22), fill=(255, 205, 90, 245))
        for ang in range(0, 360, 45):
            a = math.radians(ang)
            d.line((sx + 28 * math.cos(a), sy + 28 * math.sin(a),
                    sx + 40 * math.cos(a), sy + 40 * math.sin(a)),
                   fill=(255, 205, 90, 245), width=6)

    if st["pos"] == "left-v":
        draw_vtext(d, 64, 34, st["text"], 40, st["color"])
    else:
        draw_text(d, (STAMP_W / 2, 38), st["text"], 52, st["color"])
    return cv


def main():
    previews = []
    for st in STAMPS:
        raw = Image.open(os.path.join(SPRITES, st["sprite"] + ".png"))
        toon = add_outline(cartoonify(raw))
        img = compose(st, toon)
        img.save(os.path.join(OUT, st["name"] + ".png"))
        previews.append(img)
        print(st["name"], "done")

    # main.png (240x240) と tab.png (96x74)
    toon = add_outline(cartoonify(Image.open(os.path.join(SPRITES, "bowl.png"))))
    m = Image.new("RGBA", (240, 240), (0, 0, 0, 0))
    s = min(220 / toon.width, 220 / toon.height)
    sp = toon.resize((int(toon.width * s), int(toon.height * s)), Image.LANCZOS)
    m.alpha_composite(sp, ((240 - sp.width) // 2, (240 - sp.height) // 2))
    m.save(os.path.join(OUT, "main.png"))
    tb = Image.new("RGBA", (96, 74), (0, 0, 0, 0))
    paw(ImageDraw.Draw(tb), 48, 34, 17, (235, 140, 90, 255))
    tb.save(os.path.join(OUT, "tab.png"))

    # プレビューシート (市松背景)
    cols, cell_w, cell_h = 4, STAMP_W + 20, STAMP_H + 20
    rows = (len(previews) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell_w, rows * cell_h), (245, 245, 245))
    for y in range(0, sheet.height, 26):
        for x in range(0, sheet.width, 26):
            if (x // 26 + y // 26) % 2:
                sheet.paste((228, 228, 228), (x, y, min(x + 26, sheet.width),
                                              min(y + 26, sheet.height)))
    for i, p in enumerate(previews):
        sheet.paste(p, ((i % cols) * cell_w + 10, (i // cols) * cell_h + 10), p)
    sheet.save(os.path.join(HERE, "stamps_preview.png"))
    print("preview saved")


if __name__ == "__main__":
    main()
