import os
import io
import base64
import logging
import traceback
import requests

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("send_to_chat")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8230786310:AAGjsDxHl2H3mXFr66SnZqfRc7yjBwI44QY")

app = FastAPI(title="Auphonic Send to Chat API", redirect_slashes=False)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.api_route("/", methods=["POST", "OPTIONS"])
@app.api_route("/send-to-chat", methods=["POST", "OPTIONS"])
@app.api_route("/api/send-to-chat", methods=["POST", "OPTIONS"])
async def send_to_chat_handler(request: Request):
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
        tb = traceback.format_exc()
        logger.error("Error in send-to-chat: %s\n%s", exc, tb)
        return JSONResponse(status_code=500, content={"success": False, "error": str(exc), "traceback": tb})
