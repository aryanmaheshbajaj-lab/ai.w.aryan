import os
import logging
from dotenv import load_dotenv
from fastapi import FastAPI, Request
import uvicorn

load_dotenv()

app = FastAPI(title="Riya Simple IVR")

logging.basicConfig(level=logging.INFO)

@app.get("/")
async def health():
    return {"status": "Riya Simple IVR is running on Railway"}

# Voicelink Webhook
@app.post("/webhook")
async def voicelink_webhook(request: Request):
    try:
        data = await request.json()
        logging.info(f"Incoming call data: {data}")
        return {
            "action": "speak",
            "text": "Hello, this is Riya from Little Stars Child Clinic. How can I help you with appointment today?"
        }
    except:
        return {"action": "speak", "text": "Hello, this is Riya. How can I help you?"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
