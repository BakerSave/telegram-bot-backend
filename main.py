from fastapi.staticfiles import StaticFiles

app.mount("/static", StaticFiles(directory="static"), name="static")

from fastapi.responses import HTMLResponse

@app.get("/message", response_class=HTMLResponse)
def get_message(text: str):
    return f"""
    <html>
        <body>
            <h2>Вы написали: {text}</h2>
            <img src="/static/image.jpg" width="300">
        </body>
    </html>
    """
