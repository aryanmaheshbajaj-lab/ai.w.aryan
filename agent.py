import os
import logging
from dotenv import load_dotenv
from livekit.agents import JobContext, WorkerOptions, cli
from livekit.plugins import sarvam

load_dotenv()

logging.basicConfig(level=logging.INFO)

async def entrypoint(ctx: JobContext):
    logging.info("=== New Call Received - Riya Starting ===")
    
    await ctx.connect()
    
    agent = sarvam.Agent(
        instructions="You are Riya, a friendly and polite receptionist at Little Stars Child Clinic. Greet the caller warmly, ask how you can help, and handle appointment booking.",
        stt=sarvam.STT(),
        llm=sarvam.LLM(),
        tts=sarvam.TTS(),
    )
    
    await ctx.run_agent(agent)

if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
