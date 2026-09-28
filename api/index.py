import os
import io
import time
import uuid
import base64
import logging
from pathlib import Path
from PIL import Image
import numpy as np
import onnxruntime as ort
import requests

from fastapi import FastAPI, UploadFile, File, Form, Request, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("vercel_app")

# Environment variables
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8230786310:AAGjsDxHl2H3mXFr66SnZqfRc7yjBwI44QY")
VERCEL_URL = os.getenv("VERCEL_PROJECT_PRODUCTION_URL", os.getenv("VERCEL_URL", ""))

app = FastAPI(title="Auphonic AI Upscaler - Vercel Serverless Edition")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------- Real-ESRGAN Engine -----------------
BASE_DIR = Path(__file__).resolve().parent.parent
MODEL_PATH = BASE_DIR / "models" / "real_esrgan_general_x4v3.onnx"

# Configure ONNX session for high-speed multi-core CPU
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
        _sess = ort.InferenceSession(str(MODEL_PATH), sess_options, providers=["CPUExecutionProvider"])
        _inp_name = _sess.get_inputs()[0].name
        _out_name = _sess.get_outputs()[0].name
    return _sess, _inp_name, _out_name

# Precompute 512x512 smooth 2D ramp blending weights
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


# ----------------- Web Endpoints -----------------
@app.get("/api/health")
async def health():
    return {
        "status": "online",
        "engine": "Real-ESRGAN v3 Fast",
        "platform": "Vercel Serverless"
    }

