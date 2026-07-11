#!/usr/bin/env python3
"""うちの猫たちのLINEスタンプ (完全アニメ描き起こし版).

写真を参照に、3匹のちびキャラ(太い輪郭線・フラット塗り・大きな瞳)を
ベクター風に描画する。出力は LINE 規格 (370x320, main 240x240, tab 96x74)。

使い方: python3 make_stamps_anime.py  →  stamps_anime/ + stamps_anime_preview.png
"""
import math
import os

from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "stamps_anime")
os.makedirs(OUT, exist_ok=True)

FONT = "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf"
STAMP_W, STAMP_H = 370, 320
SS = 2                      # スーパーサンプリング倍率
W2, H2 = STAMP_W * SS, STAMP_H * SS

INK = (72, 52, 46, 255)     # 輪郭線
LW = 9                      # 線の太さ (2x)

TORA = dict(body=(247, 168, 92), stripe=(215, 122, 48), belly=(255, 241, 224),
            ear=(255, 176, 168), iris=(186, 118, 38), fluffy=False, blaze=False)
FUWA = dict(body=(246, 226, 194), stripe=(224, 192, 148), belly=(255, 249, 238),
            ear=(255, 188, 186), iris=(196, 134, 52), fluffy=True, blaze=False)
KURO = dict(body=(70, 54, 50), stripe=None, belly=(255, 252, 248),
            ear=(255, 170, 165), iris=(184, 146, 82), fluffy=True, blaze=True)

PINK = (255, 148, 150, 255)
PAD = (255, 170, 172, 255)


# ------------------------------------------------------------ primitives ----
def ell(d, box, fill, outline=INK, w=LW):
    d.ellipse(box, fill=fill, outline=outline, width=w)


def blob_shadow(d, cx, cy, rx):
    d.ellipse((cx - rx, cy - rx * 0.22, cx + rx, cy + rx * 0.22),
              fill=(90, 80, 90, 45))


def capsule(d, x0, y0, x1, y1, r, fill, outline=INK, w=LW):
    d.rounded_rectangle((x0, y0, x1, y1), radius=r, fill=fill,
                        outline=outline, width=w)


