import io
import time
import uuid
import base64
import logging
import traceback
from PIL import Image

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
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
logger = logging.getLogger("upscale_api")

app = FastAPI(title="Auphonic Upscale API", redirect_slashes=False)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.api_route("/", methods=["GET", "POST", "OPTIONS"])
@app.api_route("/upscale", methods=["GET", "POST", "OPTIONS"])
@app.api_route("/api/upscale", methods=["GET", "POST", "OPTIONS"])
async def upscale_handler(
    file: UploadFile = File(None),
    scale: str = Form("4"),
    mode: str = Form("photo")
):
    if file is None:
        return {"status": "ready", "service": "Auphonic Real-ESRGAN Upscaler"}

    try:
        content = await file.read()
        if not content:
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": "Сурет файлы бос немесе жүктелмеді",
                    "error_type": "EmptyFileError",
                    "details": "Uploaded file content is empty (0 bytes)."
                }
            )

        try:
            pil_img = Image.open(io.BytesIO(content))
        except Exception as img_err:
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": f"Суретті оқу мүмкін болмады: {img_err}",
                    "error_type": type(img_err).__name__,
                    "details": "Pillow could not decode this image file format."
                }
            )

        orig_w, orig_h = pil_img.size
        orig_b64 = base64.b64encode(content).decode("utf-8")
        orig_mime = file.content_type or "image/png"
        orig_url = f"data:{orig_mime};base64,{orig_b64}"

        scale_val = 2 if "2" in str(scale) else 4

        t0 = time.time()
        up_img = upscale_image(pil_img, scale=scale_val)
        elapsed = round(time.time() - t0, 2)

        up_w, up_h = up_img.size

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
            "scale": f"{scale_val}x",
            "orig_dimensions": f"{orig_w}×{orig_h}",
            "dimensions": f"{up_w}×{up_h}",
            "elapsed": elapsed
        }

    except Exception as exc:
        tb = traceback.format_exc()
        logger.error("Upscale processing failed: %s\n%s", exc, tb)
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": f"AI өңдеу қатесі: {str(exc)}",
                "error_type": type(exc).__name__,
                "details": str(exc),
                "traceback": tb
            }
        )
