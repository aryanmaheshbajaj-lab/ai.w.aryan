import os
import logging
from dotenv import load_dotenv
from fastapi import FastAPI
from livekit.agents import JobContext, WorkerOptions, cli
from livekit.plugins import sarvam

load_dotenv()

app = FastAPI()

logging.basicConfig(level=logging.INFO)

async def entrypoint(ctx: JobContext):
    logging.info("=== Riya Voice Agent Starting ===")
    await ctx.connect()
    logging.info("Connected to LiveKit room")
    
    agent = sarvam.RealtimeAgent(
        instructions="""You are Riya, a polite, professional, and friendly receptionist at Little Stars Child Clinic.
        Help patients book appointments, check availability, and answer general queries.
        Always be clear, helpful, and confirm details before booking.""",
        stt=sarvam.STT(),
        llm=sarvam.LLM(),
        tts=sarvam.TTS(),
    )
    await ctx.run_agent(agent)

@app.get("/")
async def health():
    return {"status": "Riya Voice Agent is running"}

if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