# ---------------------------------------------------------------- head ------
def head_layer(r, pal, expr="open", look=(0, 0)):
    """頭のレイヤー (サイズ 4r x 4r、中心 2r,2r) を返す。"""
    size = int(r * 4)
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    cx = cy = size / 2

    # 耳
    for s in (-1, 1):
        pts = [(cx + s * r * 0.88, cy - r * 0.42),
               (cx + s * r * 0.72, cy - r * 1.28),
               (cx + s * r * 0.18, cy - r * 0.86)]
        d.polygon(pts, fill=pal["body"], outline=INK, width=LW)
        ipts = [(cx + s * r * 0.72, cy - r * 0.52),
               (cx + s * r * 0.62, cy - r * 1.05),
               (cx + s * r * 0.28, cy - r * 0.76)]
        d.polygon(ipts, fill=pal["ear"])

    # 顔のふわ毛 (頬のとがり)
    if pal["fluffy"]:
        for s in (-1, 1):
            d.polygon([(cx + s * r * 0.96, cy + r * 0.05),
                       (cx + s * r * 1.28, cy + r * 0.22),
                       (cx + s * r * 0.92, cy + r * 0.38)],
                      fill=pal["body"], outline=INK, width=LW - 3)
            d.polygon([(cx + s * r * 0.94, cy + r * 0.40),
                       (cx + s * r * 1.22, cy + r * 0.60),
                       (cx + s * r * 0.84, cy + r * 0.66)],
                      fill=pal["body"], outline=INK, width=LW - 3)

    # 頭 (少し横長)
    ell(d, (cx - r * 1.04, cy - r * 0.96, cx + r * 1.04, cy + r * 0.96),
        pal["body"])

    # ハチワレ (くろ): 白いブレーズ
    if pal["blaze"]:
        d.polygon([(cx - r * 0.34, cy + r * 0.94), (cx - r * 0.16, cy - r * 0.1),
                   (cx, cy - r * 0.32), (cx + r * 0.16, cy - r * 0.1),
                   (cx + r * 0.34, cy + r * 0.94),
                   (cx, cy + r * 0.96)], fill=pal["belly"])

    # おでこの縞
    if pal["stripe"]:
        for k in (-1, 0, 1):
            x = cx + k * r * 0.30
            d.rounded_rectangle((x - r * 0.055, cy - r * 0.95 + abs(k) * r * 0.06,
                                 x + r * 0.055, cy - r * 0.52),
                                radius=r * 0.05, fill=pal["stripe"])

    # マズル (口周りの白)
    ell(d, (cx - r * 0.46, cy + r * 0.18, cx + r * 0.46, cy + r * 0.78),
        pal["belly"], outline=None, w=0)

    # 目
    ex, ey = r * 0.46, r * 0.02
    lx, ly = look
    if expr == "open":
        for s in (-1, 1):
            x, y = cx + s * ex + lx * r, cy + ey + ly * r
            ew, eh = r * 0.30, r * 0.40
            ell(d, (x - ew, y - eh, x + ew, y + eh), (255, 255, 255, 255),
                outline=INK, w=LW - 2)
            ir = r * 0.23
            d.ellipse((x - ir + lx * 14, y - ir + ly * 14,
                       x + ir + lx * 14, y + ir + ly * 14), fill=pal["iris"])
            pr = r * 0.13
            d.ellipse((x - pr + lx * 18, y - pr + ly * 18,
                       x + pr + lx * 18, y + pr + ly * 18), fill=(40, 28, 26))
            d.ellipse((x - r * 0.13, y - r * 0.20, x + r * 0.01, y - r * 0.06),
                      fill=(255, 255, 255, 240))
            d.ellipse((x + r * 0.04, y + r * 0.05, x + r * 0.11, y + r * 0.12),
                      fill=(255, 255, 255, 200))
    elif expr == "happy":   # ∩ の笑い目
        for s in (-1, 1):
            x = cx + s * ex
            d.arc((x - r * 0.26, cy - r * 0.20, x + r * 0.26, cy + r * 0.24),
                  200, 340, fill=INK, width=LW)
    else:                   # sleep: ︶
        for s in (-1, 1):
            x = cx + s * ex
            d.arc((x - r * 0.26, cy - r * 0.16, x + r * 0.26, cy + r * 0.22),
                  20, 160, fill=INK, width=LW)

    # 鼻・口 (ω)
    ny = cy + r * 0.30
    d.polygon([(cx - r * 0.075, ny), (cx + r * 0.075, ny),
               (cx, ny + r * 0.09)], fill=PINK, outline=INK, width=3)
    mw = r * 0.16
    d.arc((cx - mw, ny + r * 0.02, cx, ny + r * 0.26), 0, 180, fill=INK, width=LW - 3)
    d.arc((cx, ny + r * 0.02, cx + mw, ny + r * 0.26), 0, 180, fill=INK, width=LW - 3)

    # ほっぺ
    blush = (255, 150, 150, 80)
    for s in (-1, 1):
        d.ellipse((cx + s * r * 0.78 - r * 0.16, cy + r * 0.30 - r * 0.10,
                   cx + s * r * 0.78 + r * 0.16, cy + r * 0.30 + r * 0.10),
                  fill=blush)

    # ひげ
    wc = (250, 250, 250, 230) if pal["blaze"] else (140, 108, 92, 200)
    for s in (-1, 1):
        for k in (-1, 0, 1):
            x0 = cx + s * r * 0.80
            y0 = cy + r * 0.28 + k * r * 0.10
            d.line((x0, y0, x0 + s * r * 0.45, y0 + k * r * 0.14 - r * 0.02),
                   fill=wc, width=4)
    return im


def paste_head(cv, cx, cy, r, pal, expr="open", tilt=0.0, look=(0, 0)):
    h = head_layer(r, pal, expr, look)
    if tilt:
        h = h.rotate(tilt, expand=False, resample=Image.BICUBIC)
    cv.alpha_composite(h, (int(cx - h.width / 2), int(cy - h.height / 2)))


def toe_lines(d, x, y, w, direction=90):
    """足先のスリット。direction=deg (指先が向く方向)"""
    a = math.radians(direction)
    for k in (-1, 1):
        px, py = x + k * w * 0.33, y
        d.line((px, py, px + w * 0.28 * math.cos(a), py + w * 0.28 * math.sin(a)),
               fill=INK, width=LW - 3)


def paw_pads(d, cx, cy, w):
    """肉球 (見せポーズ用)。"""
    d.ellipse((cx - w * 0.30, cy - w * 0.10, cx + w * 0.30, cy + w * 0.42),
              fill=PAD)
    for i, ang in enumerate((-50, 0, 50)):
        a = math.radians(ang - 90)
        px, py = cx + w * 0.42 * math.cos(a), cy + w * 0.05 + w * 0.42 * math.sin(a)
        rr = w * 0.13
        d.ellipse((px - rr, py - rr, px + rr, py + rr), fill=PAD)


