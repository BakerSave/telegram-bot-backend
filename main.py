from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
import openai
from dotenv import load_dotenv
import os
import httpx

# Загрузка переменных окружения
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")
telegram_token = os.getenv("TELEGRAM_TOKEN")

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

# System-промпты (ты можешь заменить на реальные позже)
system_prompts = {
    "шаблон1": "Ты ведёшь себя дружелюбно, мягко, ласково.",
    "шаблон2": "Ты отвечаешь жёстко, раздражённо и немного грубо.",
    "шаблон3": "Ты говоришь нейтрально, ровно и объективно."
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


async def get_gpt_reply(user_text: str) -> str:
    # Сначала определим, как с ботом разговаривают
    prompt_mode = await detect_prompt_mode_with_gpt(user_text)
    system_prompt = system_prompts[prompt_mode]

    print(f"🧠 Тон сообщения: {prompt_mode}")
    print(f"📥 Пользователь написал: {user_text}")

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


async def detect_prompt_mode_with_gpt(user_text: str) -> str:
    """GPT сам оценивает, как с ним говорят: вежливо, агрессивно, нейтрально."""
    classification_prompt = [
        {"role": "system", "content": "Проанализируй тон этого сообщения. Ответь только одним словом: 'вежливое', 'агрессивное' или 'нейтральное'."},
        {"role": "user", "content": user_text}
    ]

    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=classification_prompt,
        )
        result = response["choices"][0]["message"]["content"].strip().lower()
        print(f"📊 GPT классифицировал как: {result}")

        if "вежлив" in result:
            return "шаблон1"
        if "агресс" in result:
            return "шаблон2"
        return "шаблон3"

    except Exception as e:
        print("⚠️ Ошибка при классификации:", e)
        return "шаблон3"


async def send_telegram_message(chat_id: int, text: str):
    url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    async with httpx.AsyncClient() as client:
        await client.post(url, json=payload)
