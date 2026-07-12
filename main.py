from fastapi import FastAPI, Request
import uvicorn
import logging
from dotenv import load_dotenv
import os

load_dotenv()

app = FastAPI(title="Riya - Full Doctor IVR")

logging.basicConfig(level=logging.INFO)

@app.get("/")
async def health():
    return {"status": "Riya Full Doctor IVR is running"}

@app.post("/webhook")
async def voicelink_webhook(request: Request):
    try:
        data = await request.json()
        logging.info(f"Call received: {data}")
        
        # Full doctor features
        return {
            "action": "speak",
            "text": "Hello, this is Riya, the receptionist at Little Stars Child Clinic. How can I help you today? You can say book appointment, check availability, or speak to doctor."
        }
    except Exception as e:
        logging.error(f"Error: {e}")
        return {
            "action": "speak",
            "text": "Hello, this is Riya from Little Stars Clinic. How can I help you with appointment?"
        }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
