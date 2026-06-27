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
DOCTOR_TOKEN = os.getenv("DOCTOR_TOKEN")

class RiyaReceptionist(Agent):
    def __init__(self):
        super().__init__(
            instructions="You are Riya, polite AI receptionist for Little Stars Child Clinic. Speak naturally in Hindi/English. Be helpful and polite.",
            stt=sarvam.STT(),
            llm=sarvam.LLM(),
            tts=sarvam.TTS(),
        )

async def entrypoint(ctx: JobContext):
    logger.info("Riya starting for new call")
    await ctx.connect()
    session = AgentSession()
    await session.start(agent=RiyaReceptionist(), room=ctx.room)

if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