def tail(d, pts, color, w=26):
    d.line(pts, fill=INK, width=w + LW * 2, joint="curve")
    d.line(pts, fill=color, width=w, joint="curve")
    # 先端を丸く
    x, y = pts[-1]
    d.ellipse((x - w / 2 - LW, y - w / 2 - LW, x + w / 2 + LW, y + w / 2 + LW),
              fill=INK)
    d.ellipse((x - w / 2, y - w / 2, x + w / 2, y + w / 2), fill=color)


def body_stripes(d, cx, cy, rx, ry, pal, n=3):
    if not pal["stripe"]:
        return
    for k in range(n):
        t = -0.5 + k / (n - 1) if n > 1 else 0
        x = cx + t * rx * 1.1
        d.arc((x - rx * 0.22, cy - ry * 0.95, x + rx * 0.22, cy - ry * 0.1),
              200, 340, fill=pal["stripe"], width=int(LW * 1.4))


# ---------------------------------------------------------------- poses -----
def pose_bowl():
    cv = Image.new("RGBA", (W2, H2), (0, 0, 0, 0))
    d = ImageDraw.Draw(cv)
    blob_shadow(d, 370, 560, 265)
    # 木の鉢
    wood, wood_hi = (232, 195, 122, 255), (243, 214, 152, 255)
    d.rounded_rectangle((130, 300, 610, 560), radius=95, fill=wood,
                        outline=INK, width=LW)
    d.ellipse((150, 268, 590, 372), fill=(206, 206, 200, 255),
              outline=INK, width=LW)   # 内側 (グレー)
    # 前面の肉球焼き印
    for px, py, pr in ((300, 460, 20), (368, 492, 16), (436, 462, 20)):
        pd = ImageDraw.Draw(cv)
        pd.ellipse((px - pr * 0.6, py - pr * 0.3, px + pr * 0.6, py + pr * 0.8),
                   fill=(176, 138, 70, 255))
        for ang in (-45, 0, 45):
            a = math.radians(ang - 90)
            qx, qy = px + pr * 1.05 * math.cos(a), py + pr * 0.15 + pr * 1.05 * math.sin(a)
            pd.ellipse((qx - pr * 0.28, qy - pr * 0.28, qx + pr * 0.28, qy + pr * 0.28),
                       fill=(176, 138, 70, 255))
    # 頭 (縁から見上げ)
    paste_head(cv, 370, 265, 118, TORA, expr="open", look=(0, 0.05))
    # 縁にかけた前足
    d = ImageDraw.Draw(cv)
    for sx in (-1, 1):
        x = 370 + sx * 62
        capsule(d, x - 34, 300, x + 34, 402, 32, TORA["body"])
        toe_lines(d, x, 384, 62, 90)
    return cv


