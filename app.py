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
    """Opens a native Windows folder dialog to select where to save."""
    def run_dialog():
        # 1. Try Windows native FolderBrowserDialog via PowerShell (most reliable on Windows)
        try:
            ps_script = """
Add-Type -AssemblyName System.Windows.Forms
$dialog = New-Object System.Windows.Forms.FolderBrowserDialog
$dialog.Description = "Select Download Folder for A1 Downloader"
$dialog.ShowNewFolderButton = $true
$dialog.SelectedPath = [System.Environment]::GetFolderPath([System.Environment+SpecialFolder]::UserProfile) + "\\Downloads"
$topForm = New-Object System.Windows.Forms.Form
$topForm.TopMost = $true
$result = $dialog.ShowDialog($topForm)
if ($result -eq [System.Windows.Forms.DialogResult]::OK) {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    Write-Output $dialog.SelectedPath
}
"""
            proc = subprocess.run(
                ["powershell", "-Sta", "-NoProfile", "-Command", ps_script],
                capture_output=True,
                text=True,
                timeout=60
            )
            selected = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""
            if selected and os.path.exists(selected):
                return selected
        except Exception:
            pass

        # 2. Fallback to Tkinter if PowerShell dialog fails
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            folder = filedialog.askdirectory(title="Choose Download Location", initialdir=get_default_download_dir())
            root.destroy()
            if folder and os.path.exists(folder):
                return os.path.abspath(folder)
        except Exception:
            pass

        return get_default_download_dir()

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
