from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
import openai
from dotenv import load_dotenv
import os
import httpx
import asyncio
import time
import random

load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")
telegram_token = os.getenv("TELEGRAM_TOKEN")

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

MASKS = {
    "flirt": {
        "name": "Флирт",
        "prompt": "Ты флиртуешь с собеседником. Общение лёгкое, игривое, с поддразниванием и улыбкой."
    },
    "rude": {
        "name": "Грубый",
        "prompt": "Ты говоришь резко, грубо, с раздражением и вызовом. Можешь саркастично шутить."
    },
    "friendly": {
        "name": "Дружелюбный",
        "prompt": "Ты общаешься мягко, поддерживающе, с юмором и сочувствием."
    }
}

user_styles = {}
last_active = {}        # chat_id: timestamp
was_pinged = {}         # chat_id: bool
chat_histories = {}     # chat_id: list of messages

@app.on_event("startup")
async def start_background_task():
    asyncio.create_task(background_checker())

@app.post("/webhook")
async def telegram_webhook(request: Request):
    payload = await request.json()
    chat_id = payload["message"]["chat"]["id"]
    text = payload["message"]["text"].lower()

    # Обновляем активность
    last_active[chat_id] = time.time()
    was_pinged[chat_id] = False

    if chat_id not in chat_histories:
        chat_histories[chat_id] = []

    if text.startswith("/style"):
        return await handle_style_command(chat_id, text)

    if "фото" in text:
        await save_message(chat_id, "user", text)
        await save_message(chat_id, "assistant", "[фото]")
        return await send_telegram_message(chat_id, "[фото]")

    if any(w in text for w in ["видео", "кружок", "голос"]):
        reply = await generate_media_denial(chat_id, text)
        await save_message(chat_id, "user", text)
        await save_message(chat_id, "assistant", reply)
        return await send_telegram_message(chat_id, f"{reply}\n\n🎭 Маска: {MASKS[get_style(chat_id)]['name']}")

    reply = await generate_reply(chat_id, text)
    await save_message(chat_id, "user", text)
    await save_message(chat_id, "assistant", reply)
    return await send_telegram_message(chat_id, f"{reply}\n\n🎭 Маска: {MASKS[get_style(chat_id)]['name']}")

async def handle_style_command(chat_id: int, text: str):
    try:
        style_key = text.split(" ", 1)[1].strip()
    except IndexError:
        return await send_telegram_message(chat_id, "Укажи стиль: /style flirt | rude | friendly")

    if style_key not in MASKS:
        return await send_telegram_message(chat_id, "Неизвестный стиль. Возможные: flirt, rude, friendly")

    user_styles[chat_id] = style_key
    return await send_telegram_message(chat_id, f"✅ Маска переключена: {MASKS[style_key]['name']}")

def get_style(chat_id: int) -> str:
    return user_styles.get(chat_id, "friendly")

async def generate_reply(chat_id: int, user_text: str) -> str:
    style = get_style(chat_id)
    prompt = MASKS[style]["prompt"]
    messages = [{"role": "system", "content": prompt}] + chat_histories.get(chat_id, [])[-6:] + [
        {"role": "user", "content": user_text}
    ]
    try:
        response = openai.ChatCompletion.create(model="gpt-3.5-turbo", messages=messages)
        return response["choices"][0]["message"]["content"]
    except Exception as e:
        return f"⚠️ Ошибка GPT: {e}"

async def generate_media_denial(chat_id: int, user_text: str) -> str:
    tone = MASKS[get_style(chat_id)]["prompt"]
    instruction = (
        "Тебя попросили отправить медиа (видео, кружок, голос). "
        "Ты не можешь этого сделать. Ответь в стиле маски: " + tone +
        " Намекни, отшутись или флиртуй, но не отправляй медиа."
    )
    messages = [{"role": "system", "content": instruction}, {"role": "user", "content": user_text}]
    try:
        response = openai.ChatCompletion.create(model="gpt-3.5-turbo", messages=messages)
        return response["choices"][0]["message"]["content"]
    except Exception as e:
        return f"⚠️ Ошибка при отказе медиа: {e}"

async def send_telegram_message(chat_id: int, text: str):
    url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    async with httpx.AsyncClient() as client:
        await client.post(url, json=payload)

async def save_message(chat_id: int, role: str, content: str):
    if chat_id not in chat_histories:
        chat_histories[chat_id] = []
    chat_histories[chat_id].append({"role": role, "content": content})

async def background_checker():
    while True:
        now = time.time()
        for chat_id, last_time in last_active.items():
            if was_pinged.get(chat_id):
                continue

            elapsed = now - last_time
            random_delay = random.randint(60, 120)  # от 1 до 2 минут

            if elapsed >= random_delay:
                reply = await generate_ping(chat_id)
                await send_telegram_message(chat_id, f"{reply}\n\n🎭 Маска: {MASKS[get_style(chat_id)]['name']}")
                await save_message(chat_id, "assistant", reply)
                was_pinged[chat_id] = True

        await asyncio.sleep(30)

async def generate_ping(chat_id: int) -> str:
    prompt = MASKS[get_style(chat_id)]["prompt"]
    messages = [{"role": "system", "content": prompt}] + chat_histories.get(chat_id, [])[-6:] + [
        {"role": "user", "content": "Ты хочешь продолжить разговор, потому что пользователь молчит. Ответь в характерном стиле."}
    ]
    try:
        response = openai.ChatCompletion.create(model="gpt-3.5-turbo", messages=messages)
        return response["choices"][0]["message"]["content"]
    except Exception as e:
        return f"🤖 (не смог пингануть): {e}"
