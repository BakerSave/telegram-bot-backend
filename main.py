from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
import openai
from dotenv import load_dotenv
import os
import httpx

# Загрузка переменных из .env
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")
telegram_token = os.getenv("TELEGRAM_TOKEN")

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

# Шаблонные system-промпты (можешь потом заменить на реальные)
system_prompts = {
    "шаблон1": "Ты ведёшь себя тепло и ласково.",
    "шаблон2": "Ты отвечаешь резко, грубо и с раздражением.",
    "шаблон3": "Ты говоришь сдержанно и нейтрально."
}


@app.post("/webhook")
async def telegram_webhook(request: Request):
    payload = await request.json()
    print("📨 Входящее сообщение от Telegram:", payload)

    try:
        chat_id = payload["message"]["chat"]["id"]
        text = payload["message"]["text"]

        reply = await get_gpt_reply(text)
        await send_telegram_message(chat_id, reply)

    except Exception as e:
        print("❌ Ошибка при обработке:", e)

    return {"ok": True}


def detect_prompt_mode(text: str) -> str:
    """Определяем шаблон по словам в сообщении."""
    text = text.lower()
    if any(word in text for word in ["милая", "умница", "классная", "люблю", "спасибо", "лапочка"]):
        return "шаблон1"
    if any(word in text for word in ["тварь", "идиот", "дура", "ненавижу", "бесишь", "отвратительно"]):
        return "шаблон2"
    return "шаблон3"  # Нейтральное


async def get_gpt_reply(user_text: str) -> str:
    # Выбор шаблона на основе текста
    mode = detect_prompt_mode(user_text)
    system_prompt = system_prompts[mode]

    print(f"🧠 Выбран шаблон: {mode}")
    print(f"📥 Сообщение: {user_text}")

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_text}
    ]

    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=messages,
        )
        reply = response["choices"][0]["message"]["content"]
        return reply
    except Exception as e:
        return f"⚠️ Ошибка GPT: {e}"


async def send_telegram_message(chat_id: int, text: str):
    url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    async with httpx.AsyncClient() as client:
        await client.post(url, json=payload)
