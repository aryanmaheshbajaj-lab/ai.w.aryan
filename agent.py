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
    logging.info("Riya worker starting...")
    await ctx.connect()
    logging.info("Connected to room")
    
    agent = sarvam.RealtimeAgent(
        instructions="""You are Riya, a polite and professional receptionist at Little Stars Clinic.
        Help patients with appointment booking, doctor availability, and general inquiries.
        Be helpful, clear, and friendly. Always confirm details before booking.""",
        stt=sarvam.STT(),
        llm=sarvam.LLM(),
        tts=sarvam.TTS(),
    )
    await ctx.run_agent(agent)

# Webhook for Voicelink
@app.post("/webhook")
async def webhook():
    return {"status": "ok"}

if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
