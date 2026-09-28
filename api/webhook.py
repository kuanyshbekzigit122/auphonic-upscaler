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

_processed_updates = set()
_running_jobs = set()

def get_webapp_url(request: Request) -> str:
    url = f"https://{VERCEL_URL}" if not VERCEL_URL.startswith("http") else VERCEL_URL
    req_host = request.headers.get("x-forwarded-host") or request.headers.get("host")
    if req_host:
        url = f"https://{req_host}"
    return url

# ================= MINIMALIST UI SCREENS =================

def get_main_screen(first_name: str, webapp_url: str):
    name_str = f", {first_name}" if first_name else ""
    text = (
        f"<b>Auphonic - AI Upscaler Pro</b>\n\n"
        f"Сәлем{name_str}! Мен суреттер мен бейнелердің сапасын AI арқылы жақсартамын.\n\n"
        f"<blockquote>📷 <b>Сурет жіберіңіз</b> — 2× немесе 4× үлкейтемін\n"
        f"🎥 <b>Бейне жіберіңіз</b> — кадр бойынша өңдеп беремін</blockquote>"
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
    return text, keyboard

def get_help_screen(webapp_url: str):
    text = (
        "<b>Auphonic - AI Upscaler Pro</b>\n\n"
        "💡 <b>Қалай қолдану керек:</b>\n\n"
        "<blockquote>1. Маған кез келген сурет немесе қысқа бейне жіберіңіз.\n"
        "2. Сапасын (2× немесе 4×) және түрін таңдаңыз.\n"
        "3. «Өңдеуді бастау» батырмасын басыңыз.\n"
        "4. Нәтиже дайын болғанда бірден жүктеп алыңыз.\n\n"
        "⚙️ <b>Шектеулер:</b>\n"
        "• Сурет көлемі: 20 МБ дейін\n"
        "• Бейне ұзақтығы: 60 секундқа дейін\n"
        "• Форматтар: JPG, PNG, WEBP, MP4, MOV</blockquote>"
    )
    keyboard = {
        "inline_keyboard": [
            [
                {"text": "🚀 Жұмысты бастау", "callback_data": "nav:work"},
                {"text": "⬅️ Артқа", "callback_data": "nav:main"}
            ]
        ]
    }
    return text, keyboard

def get_work_screen(webapp_url: str):
    text = (
        "<b>Auphonic - AI Upscaler Pro</b>\n\n"
        "🚀 <b>Сапаны арттыруға дайынсыз ба?</b>\n\n"
        "<blockquote>📷 <b>Суретті</b> (JPG, PNG, WEBP) немесе 🎥 <b>бейнені</b> (MP4, MOV) осы чатқа тікелей жіберіңіз!\n\n"
        "Файлды қабылдаған бойда бот сапаны <b>2×</b> немесе <b>4×</b> есе көтеру баптауларын ұсынады.</blockquote>"
    )
    keyboard = {
        "inline_keyboard": [
            [{"text": "📱 Mini App ашу", "web_app": {"url": webapp_url}}],
            [{"text": "⬅️ Артқа", "callback_data": "nav:main"}]
        ]
    }
    return text, keyboard

# ================= INLINE WIZARD SCREENS =================

def get_wizard_step1(file_id: str):
    text = (
        "<b>Auphonic - AI Upscaler Pro</b>\n"
        "Қадам 1 / 2\n\n"
        "<b>Суретті қанша есе үлкейткіңіз келеді?</b>\n"
        "Масштаб пен сапаны таңдаңыз:"
    )
    keyboard = {
        "inline_keyboard": [
            [
                {"text": "✨ 2× Үлкейту", "callback_data": f"w:s1:2:{file_id}"},
                {"text": "🚀 4× Ультра", "callback_data": f"w:s1:4:{file_id}"}
            ]
        ]
    }
    return text, keyboard

def get_wizard_step2(scale: str, file_id: str):
    text = (
        "<b>Auphonic - AI Upscaler Pro</b>\n"
        "Қадам 2 / 2\n\n"
        "<b>Суреттің түрі қандай?</b>\n"
        f"Таңдалған: <b>{scale}× масштаб</b>\n\n"
        "AI сурет түріне қарай бейімделеді:"
    )
    keyboard = {
        "inline_keyboard": [
            [
                {"text": "📸 Фотосурет", "callback_data": f"w:s2:{scale}:photo:{file_id}"},
                {"text": "🎨 Арт / Аниме", "callback_data": f"w:s2:{scale}:anime:{file_id}"}
            ],
            [
                {"text": "⬅️ Артқа", "callback_data": f"w:back:1:{file_id}"}
            ]
        ]
    }
    return text, keyboard

def get_wizard_confirm(scale: str, mode: str, file_id: str):
    mode_label = "Фотосурет" if mode == "photo" else "Арт / Аниме"
    text = (
        "<b>Auphonic - AI Upscaler Pro</b>\n"
        "Барлығы дайын! ✨\n\n"
        "<b>Өңдеуді бастаймыз ба?</b>\n"
        f"Таңдалған: <b>{scale}×</b> • <b>{mode_label}</b>\n\n"
        "AI сапаны арттыруға толық дайын."
    )
    keyboard = {
        "inline_keyboard": [
            [{"text": "🚀 Өңдеуді бастау", "callback_data": f"w:run:{scale}:{mode}:{file_id}"}],
            [{"text": "⬅️ Артқа", "callback_data": f"w:back:2:{scale}:{file_id}"}]
        ]
    }
    return text, keyboard


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

    update_id = update.get("update_id")
    if update_id:
        if update_id in _processed_updates:
            logger.info("Ignoring duplicate update_id=%s", update_id)
            return {"ok": True}
        _processed_updates.add(update_id)
        if len(_processed_updates) > 5000:
            _processed_updates.clear()

    base_tg_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
    webapp_url = get_webapp_url(request)

    # ------------------ CALLBACK QUERIES (In-Place Edit) ------------------
    if "callback_query" in update:
        cq = update["callback_query"]
        cq_id = cq.get("id")
        msg = cq.get("message", {})
        chat_id = msg.get("chat", {}).get("id")
        message_id = msg.get("message_id")
        data = cq.get("data", "")
        from_user = cq.get("from", {})
        first_name = from_user.get("first_name", "")

        requests.post(f"{base_tg_url}/answerCallbackQuery", json={"callback_query_id": cq_id}, timeout=5)

        # 1. Navigation callbacks (main, help, work) -> EDIT IN-PLACE
        if data == "nav:help":
            text, kb = get_help_screen(webapp_url)
            requests.post(f"{base_tg_url}/editMessageText", json={
                "chat_id": chat_id,
                "message_id": message_id,
                "text": text,
                "parse_mode": "HTML",
                "reply_markup": kb
            }, timeout=10)

        elif data == "nav:work":
            text, kb = get_work_screen(webapp_url)
            requests.post(f"{base_tg_url}/editMessageText", json={
                "chat_id": chat_id,
                "message_id": message_id,
                "text": text,
                "parse_mode": "HTML",
                "reply_markup": kb
            }, timeout=10)

        elif data == "nav:main":
            text, kb = get_main_screen(first_name, webapp_url)
            requests.post(f"{base_tg_url}/editMessageText", json={
                "chat_id": chat_id,
                "message_id": message_id,
                "text": text,
                "parse_mode": "HTML",
                "reply_markup": kb
            }, timeout=10)

        # 2. Wizard callbacks -> EDIT IN-PLACE
        elif data.startswith("w:s1:"):
            # w:s1:scale:file_id
            parts = data.split(":")
            scale = parts[2]
            file_id = parts[3]
            text, kb = get_wizard_step2(scale, file_id)
            requests.post(f"{base_tg_url}/editMessageText", json={
                "chat_id": chat_id,
                "message_id": message_id,
                "text": text,
                "parse_mode": "HTML",
                "reply_markup": kb
            }, timeout=10)

        elif data.startswith("w:s2:"):
            # w:s2:scale:mode:file_id
            parts = data.split(":")
            scale = parts[2]
            mode = parts[3]
            file_id = parts[4]
            text, kb = get_wizard_confirm(scale, mode, file_id)
            requests.post(f"{base_tg_url}/editMessageText", json={
                "chat_id": chat_id,
                "message_id": message_id,
                "text": text,
                "parse_mode": "HTML",
                "reply_markup": kb
            }, timeout=10)

        elif data.startswith("w:back:1:"):
            parts = data.split(":")
            file_id = parts[3]
            text, kb = get_wizard_step1(file_id)
            requests.post(f"{base_tg_url}/editMessageText", json={
                "chat_id": chat_id,
                "message_id": message_id,
                "text": text,
                "parse_mode": "HTML",
                "reply_markup": kb
            }, timeout=10)

        elif data.startswith("w:back:2:"):
            parts = data.split(":")
            scale = parts[3]
            file_id = parts[4]
            text, kb = get_wizard_step2(scale, file_id)
            requests.post(f"{base_tg_url}/editMessageText", json={
                "chat_id": chat_id,
                "message_id": message_id,
                "text": text,
                "parse_mode": "HTML",
                "reply_markup": kb
            }, timeout=10)

        elif data.startswith("w:run:"):
            # w:run:scale:mode:file_id
            parts = data.split(":")
            scale_val = int(parts[2]) if parts[2].isdigit() else 4
            file_id = parts[4]

            # Prevent Telegram retry duplicate executions
            job_key = f"{chat_id}:{message_id}:{file_id}"
            if job_key in _running_jobs:
                logger.info("Job %s is already running/finished. Skipping duplicate.", job_key)
                return {"ok": True}
            _running_jobs.add(job_key)
            if len(_running_jobs) > 1000:
                _running_jobs.clear()

            # Edit to live processing status AND remove keyboard to prevent double clicks
            requests.post(f"{base_tg_url}/editMessageText", json={
                "chat_id": chat_id,
                "message_id": message_id,
                "text": "⏳ <b>AI 4K Real-ESRGAN арқылы өңдеуде...</b>",
                "parse_mode": "HTML",
                "reply_markup": {"inline_keyboard": []}
            }, timeout=5)

            # Run upscale
            try:
                file_info = requests.get(f"{base_tg_url}/getFile?file_id={file_id}", timeout=10).json()
                if not file_info.get("ok"):
                    raise RuntimeError(file_info.get("description", "Telegram getFile error"))

                file_path = file_info["result"]["file_path"]
                download_url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}"
                img_data = requests.get(download_url, timeout=30).content

                pil_img = Image.open(io.BytesIO(img_data))
                orig_w, orig_h = pil_img.size

                t0 = time.time()
                up_img = upscale_image(pil_img, scale=scale_val)
                elapsed = round(time.time() - t0, 2)

                buf = io.BytesIO()
                # Fast PNG encode (compress_level=1 is 30x faster than optimize=True, avoiding webhook timeout)
                up_img.save(buf, format="PNG", compress_level=1)
                buf.seek(0)

                # Send lossless uncompressed document
                caption = (
                    f"✨ <b>Дайын!</b> ({elapsed} сек)\n"
                    f"📐 <b>Көлемі:</b> {orig_w}×{orig_h} ➔ <b>{up_img.size[0]}×{up_img.size[1]} px</b>"
                )
                kb = {
                    "inline_keyboard": [
                        [{"text": "📱 Mini App ашу", "web_app": {"url": webapp_url}}]
                    ]
                }
                requests.post(
                    f"{base_tg_url}/sendDocument",
                    data={
                        "chat_id": chat_id,
                        "caption": caption,
                        "parse_mode": "HTML",
                        "reply_markup": str(kb).replace("'", '"')
                    },
                    files={"document": ("auphonic_4k_upscaled.png", buf, "image/png")},
                    timeout=60
                )

                # Remove the processing card
                requests.post(f"{base_tg_url}/deleteMessage", json={
                    "chat_id": chat_id,
                    "message_id": message_id
                }, timeout=10)

            except Exception as exc:
                tb = traceback.format_exc()
                logger.error("Error processing wizard photo: %s\n%s", exc, tb)
                err_report = (
                    f"⚠️ <b>Суретті өңдеу кезінде қате орын алды!</b>\n\n"
                    f"<b>Қате түрі:</b> <code>{type(exc).__name__}</code>\n"
                    f"<b>Себебі:</b> <code>{str(exc)}</code>\n\n"
                    f"<b>Толық лог (traceback):</b>\n<code>{tb[:250]}...</code>"
                )
                requests.post(f"{base_tg_url}/editMessageText", json={
                    "chat_id": chat_id,
                    "message_id": message_id,
                    "text": err_report,
                    "parse_mode": "HTML"
                }, timeout=10)

        return {"ok": True}

    if "message" not in update:
        return {"ok": True}

    msg = update["message"]
    chat_id = msg.get("chat", {}).get("id")
    text = msg.get("text", "")
    from_user = msg.get("from", {})
    first_name = from_user.get("first_name", "")

    if not chat_id:
        return {"ok": True}

    # ------------------ /start COMMAND ------------------
    if text.startswith("/start") or text.startswith("/help"):
        welcome_text, kb = get_main_screen(first_name, webapp_url)
        requests.post(f"{base_tg_url}/sendMessage", json={
            "chat_id": chat_id,
            "text": welcome_text,
            "parse_mode": "HTML",
            "reply_markup": kb
        }, timeout=10)
        return {"ok": True}

    # ------------------ PHOTO UPLOAD (Wizard Launch) ------------------
    file_id = None
    if "photo" in msg and len(msg["photo"]) > 0:
        file_id = msg["photo"][-1]["file_id"]
    elif "document" in msg and msg.get("document", {}).get("mime_type", "").startswith("image/"):
        file_id = msg["document"]["file_id"]

    if file_id:
        photo_key = f"photo:{chat_id}:{file_id}"
        if photo_key in _running_jobs:
            logger.info("Photo %s already received. Skipping duplicate.", photo_key)
            return {"ok": True}
        _running_jobs.add(photo_key)

        w_text, w_kb = get_wizard_step1(file_id)
        requests.post(f"{base_tg_url}/sendMessage", json={
            "chat_id": chat_id,
            "text": w_text,
            "parse_mode": "HTML",
            "reply_markup": w_kb,
            "reply_to_message_id": msg.get("message_id")
        }, timeout=10)

    return {"ok": True}
