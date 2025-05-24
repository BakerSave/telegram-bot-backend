from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
import openai
from dotenv import load_dotenv
import os
import httpx

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


@app.post("/webhook")
async def telegram_webhook(request: Request):
    payload = await request.json()
    print("📨 Входящее сообщение от Telegram:", payload)

    try:
        chat_id = payload["message"]["chat"]["id"]
        text = payload["message"]["text"].lower()

        if text.startswith("/style"):
            return await handle_style_command(chat_id, text)

        if "фото" in text:
            return await send_telegram_message(chat_id, "[фото]")  # Заглушка

        if any(word in text for word in ["видео", "кружок", "голос", "voice"]):
            reply = await generate_media_denial(chat_id, text)
            return await send_telegram_message(chat_id, f"{reply}\n\n🎭 Маска: {MASKS[get_style(chat_id)]['name']}")

        reply = await generate_reply(chat_id, text)
        return await send_telegram_message(chat_id, f"{reply}\n\n🎭 Маска: {MASKS[get_style(chat_id)]['name']}")

    except Exception as e:
        print("❌ Ошибка:", e)
        return {"ok": False}


async def handle_style_command(chat_id: int, text: str):
    try:
        style_key = text.split(" ", 1)[1].strip()
    except IndexError:
        return await send_telegram_message(chat_id, "Укажи стиль: /style flirt | rude | friendly")

    if style_key not in MASKS:
        return await send_telegram_message(chat_id, "Неизвестный стиль. Возможные: flirt, rude, friendly")

    user_styles[chat_id] = style_key
    name = MASKS[style_key]["name"]
    return await send_telegram_message(chat_id, f"✅ Маска переключена: {name}")


def get_style(chat_id: int) -> str:
    return user_styles.get(chat_id, "friendly")


async def generate_reply(chat_id: int, user_text: str) -> str:
    style = get_style(chat_id)
    prompt = MASKS[style]["prompt"]

    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": user_text}
    ]

    print(f"🎭 Маска: {style} ({MASKS[style]['name']})")
    print(f"📥 Пользователь: {user_text}")

    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=messages,
        )
        return response["choices"][0]["message"]["content"]
    except Exception as e:
        return f"⚠️ Ошибка GPT: {e}"


async def generate_media_denial(chat_id: int, user_text: str) -> str:
    style = get_style(chat_id)
    tone = MASKS[style]["prompt"]

    denial_instruction = (
        "Тебя попросили прислать медиа (видео, кружок, голос). "
        "Ты не можешь этого сделать. Ответь так, будто ты в маске:"
        f" '{MASKS[style]['name']}' — в характерной манере. "
        "Намекни, пофлиртуй или отшутись, но без медиа."
    )

    messages = [
        {"role": "system", "content": denial_instruction},
        {"role": "user", "content": user_text}
    ]

    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=messages,
        )
        return response["choices"][0]["message"]["content"]
    except Exception as e:
        return f"⚠️ Ошибка при отказе медиа: {e}"


async def send_telegram_message(chat_id: int, text: str):
    url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    async with httpx.AsyncClient() as client:
        await client.post(url, json=payload)
