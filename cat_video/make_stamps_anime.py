#!/usr/bin/env python3
"""うちの猫たちのLINEスタンプ (かわいいアニメ描き起こし版 v2).

かわいさの設計:
- 低頭身 (顔でか・体ちんまり)、まん丸フェイス
- 大きな瞳を顔の低い位置に。虹彩は縦グラデーション + 大粒ハイライト
- 輪郭線は黒ではなく毛色に合わせたソフトカラー
- もこもこ毛並みは波打つポリゴンシルエットで表現
- 各スタンプに淡いパステルの丸バッジ背景

使い方: python3 make_stamps_anime.py  →  stamps_anime/ + stamps_anime_preview.png
"""
import math
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "stamps_anime")
os.makedirs(OUT, exist_ok=True)

FONT = "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf"
STAMP_W, STAMP_H = 370, 320
SS = 2
W2, H2 = STAMP_W * SS, STAMP_H * SS
LW = 8          # 基本線幅 (2x)
INK = (88, 62, 54, 255)   # 顔パーツ用のソフトインク

TORA = dict(body=(252, 182, 108), shade=(240, 156, 82), stripe=(224, 132, 62),
            belly=(255, 246, 232), outline=(206, 118, 58),
            ear=(255, 186, 178), fluffy=0.0, blaze=False,
            iris_top=(154, 94, 34), iris_bot=(244, 190, 96))
FUWA = dict(body=(250, 234, 208), shade=(240, 218, 184), stripe=(232, 206, 166),
            belly=(255, 252, 244), outline=(202, 164, 118),
            ear=(255, 196, 190), fluffy=0.055, blaze=False,
            iris_top=(160, 104, 40), iris_bot=(248, 202, 108))
KURO = dict(body=(88, 70, 66), shade=(72, 56, 52), stripe=None,
            belly=(255, 252, 248), outline=(52, 40, 36),
            ear=(255, 178, 172), fluffy=0.05, blaze=True,
            iris_top=(158, 120, 52), iris_bot=(240, 202, 116), eye_scale=1.14)

PINK = (255, 150, 152, 255)
PAD = (255, 176, 178, 255)
BLUSH = (255, 158, 158, 105)


# ------------------------------------------------------------ primitives ----
def fluffy_pts(cx, cy, rx, ry, amp=0.0, bumps=14, phase=0.0, n=240):
    """毛並みの波打ちつき楕円ポリゴン。amp=0 でなめらか。"""
    pts = []
    for i in range(n):
        th = 2 * math.pi * i / n
        wob = 1 + amp * abs(math.sin(bumps * th / 2 + phase))
        pts.append((cx + rx * wob * math.cos(th), cy + ry * wob * math.sin(th)))
    return pts


def shape(d, pts, fill, outline=None, w=LW):
    d.polygon(pts, fill=fill, outline=outline, width=w)


def ell(d, box, fill, outline=None, w=LW):
    d.ellipse(box, fill=fill, outline=outline, width=w)


def rr(d, box, radius, fill, outline=None, w=LW):
    d.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=w)


def arc_line(d, cx, cy, r, a0, a1, color, w, n=24):
    pts = [(cx + r * math.cos(math.radians(a0 + (a1 - a0) * i / n)),
            cy + r * math.sin(math.radians(a0 + (a1 - a0) * i / n)))
           for i in range(n + 1)]
    d.line(pts, fill=color, width=w, joint="curve")
    for x, y in (pts[0], pts[-1]):
        d.ellipse((x - w / 2, y - w / 2, x + w / 2, y + w / 2), fill=color)


