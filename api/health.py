from fastapi import FastAPI

app = FastAPI(title="Auphonic Health API")

@app.api_route("/", methods=["GET", "OPTIONS"])
@app.api_route("/health", methods=["GET", "OPTIONS"])
@app.api_route("/api/health", methods=["GET", "OPTIONS"])
def health_handler():
    return {
        "status": "online",
        "engine": "Real-ESRGAN v3 Fast",
        "platform": "Vercel Serverless"
    }
