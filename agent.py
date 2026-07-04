import os
import logging
from dotenv import load_dotenv
from livekit.agents import JobContext, WorkerOptions, cli
from livekit.plugins import sarvam

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Riya-IVR")

class RiyaReceptionist:
    def __init__(self):
        self.instructions = """You are Riya, a polite and friendly AI receptionist at Little Stars Child Clinic. 
        Speak naturally in Hindi or English. Help with appointments, greetings, and basic queries."""

async def entrypoint(ctx: JobContext):
    logger.info("New call received - Riya starting")
    
    await ctx.connect()

    agent = sarvam.Agent(
        instructions=RiyaReceptionist().instructions,
        stt=sarvam.STT(),
        llm=sarvam.LLM(),
        tts=sarvam.TTS(),
    )

    await ctx.run_agent(agent)

if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