def bezier(p0, p1, p2, n=20):
    return [((1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t * t * p2[0],
             (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t * t * p2[1])
            for t in (i / n for i in range(n + 1))]


def blob_shadow(d, cx, cy, rx):
    d.ellipse((cx - rx, cy - rx * 0.20, cx + rx, cy + rx * 0.20),
              fill=(120, 100, 120, 38))


def tail(d, pts, color, outline, w=30):
    d.line(pts, fill=outline, width=w + LW * 2, joint="curve")
    for x, y in (pts[0], pts[-1]):
        d.ellipse((x - w / 2 - LW, y - w / 2 - LW, x + w / 2 + LW, y + w / 2 + LW),
                  fill=outline)
    d.line(pts, fill=color, width=w, joint="curve")
    for x, y in (pts[0], pts[-1]):
        d.ellipse((x - w / 2, y - w / 2, x + w / 2, y + w / 2), fill=color)


# ------------------------------------------------------------------ eyes ----
def eye_img(w, h, pal):
    """縦グラデーション虹彩 + 大粒ハイライトの瞳。"""
    top, bot = pal["iris_top"], pal["iris_bot"]
    grad = np.zeros((h, w, 4), np.uint8)
    for y in range(h):
        t = y / max(1, h - 1)
        grad[y, :, 0] = int(top[0] + (bot[0] - top[0]) * t)
        grad[y, :, 1] = int(top[1] + (bot[1] - top[1]) * t)
        grad[y, :, 2] = int(top[2] + (bot[2] - top[2]) * t)
        grad[y, :, 3] = 255
    im = Image.fromarray(grad)
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, w - 1, h - 1), fill=255)
    im.putalpha(mask)
    d = ImageDraw.Draw(im)
    # 瞳孔
    d.ellipse((w * 0.28, h * 0.26, w * 0.72, h * 0.80), fill=(54, 38, 32, 255))
    # 下のうるうる反射
    d.ellipse((w * 0.24, h * 0.62, w * 0.76, h * 0.94),
              fill=(255, 226, 160, 110))
    # 大粒ハイライト
    d.ellipse((w * 0.12, h * 0.08, w * 0.54, h * 0.46), fill=(255, 255, 255, 245))
    d.ellipse((w * 0.60, h * 0.56, w * 0.80, h * 0.74), fill=(255, 255, 255, 215))
    # 輪郭
    d.ellipse((0, 0, w - 1, h - 1), outline=(70, 48, 40, 255),
              width=max(3, w // 14))
    return im


# ------------------------------------------------------------------ head ----
def head_layer(r, pal, expr="open", look=(0.0, 0.0)):
    size = int(r * 4.2)
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    cx = cy = size / 2
    out = pal["outline"]

    # --- 耳 (ベジェで丸みのある三角) ---
    for s in (-1, 1):
        base_in = (cx + s * r * 0.30, cy - r * 0.78)
        base_out = (cx + s * r * 0.94, cy - r * 0.28)
        tip = (cx + s * r * 0.86, cy - r * 1.30)
        pts = bezier(base_in, (cx + s * r * 0.46, cy - r * 1.32), tip) + \
            bezier(tip, (cx + s * r * 1.06, cy - r * 0.86), base_out)
        shape(d, pts, pal["body"], out, LW)
        ipts = bezier((cx + s * r * 0.42, cy - r * 0.74),
                      (cx + s * r * 0.52, cy - r * 1.12),
                      (cx + s * r * 0.76, cy - r * 1.10)) + \
            bezier((cx + s * r * 0.76, cy - r * 1.10),
                   (cx + s * r * 0.88, cy - r * 0.66),
                   (cx + s * r * 0.78, cy - r * 0.46))
        shape(d, ipts, pal["ear"])

    # --- 顔 (まん丸、長毛はもこもこ) ---
    face = fluffy_pts(cx, cy, r * 1.10, r * 1.00, amp=pal["fluffy"], bumps=13,
                      phase=0.6)
    shape(d, face, pal["body"], out, LW)

    # ハチワレの白ブレーズ (なめらかな曲線・あごまで白く)
    if pal["blaze"]:
        left = bezier((cx - r * 0.74, cy + r * 0.90), (cx - r * 0.58, cy + r * 0.02),
                      (cx - r * 0.16, cy - r * 0.14))
        top = bezier((cx - r * 0.16, cy - r * 0.14), (cx, cy - r * 0.28),
                     (cx + r * 0.16, cy - r * 0.14))
        right = bezier((cx + r * 0.16, cy - r * 0.14), (cx + r * 0.58, cy + r * 0.02),
                       (cx + r * 0.74, cy + r * 0.90))
        bottom = bezier((cx + r * 0.74, cy + r * 0.90), (cx, cy + r * 1.30),
                        (cx - r * 0.74, cy + r * 0.90))
        shape(d, left + top + right + bottom, pal["belly"])

    # おでこの縞 (先すぼみの葉っぱ形)
    if pal["stripe"]:
        for k in (-1, 0, 1):
            x = cx + k * r * 0.28
            y0 = cy - r * 0.92 + abs(k) * r * 0.07
            y1 = cy - r * 0.50 + abs(k) * r * 0.04
            shape(d, [(x - r * 0.07, y0), (x + r * 0.07, y0), (x, y1)],
                  pal["stripe"])

    # --- 目 (大きく、低めに) ---
    ex, ey = r * 0.50, cy + r * 0.12
    lx, ly = look
    if expr == "open":
        es = pal.get("eye_scale", 1.0)
        ew, eh = int(r * 0.46 * es), int(r * 0.60 * es)
        e = eye_img(ew, eh, pal)
        for s in (-1, 1):
            im.alpha_composite(e, (int(cx + s * ex - ew / 2 + lx * r),
                                   int(ey - eh / 2 + ly * r)))
    elif expr == "happy":
        for s in (-1, 1):
            arc_line(d, cx + s * ex, ey + r * 0.02, r * 0.22, 195, 345,
                     INK, LW + 1)
    else:  # sleep
        for s in (-1, 1):
            arc_line(d, cx + s * ex, ey - r * 0.04, r * 0.22, 15, 165,
                     INK, LW + 1)

    # --- 鼻・口 ---
    ny = cy + r * 0.44
    d.polygon([(cx - r * 0.065, ny), (cx + r * 0.065, ny), (cx, ny + r * 0.075)],
              fill=PINK)
    arc_line(d, cx - r * 0.085, ny + r * 0.13, r * 0.085, 25, 155, INK, LW - 3)
    arc_line(d, cx + r * 0.085, ny + r * 0.13, r * 0.085, 25, 155, INK, LW - 3)

    # --- ほっぺ (ハチワレは白い部分の上に) ---
    bx = r * 0.52 if pal["blaze"] else r * 0.72
    bc = (255, 152, 152, 150) if pal["blaze"] else BLUSH
    for s in (-1, 1):
        ell(d, (cx + s * bx - r * 0.16, cy + r * 0.44 - r * 0.10,
                cx + s * bx + r * 0.16, cy + r * 0.44 + r * 0.10), bc)

    # --- ひげ (短く控えめ) ---
    wc = (255, 255, 255, 190) if pal["blaze"] else (188, 148, 118, 160)
    wl = r * 0.20 if pal["blaze"] else r * 0.30
    for s in (-1, 1):
        for k in (-1, 1):
            x0 = cx + s * r * 0.94
            y0 = cy + r * 0.34 + k * r * 0.09
            d.line((x0, y0, x0 + s * wl, y0 + k * r * 0.10), fill=wc, width=3)
    return im


def paste_head(cv, cx, cy, r, pal, expr="open", tilt=0.0, look=(0.0, 0.0)):
    h = head_layer(r, pal, expr, look)
    if tilt:
        h = h.rotate(tilt, expand=False, resample=Image.BICUBIC)
    cv.alpha_composite(h, (int(cx - h.width / 2), int(cy - h.height / 2)))


def paw_pads(d, cx, cy, w):
    d.ellipse((cx - w * 0.28, cy - w * 0.06, cx + w * 0.28, cy + w * 0.40),
              fill=PAD)
    for ang in (-48, 0, 48):
        a = math.radians(ang - 90)
        px, py = cx + w * 0.40 * math.cos(a), cy + w * 0.06 + w * 0.40 * math.sin(a)
        rr_ = w * 0.12
        d.ellipse((px - rr_, py - rr_, px + rr_, py + rr_), fill=PAD)


def toe_slits(d, x, y, w, color):
    for k in (-1, 1):
        d.line((x + k * w * 0.18, y, x + k * w * 0.18, y + w * 0.22),
               fill=color, width=LW - 3)


# ------------------------------------------------------------------ badge ---
def badge(d, color, ring, deco=True):
    ell(d, (370 - 258, 372 - 246, 370 + 258, 372 + 246), color)
    if deco:
        for i in range(10):
            a = math.radians(36 * i + 12)
            x = 370 + 236 * math.cos(a)
            y = 372 + 226 * math.sin(a)
            r_ = 7 + (i % 3) * 3
            d.ellipse((x - r_, y - r_, x + r_, y + r_), fill=ring)


# ------------------------------------------------------------------ poses ---
def canvas():
    cv = Image.new("RGBA", (W2, H2), (0, 0, 0, 0))
    return cv, ImageDraw.Draw(cv)


def pose_bowl():
    cv, d = canvas()
    badge(d, (255, 236, 212, 255), (255, 214, 170, 255))
    blob_shadow(d, 370, 580, 240)
    wood = (240, 205, 138, 255)
    wout = (204, 160, 92, 255)
    rr(d, (160, 372, 580, 585), 85, wood, wout, LW)
    ell(d, (185, 338, 555, 425), (218, 214, 206, 255), wout, LW)
    # 肉球焼き印
    for px, py, pr in ((295, 495, 17), (370, 522, 14), (445, 497, 17)):
        d.ellipse((px - pr * 0.62, py - pr * 0.35, px + pr * 0.62, py + pr * 0.78),
                  fill=(196, 152, 88, 255))
        for ang in (-46, 0, 46):
            a = math.radians(ang - 90)
            qx, qy = px + pr * 1.02 * math.cos(a), py + pr * 0.1 + pr * 1.02 * math.sin(a)
            d.ellipse((qx - pr * 0.26, qy - pr * 0.26, qx + pr * 0.26, qy + pr * 0.26),
                      fill=(196, 152, 88, 255))
    paste_head(cv, 370, 292, 122, TORA, expr="open", look=(0, 0.03))
    d = ImageDraw.Draw(cv)
    for sx in (-1, 1):
        x = 370 + sx * 64
        rr(d, (x - 33, 358, x + 33, 452), 33, TORA["body"], TORA["outline"], LW)
        toe_slits(d, x, 428, 62, TORA["outline"])
    return cv


def pose_upside():
    cv, d = canvas()
    badge(d, (255, 228, 236, 255), (255, 198, 214, 255))
    blob_shadow(d, 385, 575, 235)
    # 仰向けボディ
    shape(d, fluffy_pts(430, 480, 185, 105, 0.0), TORA["body"], TORA["outline"], LW)
    ell(d, (330, 415, 545, 545), TORA["belly"])
    # 縞
    for x in (505, 560):
        arc_line(d, x, 500, 52, 240, 300, TORA["stripe"], LW + 2)
    # しっぽ くるん
    tail(d, [(590, 500), (642, 462), (636, 404), (592, 390)], TORA["body"],
         TORA["outline"], 24)
    # 上げた前足 (肉球)
    for x, ang in ((432, -10), (516, 10)):
        layer = Image.new("RGBA", (150, 220), (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        rr(ld, (42, 18, 108, 200), 33, TORA["body"], TORA["outline"], LW)
        paw_pads(ld, 75, 50, 56)
        layer = layer.rotate(ang, expand=True, resample=Image.BICUBIC)
        cv.alpha_composite(layer, (x - layer.width // 2, 300))
    paste_head(cv, 245, 435, 116, TORA, expr="open", tilt=16, look=(0.02, 0))
    return cv


def pose_boxcurl():
    cv, d = canvas()
    badge(d, (224, 236, 252, 255), (196, 216, 244, 255))
    box, box_dark, box_out = (228, 192, 142, 255), (206, 168, 118, 255), (188, 148, 98, 255)
    d.polygon([(185, 350), (555, 350), (532, 430), (208, 430)],
              fill=box_dark, outline=box_out, width=LW)
    # まるまる猫
    shape(d, fluffy_pts(370, 425, 155, 130, 0.0), TORA["body"], TORA["outline"], LW)
    for x in (300, 370, 440):
        arc_line(d, x, 348, 40, 200, 340, TORA["stripe"], LW + 2)
    tail(d, [(255, 480), (330, 520), (430, 515), (478, 486)], TORA["stripe"],
         TORA["outline"], 28)
    paste_head(cv, 435, 385, 98, TORA, expr="sleep", tilt=-8)
    d = ImageDraw.Draw(cv)
    rr(d, (172, 468, 568, 608), 16, box, box_out, LW)
    d.line((172, 502, 568, 502), fill=box_out, width=5)
    return cv


def pose_sleep():
    cv, d = canvas()
    badge(d, (234, 228, 250, 255), (214, 202, 244, 255))
    blob_shadow(d, 375, 580, 240)
    shape(d, fluffy_pts(390, 490, 195, 100, FUWA["fluffy"], 16),
          FUWA["body"], FUWA["outline"], LW)
    # 前足そろえて
    for x0 in (285, 360):
        rr(d, (x0, 512, x0 + 82, 570), 27, FUWA["belly"], FUWA["outline"], LW - 2)
    tail(d, [(558, 515), (600, 536), (622, 566), (610, 590)],
         FUWA["body"], FUWA["outline"], 32)
    paste_head(cv, 315, 408, 114, FUWA, expr="sleep", tilt=5)
    return cv


def pose_sit(pal, wave=False, expr="open", look=(0.0, 0.0)):
    cv, d = canvas()
    if wave:
        badge(d, (222, 244, 232, 255), (192, 228, 208, 255))
    else:
        badge(d, (255, 246, 212, 255), (255, 228, 160, 255))
    blob_shadow(d, 370, 595, 195)
    # ちんまり座り体
    shape(d, fluffy_pts(370, 490, 130, 118, pal["fluffy"], 12),
          pal["body"], pal["outline"], LW)
    ell(d, (312, 440, 428, 592), pal["belly"])
    # 前足
    rr(d, (312, 470, 362, 596), 25, pal["body"], pal["outline"], LW)
    toe_slits(d, 337, 574, 46, pal["outline"])
    if wave:
        layer = Image.new("RGBA", (150, 210), (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        rr(ld, (44, 16, 106, 194), 31, pal["body"], pal["outline"], LW)
        paw_pads(ld, 75, 46, 52)
        layer = layer.rotate(-38, expand=True, resample=Image.BICUBIC)
        cv.alpha_composite(layer, (448, 272))
        d = ImageDraw.Draw(cv)
    else:
        rr(d, (378, 470, 428, 596), 25, pal["body"], pal["outline"], LW)
        toe_slits(d, 403, 574, 46, pal["outline"])
    tail(d, [(485, 555), (562, 540), (596, 478)], pal["body"], pal["outline"], 28)
    paste_head(cv, 370, 302, 124, pal, expr=expr, look=look)
    return cv


def pose_kuro():
    cv, d = canvas()
    badge(d, (226, 242, 224, 255), (198, 228, 196, 255))
    blob_shadow(d, 385, 585, 235)
    shape(d, fluffy_pts(395, 480, 180, 100, KURO["fluffy"], 15),
          KURO["body"], KURO["outline"], LW)
    # 白い前足
    for x0 in (300, 392):
        rr(d, (x0, 505, x0 + 80, 568), 26, KURO["belly"], KURO["outline"], LW - 2)
        toe_slits(d, x0 + 40, 548, 48, (210, 196, 188, 255))
    # しっぽ (先だけ白)
    tail(d, [(560, 480), (628, 420), (606, 344)], KURO["body"], KURO["outline"], 36)
    ell(d, (606 - 24, 344 - 24, 606 + 24, 344 + 24), KURO["belly"],
        KURO["outline"], LW - 2)
    paste_head(cv, 330, 355, 120, KURO, expr="open", tilt=10, look=(0.02, 0))
    return cv


def pose_duo():
    cv, d = canvas()
    badge(d, (255, 226, 232, 255), (252, 198, 210, 255))
    blob_shadow(d, 370, 592, 245)
    # ふわ (右奥)
    shape(d, fluffy_pts(480, 500, 130, 100, FUWA["fluffy"], 12),
          FUWA["body"], FUWA["outline"], LW)
    # とら (左手前)
    shape(d, fluffy_pts(258, 508, 122, 95, 0.0), TORA["body"], TORA["outline"], LW)
    ell(d, (210, 470, 306, 596), TORA["belly"])
    tail(d, [(160, 545), (112, 492), (130, 430)], TORA["stripe"], TORA["outline"], 24)
    tail(d, [(588, 528), (640, 470), (618, 412)], FUWA["body"], FUWA["outline"], 26)
    paste_head(cv, 262, 352, 106, TORA, expr="happy", tilt=-9)
    paste_head(cv, 472, 342, 106, FUWA, expr="happy", tilt=9)
    return cv


# ------------------------------------------------------------- text/deco ----
def draw_text(d, xy, text, size, fill, stroke=(255, 255, 255, 255), sw=9,
              anchor="mm", max_w=340):
    f = ImageFont.truetype(FONT, size)
    while size > 20 and d.textlength(text, font=f) + sw * 2 > max_w:
        size -= 2
        f = ImageFont.truetype(FONT, size)
    d.text(xy, text, font=f, anchor=anchor, fill=stroke,
           stroke_width=sw, stroke_fill=stroke)
    d.text(xy, text, font=f, anchor=anchor, fill=fill)


def heart(d, cx, cy, s, color):
    d.polygon([(cx, cy + s * .45), (cx - s * .48, cy - s * .1),
               (cx, cy - s * .22), (cx + s * .48, cy - s * .1)], fill=color)
    d.ellipse((cx - s * .5, cy - s * .42, cx, cy + s * .08), fill=color)
    d.ellipse((cx, cy - s * .42, cx + s * .5, cy + s * .08), fill=color)


def sun(d, sx, sy):
    d.ellipse((sx - 20, sy - 20, sx + 20, sy + 20), fill=(255, 208, 96, 250),
              outline=(240, 172, 60, 255), width=3)
    for ang in range(0, 360, 45):
        a = math.radians(ang)
        d.line((sx + 26 * math.cos(a), sy + 26 * math.sin(a),
                sx + 37 * math.cos(a), sy + 37 * math.sin(a)),
               fill=(255, 208, 96, 250), width=5)


def zzz(d):
    for zx, zy, zs in ((300, 102, 38), (330, 68, 28), (352, 42, 21)):
        f = ImageFont.truetype(FONT, zs)
        d.text((zx, zy), "z", font=f, anchor="mm", fill=(126, 100, 196),
               stroke_width=6, stroke_fill=(255, 255, 255))


STAMPS = [
    dict(name="01_nani",     pose=pose_bowl,   text="なにしてるの?",
         color=(232, 116, 44)),
    dict(name="02_asobo",    pose=pose_upside, text="あそぼ!",
         color=(238, 92, 132)),
    dict(name="03_sotto",    pose=pose_boxcurl, text="そっとしといて…",
         color=(96, 124, 192)),
    dict(name="04_oyasumi",  pose=pose_sleep,  text="おやすみ",
         color=(124, 98, 194), deco="zzz"),
    dict(name="05_itera",    pose=lambda: pose_sit(FUWA, wave=True, expr="happy"),
         text="いってらっしゃい", color=(66, 148, 116)),
    dict(name="06_ohayo",    pose=lambda: pose_sit(FUWA, wave=False, expr="open",
                                                   look=(0, -0.02)),
         text="おはよう!", color=(230, 156, 36), deco="sun"),
    dict(name="07_yoroshiku", pose=pose_kuro,  text="よろしくね!",
         color=(88, 158, 78)),
    dict(name="08_daisuki",  pose=pose_duo,    text="だいすき♡",
         color=(234, 88, 128), deco="hearts"),
]


def white_sticker(img, width=6):
    a = img.getchannel("A").point(lambda v: 0 if v < 30 else 255)
    grow = a.filter(ImageFilter.MaxFilter(width * 2 + 1))
    grow = grow.filter(ImageFilter.GaussianBlur(1))
    base = Image.new("RGBA", img.size, (0, 0, 0, 0))
    base.paste(Image.new("RGBA", img.size, (255, 255, 255, 255)), (0, 0), grow)
    base.alpha_composite(img)
    return base


def render(st):
    art = st["pose"]().resize((STAMP_W, STAMP_H), Image.LANCZOS)
    art = white_sticker(art)
    cv = Image.new("RGBA", (STAMP_W, STAMP_H), (0, 0, 0, 0))
    cv.alpha_composite(art)
    d = ImageDraw.Draw(cv)
    deco = st.get("deco")
    if deco == "zzz":
        zzz(d)
    elif deco == "sun":
        sun(d, 56, 100)
    elif deco == "hearts":
        for hx, hy, hs in ((46, 122, 30), (326, 100, 36), (60, 218, 22),
                           (320, 212, 26)):
            heart(d, hx, hy, hs, (250, 132, 164, 240))
    draw_text(d, (STAMP_W / 2, 36), st["text"], 52, st["color"])
    return cv


def main():
    previews = []
    for st in STAMPS:
        img = render(st)
        img.save(os.path.join(OUT, st["name"] + ".png"))
        previews.append(img)
        print(st["name"], "done")

    art = pose_bowl().resize((STAMP_W, STAMP_H), Image.LANCZOS)
    art = white_sticker(art)
    m = Image.new("RGBA", (240, 240), (0, 0, 0, 0))
    s = min(235 / art.width, 235 / art.height)
    sp = art.resize((int(art.width * s), int(art.height * s)), Image.LANCZOS)
    m.alpha_composite(sp, ((240 - sp.width) // 2, (240 - sp.height) // 2))
    m.save(os.path.join(OUT, "main.png"))

    tb = Image.new("RGBA", (96 * SS * 2, 74 * SS * 2), (0, 0, 0, 0))
    hl = head_layer(100, TORA, expr="happy")
    tb.alpha_composite(hl, (tb.width // 2 - hl.width // 2,
                            tb.height // 2 - hl.height // 2 + 30))
    tb = tb.resize((96, 74), Image.LANCZOS)
    tb.save(os.path.join(OUT, "tab.png"))

    cols, cw, ch = 4, STAMP_W + 20, STAMP_H + 20
    rows = (len(previews) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cw, rows * ch), (245, 245, 245))
    for y in range(0, sheet.height, 26):
        for x in range(0, sheet.width, 26):
            if (x // 26 + y // 26) % 2:
                sheet.paste((228, 228, 228), (x, y, min(x + 26, sheet.width),
                                              min(y + 26, sheet.height)))
    for i, p in enumerate(previews):
        sheet.paste(p, ((i % cols) * cw + 10, (i // cols) * ch + 10), p)
    sheet.save(os.path.join(HERE, "stamps_anime_preview.png"))
    print("preview saved")


if __name__ == "__main__":
    main()
