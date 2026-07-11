#!/usr/bin/env python3
"""LINEスタンプ用: 新しい写真5枚から猫(＋小物)を切り抜く。

複数クリック点の magic_touch マスクと deeplab の cat クラスを合成して
pymatting で仕上げる。
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

# name: (photo, crop box, click points(crop座標), catクラスを使うか, 閾値)
TARGETS = {
    "bowl":    ("n1_bowl.jpg",   (0.00, 0.08, 1.00, 0.70),
                [(0.50, 0.44), (0.50, 0.71), (0.15, 0.60), (0.85, 0.60)], True, 0.5),
    "sleep":   ("n2_sleep.jpg",  (0.02, 0.16, 0.92, 0.82),
                [(0.48, 0.52)], True, 0.5),
    "boxcurl": ("n3_box.jpg",    (0.05, 0.38, 0.82, 0.80),
                [(0.48, 0.45)], True, 0.5),
    "upside":  ("n4_upside.jpg", (0.00, 0.00, 0.97, 0.62),
                [(0.21, 0.48), (0.62, 0.56)], True, 0.5),
    "perch":   ("n5_perch.jpg",  (0.20, 0.04, 0.95, 0.85),
                [(0.47, 0.38)], True, 0.6),
}

inter = vision.InteractiveSegmenter.create_from_options(
    vision.InteractiveSegmenterOptions(
        base_options=mp_python.BaseOptions(
            model_asset_path="/root/.models/magic_touch.tflite"),
        output_confidence_masks=True))
seg = vision.ImageSegmenter.create_from_options(
    vision.ImageSegmenterOptions(
        base_options=mp_python.BaseOptions(
            model_asset_path="/root/.models/deeplab_v3.tflite"),
        output_confidence_masks=True))


def extract(name, photo, box, points, use_cat, thr):
    im = ImageOps.exif_transpose(
        Image.open(os.path.join(HERE, "photos", photo))).convert("RGB")
    W, H = im.size
    crop = im.crop((int(box[0] * W), int(box[1] * H),
                    int(box[2] * W), int(box[3] * H)))
    crop.thumbnail((1400, 1400), Image.LANCZOS)
    rgb = np.array(crop)
    mpimg = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

    mask = np.zeros(rgb.shape[:2], dtype=np.float32)
    for px, py in points:
        roi = vision.InteractiveSegmenterRegionOfInterest(
            format=vision.InteractiveSegmenterRegionOfInterest.Format.KEYPOINT,
            keypoint=kp.NormalizedKeypoint(px, py))
        m = np.squeeze(inter.segment(mpimg, roi).confidence_masks[0].numpy_view())
        mask = np.maximum(mask, m)
    if use_cat:
        m = np.squeeze(seg.segment(mpimg).confidence_masks[8].numpy_view())
        mask = np.maximum(mask, m)

    hard = mask > thr
    lab, _ = ndimage.label(hard)
    cy, cx = int(points[0][1] * hard.shape[0]), int(points[0][0] * hard.shape[1])
    target = lab[cy, cx]
    if target == 0:
        sizes = np.bincount(lab.ravel()); sizes[0] = 0
        target = sizes.argmax()
    # クリック点成分 + それと重なる大きめ成分を残す
    keep = lab == target
    keep = ndimage.binary_fill_holes(keep)

    it = 14
    fg = ndimage.binary_erosion(keep, iterations=it)
    while fg.sum() < keep.sum() * 0.2 and it > 2:
        it = max(2, it // 2)
        fg = ndimage.binary_erosion(keep, iterations=it)
    bg = ~ndimage.binary_dilation(keep, iterations=max(it, 6))
    trimap = np.full(keep.shape, 0.5)
    trimap[fg] = 1.0
    trimap[bg] = 0.0
    alpha = np.clip(estimate_alpha_cf(rgb.astype(np.float64) / 255.0, trimap), 0, 1)

    rgba = np.dstack([rgb, (alpha * 255).astype(np.uint8)])
    ys, xs = np.where(alpha > 0.06)
    Image.fromarray(rgba[ys.min():ys.max() + 1, xs.min():xs.max() + 1]).save(
        os.path.join(OUT, f"{name}.png"))
    print(name, "ok")


for name, (photo, box, pts, use_cat, thr) in TARGETS.items():
    extract(name, photo, box, pts, use_cat, thr)
