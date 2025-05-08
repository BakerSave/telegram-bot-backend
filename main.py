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
chat_history = []

@app.get("/message", response_class=HTMLResponse)
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
  except Exception as e:
      reply = f"Ошибка при обращении к GPT: {e}"

  # Текст для вывода в браузере
  history_debug = "<br>".join([
      f"<b>{msg['role']}:</b> {msg['content']}" for msg in chat_history
  ])

  return f"""
  <html>
      <body>
          <h2>Вы написали: {text}</h2>
          <p><b>Ответ GPT:</b> {reply}</p>
          <h3>🪵 Отладка: что реально отправилось в GPT</h3>
          <div style='background:#f0f0f0; padding:10px; border:1px solid #ccc;'>{history_debug}</div>
          <br>
          <img src="/static/cat.jpg" width="300">
      </body>
  </html>
  """
  <html>
      <body>
          <h2>Вы написали: {text}</h2>
          <p><b>Ответ GPT:</b> {reply}</p>
          <img src="/static/cat.jpg" width="300">
      </body>
  </html>
  """
