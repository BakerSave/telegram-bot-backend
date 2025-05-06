from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/message", response_class=HTMLResponse)
def get_message(text: str):
    return f"""
    <html>
      <body>
        <h2>Вы написали: {text}</h2>
        <img src="/static/cat.jpg" width="300">
      </body>
    </html>
    """