def pose_upside():
    cv = Image.new("RGBA", (W2, H2), (0, 0, 0, 0))
    d = ImageDraw.Draw(cv)
    blob_shadow(d, 380, 585, 255)
    # 仰向けの胴体 (おなか見せ)
    ell(d, (250, 380, 620, 590), TORA["body"])
    ell(d, (300, 415, 570, 575), TORA["belly"], outline=None, w=0)
    body_stripes(d, 500, 470, 110, 90, TORA, 2)
    # しっぽ (くるんと巻く)
    tail(d, [(595, 515), (648, 478), (642, 420), (600, 400)], TORA["stripe"], 24)
    # 上げた前足 x2 (肉球見せ)
    for x, ang in ((440, -8), (525, 8)):
        layer = Image.new("RGBA", (140, 220), (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        capsule(ld, 35, 20, 105, 200, 34, TORA["body"])
        paw_pads(ld, 70, 52, 58)
        layer = layer.rotate(ang, expand=True, resample=Image.BICUBIC)
        cv.alpha_composite(layer, (x - layer.width // 2, 290))
    # 頭 (横倒し気味)
    paste_head(cv, 235, 430, 112, TORA, expr="open", tilt=18, look=(0.03, 0))
    return cv


def pose_boxcurl():
    cv = Image.new("RGBA", (W2, H2), (0, 0, 0, 0))
    d = ImageDraw.Draw(cv)
    # 段ボール箱 (奥板)
    box, box_dark = (221, 184, 134, 255), (198, 160, 110, 255)
    d.polygon([(150, 330), (590, 330), (560, 420), (180, 420)],
              fill=box_dark, outline=INK, width=LW)
    # 丸くなった猫
    ell(d, (215, 300, 525, 560), TORA["body"])
    body_stripes(d, 370, 430, 150, 130, TORA, 3)
    # しっぽを体に巻く
    tail(d, [(255, 500), (330, 545), (430, 540), (490, 505)], TORA["stripe"], 30)
    # 頭 (目を閉じて)
    paste_head(cv, 435, 380, 96, TORA, expr="sleep", tilt=-10)
    # 箱の前板 (猫の下半分を隠す)
    d = ImageDraw.Draw(cv)
    d.rounded_rectangle((150, 470, 590, 620), radius=18, fill=box,
                        outline=INK, width=LW)
    d.line((150, 505, 590, 505), fill=box_dark, width=6)
    return cv


def pose_sleep():
    cv = Image.new("RGBA", (W2, H2), (0, 0, 0, 0))
    d = ImageDraw.Draw(cv)
    blob_shadow(d, 370, 585, 260)
    # ふわふわの胴体
    ell(d, (190, 400, 610, 585), FUWA["body"])
    # 前足をそろえて
    capsule(d, 255, 505, 345, 570, 30, FUWA["belly"])
    capsule(d, 330, 510, 420, 572, 30, FUWA["belly"])
    # しっぽ
    tail(d, [(590, 520), (650, 560), (620, 600)], FUWA["body"], 30)
    # 頭 (すやすや)
    paste_head(cv, 320, 400, 108, FUWA, expr="sleep", tilt=6)
    return cv


def pose_sit(pal, wave=False, expr="open", look=(0, 0)):
    cv = Image.new("RGBA", (W2, H2), (0, 0, 0, 0))
    d = ImageDraw.Draw(cv)
    blob_shadow(d, 370, 600, 210)
    # 座った体 (洋ナシ型)
    d.polygon([(370, 330), (255, 420), (225, 545), (285, 600), (455, 600),
               (515, 545), (485, 420)], fill=pal["body"], outline=INK, width=LW)
    ell(d, (240, 400, 500, 605), pal["body"], outline=None, w=0)
    d = ImageDraw.Draw(cv)
    # 胸の白
    ell(d, (300, 420, 440, 590), pal["belly"], outline=None, w=0)
    body_stripes(d, 370, 500, 120, 100, pal, 2)
    # しっぽ
    tail(d, [(495, 560), (585, 545), (620, 480)], pal["body"], 30)
    # 前足
    capsule(d, 300, 480, 356, 600, 28, pal["body"])
    toe_lines(d, 328, 580, 52, 90)
    if wave:
        layer = Image.new("RGBA", (150, 230), (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        capsule(ld, 40, 20, 110, 210, 35, pal["body"])
        paw_pads(ld, 75, 55, 60)
        layer = layer.rotate(-30, expand=True, resample=Image.BICUBIC)
        cv.alpha_composite(layer, (420, 300))
    else:
        capsule(d, 384, 480, 440, 600, 28, pal["body"])
        toe_lines(d, 412, 580, 52, 90)
    # 頭
    paste_head(cv, 370, 300, 112, pal, expr=expr, look=look)
    return cv


def pose_kuro():
    cv = Image.new("RGBA", (W2, H2), (0, 0, 0, 0))
    d = ImageDraw.Draw(cv)
    blob_shadow(d, 380, 595, 250)
    # 香箱座りの胴体
    ell(d, (215, 400, 610, 590), KURO["body"])
    # 白いおなか/前足
    for x0, x1 in ((255, 350), (360, 455)):
        capsule(d, x0, 505, x1, 585, 34, KURO["belly"])
        toe_lines(d, (x0 + x1) / 2, 566, 60, 90)
    # ふさふさしっぽ (上向きにゆらり)、先だけ白
    tail(d, [(580, 490), (640, 420), (615, 335)], KURO["body"], 40)
    ell(d, (615 - 26, 335 - 26, 615 + 26, 335 + 26), KURO["belly"], w=LW - 2)
    # 頭 (かしげる)
    paste_head(cv, 330, 350, 116, KURO, expr="open", tilt=12, look=(0.02, 0))
    return cv


def pose_duo():
    cv = Image.new("RGBA", (W2, H2), (0, 0, 0, 0))
    d = ImageDraw.Draw(cv)
    blob_shadow(d, 370, 600, 265)
    # ふわの体 (右・後ろ)
    ell(d, (390, 420, 620, 600), FUWA["body"])
    # とらの体 (左・前)
    ell(d, (130, 430, 360, 605), TORA["body"])
    body_stripes(d, 245, 520, 100, 85, TORA, 2)
    # しっぽ (左右にゆれて)
    tail(d, [(165, 530), (112, 475), (132, 412)], TORA["stripe"], 26)
    tail(d, [(590, 520), (645, 462), (622, 400)], FUWA["body"], 28)
    # 頭 (ほっぺすりすり)
    paste_head(cv, 260, 350, 100, TORA, expr="happy", tilt=-10)
    paste_head(cv, 470, 340, 100, FUWA, expr="happy", tilt=10)
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
    d.ellipse((sx - 22, sy - 22, sx + 22, sy + 22), fill=(255, 205, 90, 245),
              outline=(235, 165, 40, 255), width=3)
    for ang in range(0, 360, 45):
        a = math.radians(ang)
        d.line((sx + 28 * math.cos(a), sy + 28 * math.sin(a),
                sx + 40 * math.cos(a), sy + 40 * math.sin(a)),
               fill=(255, 205, 90, 245), width=6)


def zzz(d):
    for zx, zy, zs in ((296, 100, 40), (326, 66, 30), (348, 40, 22)):
        f = ImageFont.truetype(FONT, zs)
        d.text((zx, zy), "z", font=f, anchor="mm", fill=(120, 95, 190),
               stroke_width=6, stroke_fill=(255, 255, 255))


STAMPS = [
    dict(name="01_nani",     pose=pose_bowl,   text="なにしてるの?",
         color=(235, 120, 40)),
    dict(name="02_asobo",    pose=pose_upside, text="あそぼ!",
         color=(240, 95, 135)),
    dict(name="03_sotto",    pose=pose_boxcurl, text="そっとしといて…",
         color=(90, 120, 190)),
    dict(name="04_oyasumi",  pose=pose_sleep,  text="おやすみ",
         color=(120, 95, 190), deco="zzz"),
    dict(name="05_itera",    pose=lambda: pose_sit(FUWA, wave=True, expr="happy"),
         text="いってらっしゃい", color=(70, 150, 120)),
    dict(name="06_ohayo",    pose=lambda: pose_sit(FUWA, wave=False, expr="open"),
         text="おはよう!", color=(235, 160, 40), deco="sun"),
    dict(name="07_yoroshiku", pose=pose_kuro,  text="よろしくね!",
         color=(90, 160, 80)),
    dict(name="08_daisuki",  pose=pose_duo,    text="だいすき♡",
         color=(235, 90, 130), deco="hearts"),
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
        sun(d, 52, 96)
    elif deco == "hearts":
        for hx, hy, hs in ((44, 116, 32), (330, 96, 38), (58, 216, 24),
                           (322, 208, 28)):
            heart(d, hx, hy, hs, (250, 140, 170, 235))
    draw_text(d, (STAMP_W / 2, 36), st["text"], 52, st["color"])
    return cv


def main():
    previews = []
    for st in STAMPS:
        img = render(st)
        img.save(os.path.join(OUT, st["name"] + ".png"))
        previews.append(img)
        print(st["name"], "done")

    # main.png / tab.png
    art = pose_bowl().resize((STAMP_W, STAMP_H), Image.LANCZOS)
    art = white_sticker(art)
    m = Image.new("RGBA", (240, 240), (0, 0, 0, 0))
    s = min(230 / art.width, 230 / art.height)
    sp = art.resize((int(art.width * s), int(art.height * s)), Image.LANCZOS)
    m.alpha_composite(sp, ((240 - sp.width) // 2, (240 - sp.height) // 2))
    m.save(os.path.join(OUT, "main.png"))

    tb = Image.new("RGBA", (96 * SS, 74 * SS), (0, 0, 0, 0))
    hl = head_layer(52, TORA, expr="happy")
    tb.alpha_composite(hl, (96 * SS // 2 - hl.width // 2,
                            74 * SS // 2 - hl.height // 2 + 14))
    tb = tb.resize((96, 74), Image.LANCZOS)
    tb.save(os.path.join(OUT, "tab.png"))

    # プレビュー
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
