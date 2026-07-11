#!/usr/bin/env python3
"""写真から猫を切り抜いて透過PNGスプライトを作る。

MediaPipe InteractiveSegmenter (magic_touch) + ImageSegmenter (deeplab_v3,
PASCAL VOC の cat クラス) で粗マスクを作り、pymatting のクローズドフォーム
マッティングで毛のエッジを仕上げる。
"""
import os

import numpy as np
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision
from mediapipe.tasks.python.components.containers import keypoint as kp
from PIL import Image, ImageOps
from pymatting import estimate_alpha_cf
from scipy import ndimage

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "sprites")
os.makedirs(OUT, exist_ok=True)

DEEPLAB = "/root/.models/deeplab_v3.tflite"
MAGIC = "/root/.models/magic_touch.tflite"
CAT_CLASS = 8  # PASCAL VOC

# name: (photo, crop box in fractions, click point in crop fractions)
SPRITES = {
    "tora":   ("s1_floor.jpg",   (0.00, 0.28, 0.50, 0.90), (0.38, 0.55)),
    "fuwa":   ("s1_floor.jpg",   (0.48, 0.30, 1.00, 0.86), (0.52, 0.55)),
    "duo":    ("s3_hammock.jpg", (0.00, 0.05, 0.98, 0.86), (0.50, 0.55)),
    "kuro":   ("s4_newbie.jpg",  (0.00, 0.00, 0.95, 0.74), (0.55, 0.40)),
    "kurobody": ("s5_relax.jpg", (0.00, 0.10, 0.85, 0.80), (0.55, 0.50)),
}

base_i = mp_python.BaseOptions(model_asset_path=MAGIC)
inter = vision.InteractiveSegmenter.create_from_options(
    vision.InteractiveSegmenterOptions(base_options=base_i,
                                       output_confidence_masks=True))
base_d = mp_python.BaseOptions(model_asset_path=DEEPLAB)
seg = vision.ImageSegmenter.create_from_options(
    vision.ImageSegmenterOptions(base_options=base_d,
                                 output_confidence_masks=True))


def extract(name, photo, box, point):
    im = ImageOps.exif_transpose(
        Image.open(os.path.join(HERE, "photos", photo))).convert("RGB")
    W, H = im.size
    crop = im.crop((int(box[0] * W), int(box[1] * H),
                    int(box[2] * W), int(box[3] * H)))
    # マッティングは重いので長辺1400pxで処理
    crop.thumbnail((1400, 1400), Image.LANCZOS)
    rgb = np.array(crop)
    mpimg = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

    roi = vision.InteractiveSegmenterRegionOfInterest(
        format=vision.InteractiveSegmenterRegionOfInterest.Format.KEYPOINT,
        keypoint=kp.NormalizedKeypoint(point[0], point[1]))
    m_int = np.squeeze(inter.segment(mpimg, roi).confidence_masks[0].numpy_view())
    m_cat = np.squeeze(seg.segment(mpimg).confidence_masks[CAT_CLASS].numpy_view())
    print(f"  {name}: magic={float(m_int.mean()):.3f} cat={float(m_cat.mean()):.3f}")
    mask = np.maximum(m_int, m_cat)

    hard = mask > 0.5
    # クリック点を含む連結成分だけ残す
    lab, _ = ndimage.label(hard)
    cy, cx = int(point[1] * hard.shape[0]), int(point[0] * hard.shape[1])
    target = lab[cy, cx]
    if target == 0:  # クリック点が外れていたら最大成分
        sizes = np.bincount(lab.ravel()); sizes[0] = 0
        target = sizes.argmax()
    hard = lab == target
    hard = ndimage.binary_fill_holes(hard)

    # トライマップ → クローズドフォームマッティング (侵食は面積に応じて調整)
    it = 14
    fg = ndimage.binary_erosion(hard, iterations=it)
    while fg.sum() < hard.sum() * 0.2 and it > 2:
        it = max(2, it // 2)
        fg = ndimage.binary_erosion(hard, iterations=it)
    bg = ~ndimage.binary_dilation(hard, iterations=max(it, 6))
    trimap = np.full(hard.shape, 0.5)
    trimap[fg] = 1.0
    trimap[bg] = 0.0
    alpha = estimate_alpha_cf(rgb.astype(np.float64) / 255.0, trimap)
    alpha = np.clip(alpha, 0, 1)

    rgba = np.dstack([rgb, (alpha * 255).astype(np.uint8)])
    ys, xs = np.where(alpha > 0.04)
    sprite = Image.fromarray(rgba[ys.min():ys.max() + 1,
                                  xs.min():xs.max() + 1])
    sprite.save(os.path.join(OUT, f"{name}.png"))
    print(name, sprite.size)


for name, (photo, box, point) in SPRITES.items():
    extract(name, photo, box, point)
