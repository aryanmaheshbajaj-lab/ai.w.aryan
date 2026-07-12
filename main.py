from fastapi import FastAPI
import uvicorn

app = FastAPI()

@app.get("/")
async def root():
    return {"message": "Riya is online"}

@app.post("/webhook")
async def webhook():
    return {"action": "speak", "text": "Hello, this is Riya from Little Stars Clinic. How can I help you?"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
