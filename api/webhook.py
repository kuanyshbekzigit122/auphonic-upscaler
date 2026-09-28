import os
import io
import time
import logging
import traceback
from PIL import Image
import requests

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

try:
    from api.engine import upscale_image
except ImportError:
    try:
        from engine import upscale_image
    except ImportError:
        from .engine import upscale_image

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("telegram_webhook")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8230786310:AAGjsDxHl2H3mXFr66SnZqfRc7yjBwI44QY")
VERCEL_URL = os.getenv("VERCEL_PROJECT_PRODUCTION_URL", os.getenv("VERCEL_URL", "auphonic-upscaler.vercel.app"))

app = FastAPI(title="Auphonic Telegram Webhook", redirect_slashes=False)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.api_route("/", methods=["GET", "POST", "OPTIONS"])
@app.api_route("/webhook", methods=["GET", "POST", "OPTIONS"])
@app.api_route("/api/webhook", methods=["GET", "POST", "OPTIONS"])
async def telegram_webhook_handler(request: Request):
    if request.method == "GET":
        return {"status": "active", "service": "Telegram Webhook"}

    try:
        update = await request.json()
    except Exception as parse_err:
        logger.error("Failed to parse Telegram update JSON: %s", parse_err)
        return {"ok": True}

    base_tg_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

    webapp_url = f"https://{VERCEL_URL}" if not VERCEL_URL.startswith("http") else VERCEL_URL
    req_host = request.headers.get("x-forwarded-host") or request.headers.get("host")
    if req_host:
        webapp_url = f"https://{req_host}"

    # Handle Callback Queries
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

    if not chat_id:
        return {"ok": True}

    # /start or /help
    if text.startswith("/start") or text.startswith("/help"):
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

    # Direct photo or image document upload
    file_id = None
    if "photo" in msg and len(msg["photo"]) > 0:
        file_id = msg["photo"][-1]["file_id"]
    elif "document" in msg and msg.get("document", {}).get("mime_type", "").startswith("image/"):
        file_id = msg["document"]["file_id"]

    if file_id:
        proc_msg_id = None
        try:
            status_res = requests.post(f"{base_tg_url}/sendMessage", json={
                "chat_id": chat_id,
                "text": "⏳ <b>Сурет қабылданды!</b> AI 4K Real-ESRGAN арқылы сапасын арттыруда...",
                "parse_mode": "HTML"
            }, timeout=10).json()
            proc_msg_id = status_res.get("result", {}).get("message_id")

            file_info = requests.get(f"{base_tg_url}/getFile?file_id={file_id}", timeout=10).json()
            if not file_info.get("ok"):
                raise RuntimeError(f"Telegram getFile error: {file_info.get('description', 'Unknown error')}")

            file_path = file_info["result"]["file_path"]
            download_url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}"
            img_data = requests.get(download_url, timeout=30).content

            pil_img = Image.open(io.BytesIO(img_data))
            orig_w, orig_h = pil_img.size

            t0 = time.time()
            up_img = upscale_image(pil_img, scale=4)
            elapsed = round(time.time() - t0, 2)

            buf = io.BytesIO()
            up_img.save(buf, format="PNG", optimize=True)
            buf.seek(0)

            requests.post(
                f"{base_tg_url}/sendDocument",
                data={
                    "chat_id": chat_id,
                    "caption": f"✨ <b>4K Real-ESRGAN</b> сапасы арттырылды! ({elapsed} сек)\n📐 <b>Көлемі:</b> {orig_w}×{orig_h} ➔ <b>{up_img.size[0]}×{up_img.size[1]} px</b>",
                    "parse_mode": "HTML"
                },
                files={"document": ("auphonic_4k_upscaled.png", buf, "image/png")},
                timeout=60
            )

            if proc_msg_id:
                requests.post(f"{base_tg_url}/deleteMessage", json={"chat_id": chat_id, "message_id": proc_msg_id}, timeout=10)

        except Exception as exc:
            tb = traceback.format_exc()
            logger.error("Error processing photo webhook: %s\n%s", exc, tb)
            err_report = (
                f"⚠️ <b>Суретті өңдеу кезінде қате орын алды!</b>\n\n"
                f"<b>Қате түрі:</b> <code>{type(exc).__name__}</code>\n"
                f"<b>Себебі:</b> <code>{str(exc)}</code>\n\n"
                f"<b>Толық лог (traceback):</b>\n<code>{tb[:300]}...</code>"
            )
            requests.post(
                f"{base_tg_url}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": err_report,
                    "parse_mode": "HTML"
                },
                timeout=10
            )

    return {"ok": True}