@app.post("/api/webhook")
async def telegram_webhook(request: Request):
    """
    Serverless Telegram Bot Webhook.
    Handles /start, commands, inline buttons, and direct photo uploads.
    """
    try:
        update = await request.json()
    except Exception:
        return {"ok": True}

    base_tg_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

    # Determine Mini App WebApp URL
    webapp_url = f"https://{VERCEL_URL}" if VERCEL_URL else "https://vercel.com"
    req_host = request.headers.get("x-forwarded-host") or request.headers.get("host")
    if req_host:
        webapp_url = f"https://{req_host}"

    # Handle Callback Queries (Inline button clicks)
    if "callback_query" in update:
        cq = update["callback_query"]
        cq_id = cq.get("id")
        chat_id = cq.get("message", {}).get("chat", {}).get("id")
        data = cq.get("data", "")

        requests.post(f"{base_tg_url}/answerCallbackQuery", json={"callback_query_id": cq_id}, timeout=5)

        if data == "nav:help":
            help_text = (
                "<b>Auphonic - AI Upscaler Pro</b>\n\n"
                "💡 <b>Қалай қолдану керек:</b>\n\n"
                "1. Маған кез келген суретті осы чатқа тікелей жіберіңіз.\n"
                "2. Бот оны автоматты түрде қабылдап, 4K сапада өңдеп береді.\n"
                "3. Немесе заманауи интерактивті <b>Mini App</b>-ты қолданыңыз!\n\n"
                "⚙️ <b>Шектеулер:</b>\n"
                "• Сурет көлемі: 20 МБ дейін\n"
                "• Форматтар: JPG, PNG, WEBP\n"
                "• 100% Тегін және шектеусіз"
            )
            keyboard = {
                "inline_keyboard": [
                    [{"text": "📱 Mini App ашу", "web_app": {"url": webapp_url}}],
                    [{"text": "⬅️ Артқа", "callback_data": "nav:main"}]
                ]
            }
            requests.post(f"{base_tg_url}/sendMessage", json={
                "chat_id": chat_id,
                "text": help_text,
                "parse_mode": "HTML",
                "reply_markup": keyboard
            }, timeout=10)

        elif data in ("nav:work", "nav:main"):
            welcome_text = (
                "✨ <b>Auphonic - AI Upscaler Pro</b> ботына қош келдіңіз!\n\n"
                "Мен суреттердің сапасын жасанды интеллект (<b>Real-ESRGAN 4K</b>) арқылы жоғары деңгейге көтеремін.\n\n"
                "📷 <b>Сурет жіберіңіз</b> (JPG, PNG, WEBP) — осы чатқа тікелей жіберсеңіз, сапасын 4K-ға дейін арттырамын.\n\n"
                "<i>Төмендегі батырмалар арқылы қажетті бөлімді таңдаңыз:</i>"
            )
            keyboard = {
                "inline_keyboard": [
                    [{"text": "📱 Mini App ашу", "web_app": {"url": webapp_url}}],
                    [
                        {"text": "🚀 Жұмысты бастау", "callback_data": "nav:work"},
                        {"text": "💡 Анықтама", "callback_data": "nav:help"}
                    ]
                ]
            }
            requests.post(f"{base_tg_url}/sendMessage", json={
                "chat_id": chat_id,
                "text": welcome_text,
                "parse_mode": "HTML",
                "reply_markup": keyboard
            }, timeout=10)

        return {"ok": True}

    if "message" not in update:
        return {"ok": True}

    msg = update["message"]
    chat_id = msg.get("chat", {}).get("id")
    text = msg.get("text", "")

    # Handle /start or /help commands
    if text.startswith("/start"):
        user_first = msg.get("from", {}).get("first_name", "")
        first_name_str = f", {user_first}" if user_first else ""
        welcome_text = (
            f"✨ <b>Сәлем{first_name_str}!</b>\n\n"
            f"<b>Auphonic - AI Upscaler Pro</b> ботына қош келдіңіз!\n"
            f"Мен суреттердің сапасын жасанды интеллект (<b>Real-ESRGAN 4K</b>) арқылы жоғары деңгейге көтеремін.\n\n"
            f"📷 <b>Сурет жіберіңіз</b> (JPG, PNG, WEBP) — осы чатқа жіберсеңіз, сапасын 4K-ға дейін арттырамын.\n\n"
            f"<i>Төмендегі батырмалар арқылы қажетті бөлімді таңдаңыз:</i>"
        )
        keyboard = {
            "inline_keyboard": [
                [
                    {
                        "text": "📱 Mini App ашу",
                        "web_app": {"url": webapp_url}
                    }
                ],
                [
                    {"text": "🚀 Жұмысты бастау", "callback_data": "nav:work"},
                    {"text": "💡 Анықтама", "callback_data": "nav:help"}
                ]
            ]
        }
        requests.post(
            f"{base_tg_url}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": welcome_text,
                "parse_mode": "HTML",
                "reply_markup": keyboard
            },
            timeout=10
        )
        return {"ok": True}

    # Handle direct photo upload to Telegram chat
    if "photo" in msg:
        photos = msg["photo"]
        best_photo = photos[-1]
        file_id = best_photo["file_id"]

        proc_res = requests.post(
            f"{base_tg_url}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": "⚡ <b>Real-ESRGAN AI</b> суретті 4K сапаға көтеруде...",
                "parse_mode": "HTML"
            },
            timeout=10
        ).json()
        proc_msg_id = proc_res.get("result", {}).get("message_id")

        try:
            # 1. Download photo from Telegram
            file_info = requests.get(f"{base_tg_url}/getFile?file_id={file_id}", timeout=10).json()
            file_path = file_info["result"]["file_path"]
            img_bytes = requests.get(f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}", timeout=30).content

            # 2. Run high-speed Real-ESRGAN upscale
            pil_img = Image.open(io.BytesIO(img_bytes))
            t0 = time.time()
            up_img = upscale_image(pil_img, scale=4)
            elapsed = round(time.time() - t0, 1)

            # 3. Save to PNG buffer
            buf = io.BytesIO()
            up_img.save(buf, format="PNG", optimize=True)
            buf.seek(0)

            # 4. Send back to user as document (lossless quality)
            requests.post(
                f"{base_tg_url}/sendDocument",
                data={
                    "chat_id": chat_id,
                    "caption": f"✨ <b>4K Real-ESRGAN</b> сапасы сәтті арттырылды! ({elapsed} сек)\n{up_img.size[0]}×{up_img.size[1]} px",
                    "parse_mode": "HTML"
                },
                files={"document": ("auphonic_4k_upscaled.png", buf, "image/png")},
                timeout=60
            )

            # Delete progress notification
            if proc_msg_id:
                requests.post(f"{base_tg_url}/deleteMessage", json={"chat_id": chat_id, "message_id": proc_msg_id}, timeout=10)

        except Exception as exc:
            logger.error("Error processing photo webhook: %s", exc)
            requests.post(
                f"{base_tg_url}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": f"⚠️ Суретті өңдеу кезінде қате орын алды: {exc}"
                },
                timeout=10
            )

        return {"ok": True}

    return {"ok": True}


