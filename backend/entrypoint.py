from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import app, FRONTEND


@app.get("/manifest.json")
def manifest():
    return FileResponse(FRONTEND / "manifest.json")


@app.get("/sw.js")
def sw():
    return FileResponse(FRONTEND / "sw.js")


@app.get("/")
def index():
    return FileResponse(FRONTEND / "index.html")


app.mount("/static", StaticFiles(directory=str(FRONTEND)), name="static")
