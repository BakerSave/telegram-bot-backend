from fastapi import FastAPI
from fastapi.responses import PlainTextResponse

app = FastAPI()

@app.get("/message")
def get_message(text: str):
    return PlainTextResponse(f"Вы написали: {text}")