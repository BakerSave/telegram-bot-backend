from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse

import openai
from dotenv import load_dotenv
import os

load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

app = FastAPI()
chat_history = []

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/message", response_class=HTMLResponse)
def get_message(text: str):
    global chat_history

    if not chat_history:
        chat_history.append({"role": "system", "content": "Ты дружелюбный помощник."})

    chat_history.append({"role": "user", "content": text})
    print("PROMPT to GPT:", chat_history)

    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=chat_history,
        )
        reply = response["choices"][0]["message"]["content"]
        chat_history.append({"role": "assistant", "content": reply})
    except Exception as e:
        reply = f"Ошибка при обращении к GPT: {e}"

    history_debug = "<br>".join([
        f"<b>{msg['role']}:</b> {msg['content']}" for msg in chat_history
    ])

    return f"""
    <html>
        <body>
            <h2>Вы написали: {text}</h2>
            <p><b>Ответ GPT:</b> {reply}</p>
            <h3> Текущий переданный промпт GPT</h3>
            <div style='background:#f0f0f0; padding:10px; border:1px solid #ccc;'>{history_debug}</div>
            <br>
            <img src="/static/psycho.jpg" width="300">
        </body>
    </html>
    """

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse

import openai
from dotenv import load_dotenv
import os
import httpx

load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")
telegram_token = os.getenv("TELEGRAM_TOKEN")  # Добавь эту переменную в Railway → Variables

app = FastAPI()
chat_history = []

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.post("/webhook")
async def telegram_webhook(request: Request):
    payload = await request.json()
    print("Входящее сообщение от Telegram:", payload)

    try:
        chat_id = payload["message"]["chat"]["id"]
        text = payload["message"]["text"]

        reply = get_message(text)

        await send_telegram_message(chat_id, reply)

    except Exception as e:
        print("Ошибка при обработке сообщения:", e)

    return {"ok": True}


def get_message(text: str):
    global chat_history

    if not chat_history:
        chat_history.append({"role": "system", "content": "Ты дружелюбный помощник."})

    chat_history.append({"role": "user", "content": text})
    print("📤 PROMPT to GPT:", chat_history)

    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=chat_history,
        )
        reply = response["choices"][0]["message"]["content"]
        chat_history.append({"role": "assistant", "content": reply})
        return reply
    except Exception as e:
        return f"Ошибка при обращении к GPT: {e}"


async def send_telegram_message(chat_id: int, text: str):
    url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    async with httpx.AsyncClient() as client:
        await client.post(url, json=payload)

