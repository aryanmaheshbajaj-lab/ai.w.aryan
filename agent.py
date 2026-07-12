import os
import logging
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from livekit.plugins import sarvam  # Keep Sarvam for voice

load_dotenv()

app = FastAPI(title="Riya Simple IVR")

logging.basicConfig(level=logging.INFO)

@app.get("/")
async def health():
    return {"status": "Riya Simple IVR is running"}

# Webhook for Voicelink
@app.post("/webhook")
async def voicelink_webhook(request: Request):
    data = await request.json()
    logging.info(f"Received call: {data}")
    # Here we can trigger Sarvam voice response
    return {"action": "speak", "text": "Hello, this is Riya from Little Stars Clinic. How can I help you today?"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
