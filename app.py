import os
import asyncio
import subprocess
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
from downloader import manager, analyze_url

app = FastAPI(title="A1 Downloader")

class DownloadRequest(BaseModel):
    url: str
    target_dir: str = ""
    format_id: str = "best"
    threads: int = 8

class AnalyzeRequest(BaseModel):
    url: str

def get_default_download_dir():
    # User Downloads folder
    user_home = os.path.expanduser("~")
    downloads = os.path.join(user_home, "Downloads")
    if os.path.exists(downloads):
        return os.path.abspath(downloads)
    return os.path.abspath(user_home)

@app.get("/", response_class=HTMLResponse)
async def read_index():
    with open("templates/index.html", "r", encoding="utf-8") as f:
        return f.read()

@app.get("/api/default_directory")
async def api_default_directory():
    return {"path": get_default_download_dir()}

@app.post("/api/choose_directory")
async def choose_directory_dialog():
    """Opens a native system folder dialog to select where to save."""
    def run_dialog():
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            folder = filedialog.askdirectory(title="Choose Download Location", initialdir=get_default_download_dir())
            root.destroy()
            return folder
        except Exception:
            return ""

    folder = await asyncio.to_thread(run_dialog)
    return {"path": folder}

@app.post("/api/open_folder")
async def open_folder_in_explorer(req: dict):
    path = req.get("path")
    if path and os.path.exists(path):
        if os.name == "nt":
            subprocess.Popen(f'explorer /select,"{os.path.abspath(path)}"')
        return {"ok": True}
    return {"error": "Path not found"}

@app.post("/api/analyze")
async def api_analyze(req: AnalyzeRequest):
    return await asyncio.to_thread(analyze_url, req.url)

@app.post("/api/download")
async def api_download(req: DownloadRequest):
    target = req.target_dir.strip() if req.target_dir else get_default_download_dir()
    os.makedirs(target, exist_ok=True)
    task = manager.start_download(req.url, target_dir=target, format_id=req.format_id, threads=req.threads)
    return {"status": "started", "task_id": task.task_id, "target_dir": target}

@app.post("/api/tasks/{task_id}/pause")
async def pause_task(task_id: str):
    manager.pause(task_id)
    return {"ok": True}

@app.post("/api/tasks/{task_id}/resume")
async def resume_task(task_id: str):
    manager.resume(task_id)
    return {"ok": True}

@app.post("/api/tasks/{task_id}/cancel")
async def cancel_task(task_id: str):
    manager.cancel(task_id)
    return {"ok": True}

@app.delete("/api/tasks/{task_id}")
async def delete_task(task_id: str):
    manager.remove_task(task_id)
    return {"ok": True}

@app.get("/api/download_file")
async def serve_file(path: str):
    if os.path.exists(path) and os.path.isfile(path):
        return FileResponse(path, filename=os.path.basename(path))
    raise HTTPException(status_code=404, detail="File not found")

@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            tasks_data = [t.to_dict() for t in manager.all_tasks()]
            await ws.send_json({"tasks": tasks_data})
            await asyncio.sleep(0.4)
    except WebSocketDisconnect:
        pass

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
