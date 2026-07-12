import os
import logging
from dotenv import load_dotenv
from livekit.agents import JobContext, WorkerOptions, cli
from livekit.plugins import sarvam

load_dotenv()

logging.basicConfig(level=logging.INFO)

async def entrypoint(ctx: JobContext):
    logging.info("Riya is answering the call...")
    await ctx.connect()
    logging.info("Call connected successfully")

    agent = sarvam.RealtimeAgent(
        instructions="You are Riya, friendly receptionist at Little Stars Clinic. Help with appointments.",
        stt=sarvam.STT(),
        llm=sarvam.LLM(),
        tts=sarvam.TTS(),
    )
    await ctx.run_agent(agent)

if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
