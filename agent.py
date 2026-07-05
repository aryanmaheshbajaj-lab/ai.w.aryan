import os
import logging
from dotenv import load_dotenv
from livekit.agents import JobContext, WorkerOptions, cli
from livekit.plugins import sarvam

load_dotenv()

logging.basicConfig(level=logging.INFO)

async def entrypoint(ctx: JobContext):
    logging.info("Worker starting...")
    logging.info(f"Connecting to LiveKit: {os.getenv('LIVEKIT_URL')}")
    
    await ctx.connect()
    
    logging.info("Connected to LiveKit successfully")
    
    agent = sarvam.Agent(
        instructions="You are Riya, receptionist at Little Stars Clinic. Greet the caller and help them.",
        stt=sarvam.STT(),
        llm=sarvam.LLM(),
        tts=sarvam.TTS(),
    )
    
    await ctx.run_agent(agent)

if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
