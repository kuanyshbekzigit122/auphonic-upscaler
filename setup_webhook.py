import sys
import requests

TOKEN = "8230786310:AAGjsDxHl2H3mXFr66SnZqfRc7yjBwI44QY"

def setup(vercel_url: str):
    vercel_url = vercel_url.strip().rstrip("/")
    if not vercel_url.startswith("http"):
        vercel_url = f"https://{vercel_url}"
    
    webhook_url = f"{vercel_url}/api/webhook"
    base_tg = f"https://api.telegram.org/bot{TOKEN}"
    
    print(f"1. Setting Telegram Webhook to: {webhook_url} ...")
    res1 = requests.post(f"{base_tg}/setWebhook", json={
        "url": webhook_url,
        "drop_pending_updates": True
    }, timeout=15).json()
    print("setWebhook response:", res1)
    
    print(f"2. Setting Bot Menu Button to Mini App ({vercel_url}) ...")
    res2 = requests.post(f"{base_tg}/setChatMenuButton", json={
        "menu_button": {
            "type": "web_app",
            "text": "🚀 Mini App",
            "web_app": {"url": vercel_url}
        }
    }, timeout=15).json()
    print("setChatMenuButton response:", res2)
    
    print("3. Checking bot information...")
    res3 = requests.get(f"{base_tg}/getMe", timeout=10).json()
    print("Bot info:", res3)
    
    print("\n[SUCCESS] TELEGRAM BOT AND MINI APP SUCCESSFULLY CONNECTED!")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        setup(sys.argv[1])
    else:
        url = input("Vercel сілтемеңізді енгізіңіз (мысалы https://xxx.vercel.app): ")
        setup(url)
