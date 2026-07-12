import os
import logging
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket
from livekit.agents import JobContext, WorkerOptions, cli
from livekit.plugins import sarvam

load_dotenv()

app = FastAPI()

logging.basicConfig(level=logging.INFO)

async def entrypoint(ctx: JobContext):
    logging.info("Riya Voice Agent Started for call")
    await ctx.connect()
    logging.info("Connected to room - Call should be active")
    
    agent = sarvam.RealtimeAgent(
        instructions="You are Riya, polite receptionist at Little Stars Clinic. Greet the caller warmly and help with appointments.",
        stt=sarvam.STT(),
        llm=sarvam.LLM(),
        tts=sarvam.TTS(),
    )
    await ctx.run_agent(agent)

@app.get("/")
async def health():
    return {"status": "healthy"}

# For Voicelink WebSocket
@app.websocket("/voice")
async def voice_websocket(websocket: WebSocket):
    await websocket.accept()
    # LiveKit handles the connection
    await websocket.close()

if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
