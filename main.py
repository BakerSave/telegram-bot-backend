from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
import openai
from dotenv import load_dotenv
import os
import httpx

# Загрузка переменных окружения
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")
telegram_token = os.getenv("TELEGRAM_TOKEN")  # Убедись, что он задан в Railway

app = FastAPI()

# Монтируем статику для картинки
app.mount("/static", StaticFiles(directory="static"), name="static")

# Хранилище истории диалогов (по chat_id)
user_histories = {}  # chat_id: list of messages


@app.post("/webhook")
async def telegram_webhook(request: Request):
    payload = await request.json()
    print("📨 Входящее сообщение от Telegram:", payload)

    try:
        chat_id = payload["message"]["chat"]["id"]
        text = payload["message"]["text"]

        reply = await get_gpt_reply(chat_id, text)
        await send_telegram_message(chat_id, reply)

    except Exception as e:
        print("❌ Ошибка при обработке сообщения:", e)

    return {"ok": True}


async def get_gpt_reply(chat_id: int, text: str) -> str:
    # Получаем или создаём историю пользователя
    if chat_id not in user_histories:
        user_histories[chat_id] = [
            {"role": "system", "content": "Ты дружелюбный помощник."}
        ]

    history = user_histories[chat_id]

    # Добавляем пользовательское сообщение
    history.append({"role": "user", "content": text})
    print("📤 PROMPT to GPT:", history)

    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=history,
        )
        reply = response["choices"][0]["message"]["content"]
        history.append({"role": "assistant", "content": reply})
        return reply
    except Exception as e:
        return f"Ошибка при обращении к GPT: {e}"


async def send_telegram_message(chat_id: int, text: str):
    url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    async with httpx.AsyncClient() as client:
        await client.post(url, json=payload)