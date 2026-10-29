import os
import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
from downloader import manager, analyze_url, DOWNLOAD_DIR

app = FastAPI(title="FlashDownloader Pro")

class DownloadRequest(BaseModel):
    url: str
    format_id: str = "best"
    threads: int = 8

class AnalyzeRequest(BaseModel):
    url: str

@app.get("/", response_class=HTMLResponse)
async def read_index():
    with open("templates/index.html", "r", encoding="utf-8") as f:
        return f.read()

@app.post("/api/analyze")
async def api_analyze(req: AnalyzeRequest):
    return await asyncio.to_thread(analyze_url, req.url)

@app.post("/api/download")
async def api_download(req: DownloadRequest):
    task = manager.start_download(req.url, format_id=req.format_id, threads=req.threads)
    return {"status": "started", "task_id": task.task_id}

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

@app.get("/api/files")
async def get_files():
    files = []
    if os.path.exists(DOWNLOAD_DIR):
        for f in os.listdir(DOWNLOAD_DIR):
            if not f.endswith(".part") and ".part" not in f:
                fp = os.path.join(DOWNLOAD_DIR, f)
                if os.path.isfile(fp):
                    st = os.stat(fp)
                    files.append({"name": f, "size_mb": round(st.st_size / (1024 * 1024), 2), "created": st.st_mtime})
    return sorted(files, key=lambda x: x["created"], reverse=True)

@app.get("/api/files/{filename}")
async def serve_file(filename: str):
    fp = os.path.join(DOWNLOAD_DIR, filename)
    if os.path.exists(fp):
        return FileResponse(fp, filename=filename)
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
