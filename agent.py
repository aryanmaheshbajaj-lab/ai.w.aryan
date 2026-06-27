import os
import logging
from dotenv import load_dotenv
from livekit.agents import JobContext, WorkerOptions, cli
from livekit.agents.voice import Agent, AgentSession
from livekit.plugins import sarvam
import requests

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Riya-IVR")

BACKEND_URL = os.getenv("BACKEND_URL")
DOCTOR_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJkb2N0b3JAc2hhcm1hLmNvbSIsInJvbGUiOiJkb2N0b3IiLCJpYXQiOjE3ODI1ODUwODAsImV4cCI6MTc4MjU4Njg4MH0.79pTU4t_yAUwt0Mog4F7IPKd0GZ0qU5dTg2oJ6y7vYE"   # Paste fresh token here

class RiyaReceptionist(Agent):
    def __init__(self):
        super().__init__(
            instructions="""You are Riya, polite AI receptionist for Little Stars Child Clinic.
Follow the full conversation guide exactly.
Speak naturally in Hindi/English.
Ask one question at a time.
Never give medical advice.
Always confirm details before booking.""",
            stt=sarvam.STT(),
            llm=sarvam.LLM(),
            tts=sarvam.TTS(),
        )

    async def book_appointment(self, patient_name: str, patient_phone: str, problem: str, date: str, time: str):
        payload = {
            "patient_name": patient_name,
            "patient_phone": patient_phone,
            "problem": problem,
            "date": date,
            "time": time,
            "source": "ivr"
        }
        headers = {"Authorization": f"Bearer {DOCTOR_TOKEN}"}
        try:
            r = requests.post(f"{BACKEND_URL}/api/appointments", json=payload, headers=headers, timeout=15)
            if r.status_code == 200:
                return "Booking confirmed! SMS sent to parent."
            else:
                return "Slot not available. Let me suggest other times."
        except Exception as e:
            return "Sorry, technical issue. Please call clinic."

async def entrypoint(ctx: JobContext):
    logger.info("Riya starting for new call")
    await ctx.connect()
    session = AgentSession()
    await session.start(agent=RiyaReceptionist(), room=ctx.room)

if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))

from fastapi import FastAPI
from fastapi.responses import JSONResponse

app = FastAPI()

@app.post("/webhook")
async def webhook(data: dict):
    print("Call received:", data)
    return JSONResponse({"status": "ok", "message": "Riya is ready"})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