@app.post("/api/upscale")
async def upscale_api(
    file: UploadFile = File(...),
    scale: str = Form("4"),
    mode: str = Form("photo")
):
    """
    Mini App API endpoint: Receives image, runs fast Real-ESRGAN on CPU,
    and returns 4K result as base64 data URI.
    """
    try:
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="Сурет файлы табылмады")

        pil_img = Image.open(io.BytesIO(content))
        orig_w, orig_h = pil_img.size

        # Original as data URI
        orig_b64 = base64.b64encode(content).decode("utf-8")
        orig_mime = file.content_type or "image/png"
        orig_url = f"data:{orig_mime};base64,{orig_b64}"

        scale_val = 2 if "2" in str(scale) else 4

        t0 = time.time()
        up_img = upscale_image(pil_img, scale=scale_val)
        elapsed = time.time() - t0

        up_w, up_h = up_img.size

        # Result as data URI
        buf = io.BytesIO()
        up_img.save(buf, format="PNG", optimize=True)
        out_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        result_url = f"data:image/png;base64,{out_b64}"

        job_id = uuid.uuid4().hex[:12]
        return {
            "success": True,
            "job_id": job_id,
            "orig_url": orig_url,
            "result_url": result_url,
            "download_url": result_url,
            "orig_dimensions": f"{orig_w}×{orig_h} px",
            "dimensions": f"{up_w}×{up_h} px",
            "scale": scale_val,
            "mode": mode,
            "elapsed": round(elapsed, 2)
        }

    except Exception as exc:
        logger.error("Error in /api/upscale: %s", exc, exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": f"AI өңдеу қатесі: {str(exc)}"}
        )


@app.post("/api/send-to-chat")
async def send_to_chat(request: Request):
    """
    Sends the upscaled photo from Mini App directly into the Telegram user's private chat.
    """
    try:
        body = await request.json()
        user_id = body.get("user_id")
        result_url = body.get("result_url", "")

        if not user_id:
            return JSONResponse(status_code=400, content={"success": False, "error": "user_id табылмады."})

        if not result_url or not result_url.startswith("data:image"):
            return JSONResponse(status_code=400, content={"success": False, "error": "Жарамсыз сурет дерегі."})

        header, b64_data = result_url.split(",", 1)
        img_bytes = base64.b64decode(b64_data)

        base_tg_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
        resp = requests.post(
            f"{base_tg_url}/sendDocument",
            data={
                "chat_id": user_id,
                "caption": "✨ <b>Auphonic AI</b> — 4K сападағы суретіңіз дайын!",
                "parse_mode": "HTML"
            },
            files={"document": ("auphonic_4k_upscaled.png", io.BytesIO(img_bytes), "image/png")},
            timeout=30
        )
        data = resp.json()
        if data.get("ok"):
            return {"success": True}
        else:
            return JSONResponse(status_code=400, content={"success": False, "error": data.get("description", "Telegram қатесі")})

    except Exception as exc:
        logger.error("Error in /api/send-to-chat: %s", exc)
        return JSONResponse(status_code=500, content={"success": False, "error": str(exc)})
