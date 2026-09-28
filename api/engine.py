import os
import io
import time
from pathlib import Path
from PIL import Image
import numpy as np
import onnxruntime as ort

BASE_DIR = Path(__file__).resolve().parent.parent
MODEL_PATH = BASE_DIR / "models" / "real_esrgan_general_x4v3.onnx"

sess_options = ort.SessionOptions()
sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
sess_options.execution_mode = ort.ExecutionMode.ORT_PARALLEL
cores = os.cpu_count() or 4
sess_options.intra_op_num_threads = cores

_sess = None
_inp_name = None
_out_name = None

def get_session():
    global _sess, _inp_name, _out_name
    if _sess is None:
        if not MODEL_PATH.exists():
            raise FileNotFoundError(f"Model file not found at: {MODEL_PATH}")
        _sess = ort.InferenceSession(str(MODEL_PATH), sess_options, providers=["CPUExecutionProvider"])
        _inp_name = _sess.get_inputs()[0].name
        _out_name = _sess.get_outputs()[0].name
    return _sess, _inp_name, _out_name

_ramp = np.ones(512, dtype=np.float32)
for t in range(512):
    r = min(t, 64) / 64.0
    n = min(511 - t, 64) / 64.0
    _ramp[t] = min(r, n, 1.0)
_tile_weights = np.outer(_ramp, _ramp).astype(np.float32)

def _get_indices(length: int) -> list[int]:
    if length <= 128:
        return [0]
    idx = []
    r = 0
    while r + 128 < length:
        idx.append(r)
        r += 112
    idx.append(length - 128)
    return sorted(list(set(idx)))

def upscale_image(img: Image.Image, scale: int = 4) -> Image.Image:
    """High-speed 4K Real-ESRGAN super-resolution with smooth 2D tiling (0.6-2.5s)"""
    sess, inp_name, out_name = get_session()

    has_alpha = img.mode in ("RGBA", "LA") or ("transparency" in img.info)
    if has_alpha:
        rgba = img.convert("RGBA")
        rgb = rgba.convert("RGB")
        alpha = rgba.split()[3]
    else:
        rgb = img.convert("RGB")
        alpha = None

    w, h = rgb.size
    pad_w = max(w, 128)
    pad_h = max(h, 128)

    padded = Image.new("RGB", (pad_w, pad_h), (0, 0, 0))
    padded.paste(rgb, (0, 0))

    xs = _get_indices(pad_w)
    ys = _get_indices(pad_h)

    acc = np.zeros((3, pad_h * 4, pad_w * 4), dtype=np.float32)
    wacc = np.zeros((pad_h * 4, pad_w * 4), dtype=np.float32)

    for y in ys:
        for x in xs:
            tile = padded.crop((x, y, x + 128, y + 128))
            arr = np.array(tile, dtype=np.float32) / 255.0
            arr = np.transpose(arr, (2, 0, 1))[np.newaxis, :]
            out = sess.run([out_name], {inp_name: arr})[0][0]
            out = np.clip(out, 0.0, 1.0)

            acc[:, y * 4:y * 4 + 512, x * 4:x * 4 + 512] += out * _tile_weights
            wacc[y * 4:y * 4 + 512, x * 4:x * 4 + 512] += _tile_weights

    res_arr = acc / np.maximum(wacc, 1e-5)
    res_arr = np.clip(res_arr, 0.0, 1.0)
    res_arr = (np.transpose(res_arr, (1, 2, 0)) * 255.0).astype(np.uint8)
    res_img = Image.fromarray(res_arr).crop((0, 0, w * 4, h * 4))

    if scale == 2:
        res_img = res_img.resize((w * 2, h * 2), Image.Resampling.LANCZOS)

    if alpha is not None:
        target_w, target_h = res_img.size
        up_alpha = alpha.resize((target_w, target_h), Image.Resampling.LANCZOS)
        res_img.putalpha(up_alpha)

    return res_img
