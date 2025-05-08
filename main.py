from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse

import openai
from dotenv import load_dotenv
import os

load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/message", response_class=HTMLResponse)
def get_message(text: str):
    messages = [
        {"role": "system", "content": "Ты дружелюбный помощник."},
        {"role": "user", "content": text}
    ]

    print("PROMPT to GPT:", messages)

    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=messages,
        )
        reply = response["choices"][0]["message"]["content"]
    except Exception as e:
        reply = f"Ошибка при обращении к GPT: {e}"

    return f"""
    <html>
        <body>
            <h2>Вы написали: {text}</h2>
            <p><b>Ответ GPT:</b> {reply}</p>
            <img src="/static/cat.jpg" width="300">
        </body>
    </html>
    """
