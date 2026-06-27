import os
import logging
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from livekit.agents import JobContext, WorkerOptions, cli
from livekit.agents.voice import Agent, AgentSession
from livekit.plugins import sarvam
import requests

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Riya-IVR")

BACKEND_URL = os.getenv("BACKEND_URL")
DOCTOR_TOKEN = os.getenv("DOCTOR_TOKEN")

app = FastAPI()

class RiyaReceptionist(Agent):
    def __init__(self):
        super().__init__(
            instructions="You are Riya, polite receptionist for Little Stars Child Clinic. Speak naturally in Hindi/English. Follow the conversation guide.",
            stt=sarvam.STT(),
            llm=sarvam.LLM(),
            tts=sarvam.TTS(),
        )

@app.post("/webhook")
async def webhook():
    logger.info("Call received from Voicelink")
    return {"status": "ok", "message": "Riya is ready"}

if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
   
if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))

if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=lambda ctx: AgentSession().start(RiyaReceptionist(), room=ctx.room)))
