import os
import sys
import time
import uuid
import threading
import logging
import requests
import yt_dlp
from typing import Dict, Any, Optional, List

DOWNLOAD_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "downloads"))
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("A1Downloader")

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.tiktok.com/"
}

class DownloadTask:
    def __init__(self, task_id: str, url: str, threads: int = 8, format_id: str = "best"):
        self.task_id = task_id
        self.url = url
        self.threads = max(1, min(threads, 32))
        self.format_id = format_id
        self.filename = ""
        self.filepath = ""
        self.total_bytes = 0
        self.downloaded_bytes = 0
        self.speed = 0.0
        self.eta = 0
        self.status = "queued"
        self.error_message = ""
        self.is_media_stream = False
        self.title = ""
        self.thumbnail = ""
        self.chunk_count = self.threads
        self.direct_stream_url = ""  # For TikTok direct CDN
        self._pause_event = threading.Event()
        self._pause_event.set()
        self._cancel_flag = False
        self._lock = threading.Lock()

    def pause(self):
        self._pause_event.clear()
        self.status = "paused"

    def resume(self):
        self._pause_event.set()
        self.status = "downloading"

    def cancel(self):
        self._cancel_flag = True
        self._pause_event.set()
        self.status = "cancelled"

    def add_bytes(self, n: int):
        with self._lock:
            self.downloaded_bytes += n

    @property
    def percent(self) -> float:
        if self.total_bytes > 0:
            return round(min(100.0, (self.downloaded_bytes / self.total_bytes) * 100), 2)
        return 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.task_id,
            "url": self.url,
            "filename": self.filename or "Analyzing...",
            "title": self.title,
            "thumbnail": self.thumbnail,
            "total_bytes": self.total_bytes,
            "downloaded_bytes": self.downloaded_bytes,
            "percent": self.percent,
            "speed_mb": round(self.speed / (1024 * 1024), 2),
            "eta": self.eta,
            "status": self.status,
            "error": self.error_message,
            "is_media": self.is_media_stream,
            "threads": self.threads,
            "chunk_count": self.chunk_count
        }

def resolve_tiktok_direct(url: str) -> Optional[Dict[str, Any]]:
    """Dedicated TikTok Engine: Extracts 100% watermark-free HD MP4."""
    try:
        api_endpoint = f"https://www.tikwm.com/api/?url={requests.utils.quote(url)}"
        resp = requests.get(api_endpoint, headers=BROWSER_HEADERS, timeout=12)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("code") == 0 and data.get("data"):
                d = data["data"]
                play_url = d.get("play") or d.get("wmplay")
                music_url = d.get("music")
                title = d.get("title") or "TikTok_Video"
                # Clean title for filesystem
                safe_title = "".join(c for c in title if c.isalnum() or c in " ._-")[:60].strip() or "TikTok_Video"
                return {
                    "type": "tiktok",
                    "title": title,
                    "filename": f"TikTok_{safe_title}.mp4",
                    "thumbnail": d.get("cover") or "",
                    "video_url": play_url,
                    "music_url": music_url,
                    "size": d.get("size", 0)
                }
    except Exception as e:
        log.warning(f"TikTok Direct API fallback failed: {e}")
    return None

def analyze_url(url: str) -> Dict[str, Any]:
    # Check if TikTok
    if "tiktok.com" in url.lower():
        tt_info = resolve_tiktok_direct(url)
        if tt_info:
            return {
                "type": "media",
                "title": tt_info["title"],
                "thumbnail": tt_info["thumbnail"],
                "uploader": "TikTok Creator",
                "tiktok_direct": tt_info,
                "formats": [
                    {"format_id": "best", "ext": "mp4", "res": "HD (No Watermark)", "filesize": tt_info["size"]},
                    {"format_id": "audio", "ext": "mp3", "res": "Audio Only (MP3)", "filesize": 0}
                ]
            }

    # Standard yt-dlp extractor with browser spoofing
    ydl_opts = {
        "extract_flat": False,
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "http_headers": BROWSER_HEADERS
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if info and (info.get("formats") or info.get("_type") == "video" or info.get("url")):
                formats = []
                for f in info.get("formats", []):
                    if f.get("vcodec") == "none" and f.get("acodec") == "none":
                        continue
                    res = f.get("resolution") or f"{f.get('width', '')}x{f.get('height', '')}"
                    formats.append({
                        "format_id": f.get("format_id", ""),
                        "ext": f.get("ext", "mp4"),
                        "res": res,
                        "note": f.get("format_note", ""),
                        "filesize": f.get("filesize") or f.get("filesize_approx") or 0
                    })
                return {
                    "type": "media",
                    "title": info.get("title", "Video"),
                    "thumbnail": info.get("thumbnail", ""),
                    "duration": info.get("duration", 0),
                    "uploader": info.get("uploader", ""),
                    "formats": formats[:15]
                }
    except Exception:
        pass

    # Direct File Link Probe
    try:
        head = requests.head(url, allow_redirects=True, timeout=12, headers=BROWSER_HEADERS)
        content_length = int(head.headers.get("content-length", 0))
        accepts_ranges = "bytes" in head.headers.get("accept-ranges", "").lower()
        cd = head.headers.get("content-disposition", "")
        filename = ""
        if "filename=" in cd:
            filename = cd.split("filename=")[-1].strip('"; ')
        if not filename:
            filename = url.split("?")[0].rstrip("/").split("/")[-1] or "downloaded_file"
        return {
            "type": "direct",
            "filename": filename,
            "filesize": content_length,
            "supports_chunks": accepts_ranges and content_length > (2 * 1024 * 1024)
        }
    except Exception as e:
        return {"type": "direct", "filename": "downloaded_file", "filesize": 0, "supports_chunks": False}

class DownloadManager:
    def __init__(self):
        self.tasks: Dict[str, DownloadTask] = {}
        self._lock = threading.Lock()

    def all_tasks(self) -> List[DownloadTask]:
        with self._lock:
            return list(self.tasks.values())

    def get_task(self, task_id: str) -> Optional[DownloadTask]:
        return self.tasks.get(task_id)

    def start_download(self, url: str, format_id: str = "best", threads: int = 8) -> DownloadTask:
        task_id = uuid.uuid4().hex[:8]
        task = DownloadTask(task_id, url, threads=threads, format_id=format_id)
        with self._lock:
            self.tasks[task_id] = task
        threading.Thread(target=self._run_task, args=(task,), daemon=True).start()
        return task

    def pause(self, task_id: str):
        if t := self.get_task(task_id): t.pause()

    def resume(self, task_id: str):
        if t := self.get_task(task_id): t.resume()

    def cancel(self, task_id: str):
        if t := self.get_task(task_id): t.cancel()

    def _run_task(self, task: DownloadTask):
        task.status = "analyzing"
        analysis = analyze_url(task.url)

        if analysis.get("type") == "media":
            task.is_media_stream = True
            task.title = analysis.get("title", "")
            task.thumbnail = analysis.get("thumbnail", "")

            # If direct TikTok no-watermark stream is resolved:
            if "tiktok_direct" in analysis:
                tt = analysis["tiktok_direct"]
                target_url = tt["music_url"] if "audio" in task.format_id else tt["video_url"]
                ext = ".mp3" if "audio" in task.format_id else ".mp4"
                task.filename = tt["filename"].replace(".mp4", ext)
                self._download_stream(task, target_url)
            else:
                self._download_ytdlp(task)
        else:
            self._download_direct(task, analysis)

    def _download_stream(self, task: DownloadTask, direct_url: str):
        """Direct stream downloader with real-time speed & pause/resume."""
        task.status = "downloading"
        task.filepath = os.path.join(DOWNLOAD_DIR, task.filename)
        try:
            with requests.get(direct_url, headers=BROWSER_HEADERS, stream=True, timeout=30) as r:
                r.raise_for_status()
                task.total_bytes = int(r.headers.get("content-length", 0))
                last_time = time.time()
                last_bytes = 0

                with open(task.filepath, "wb") as f:
                    for chunk in r.iter_content(chunk_size=128 * 1024):
                        if task._cancel_flag:
                            task.status = "cancelled"
                            if os.path.exists(task.filepath): os.remove(task.filepath)
                            return
                        task._pause_event.wait()
                        if chunk:
                            f.write(chunk)
                            task.add_bytes(len(chunk))
                            now = time.time()
                            if now - last_time >= 0.4:
                                task.speed = (task.downloaded_bytes - last_bytes) / (now - last_time)
                                if task.speed > 0 and task.total_bytes > 0:
                                    task.eta = int((task.total_bytes - task.downloaded_bytes) / task.speed)
                                last_bytes = task.downloaded_bytes
                                last_time = now
            task.status = "completed"
        except Exception as e:
            task.status = "failed"
            task.error_message = str(e)

    def _download_ytdlp(self, task: DownloadTask):
        task.status = "downloading"
        def progress_hook(d):
            if task._cancel_flag:
                raise yt_dlp.utils.DownloadError("Cancelled by user")
            if d['status'] == 'downloading':
                task.downloaded_bytes = d.get('downloaded_bytes', 0)
                task.total_bytes = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
                task.speed = d.get('speed') or 0.0
                task.eta = d.get('eta') or 0
                task.filename = os.path.basename(d.get('filename', 'video.mp4'))
            elif d['status'] == 'finished':
                task.status = "merging"
                task.downloaded_bytes = task.total_bytes

        ydl_opts = {
            'format': task.format_id or 'bestvideo+bestaudio/best',
            'outtmpl': os.path.join(DOWNLOAD_DIR, '%(title).80s.%(ext)s'),
            'progress_hooks': [progress_hook],
            'http_headers': BROWSER_HEADERS,
            'quiet': True,
            'no_warnings': True,
            'nocheckcertificate': True
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(task.url, download=True)
                task.filename = os.path.basename(ydl.prepare_filename(info))
            task.status = "completed"
        except Exception as e:
            task.status = "failed"
            task.error_message = str(e)

    def _download_direct(self, task: DownloadTask, analysis: Dict[str, Any]):
        task.filename = analysis.get("filename", "download_file")
        task.total_bytes = analysis.get("filesize", 0)
        task.filepath = os.path.join(DOWNLOAD_DIR, task.filename)
        supports_chunks = analysis.get("supports_chunks", False)
        task.status = "downloading"

        def monitor():
            last_bytes = 0
            last_time = time.time()
            while task.status == "downloading":
                time.sleep(0.5)
                now = time.time()
                dt = now - last_time
                db = task.downloaded_bytes - last_bytes
                if dt > 0:
                    task.speed = db / dt
                    rem = task.total_bytes - task.downloaded_bytes
                    task.eta = int(rem / task.speed) if task.speed > 0 else 0
                last_bytes = task.downloaded_bytes
                last_time = now
        threading.Thread(target=monitor, daemon=True).start()

        if not supports_chunks or task.threads <= 1:
            try:
                with requests.get(task.url, stream=True, timeout=30, headers=BROWSER_HEADERS) as r:
                    r.raise_for_status()
                    if task.total_bytes == 0:
                        task.total_bytes = int(r.headers.get("content-length", 0))
                    with open(task.filepath, "wb") as f:
                        for chunk in r.iter_content(chunk_size=128 * 1024):
                            if task._cancel_flag: return
                            task._pause_event.wait()
                            if chunk:
                                f.write(chunk)
                                task.add_bytes(len(chunk))
                task.status = "completed"
            except Exception as e:
                task.status = "failed"
                task.error_message = str(e)
            return

        # Parallel chunked range download
        chunk_size = task.total_bytes // task.threads
        ranges = []
        for i in range(task.threads):
            s = i * chunk_size
            e = (s + chunk_size - 1) if i < task.threads - 1 else (task.total_bytes - 1)
            ranges.append((i, s, e))
        part_files = [f"{task.filepath}.part{i}" for i in range(task.threads)]

        def worker(idx, s, e):
            p = part_files[idx]
            headers = dict(BROWSER_HEADERS)
            headers["Range"] = f"bytes={s}-{e}"
            try:
                with requests.get(task.url, headers=headers, stream=True, timeout=30) as r:
                    r.raise_for_status()
                    with open(p, "wb") as pf:
                        for b in r.iter_content(chunk_size=64 * 1024):
                            if task._cancel_flag: return
                            task._pause_event.wait()
                            if b:
                                pf.write(b)
                                task.add_bytes(len(b))
            except Exception as ex:
                task.error_message = str(ex)

        threads_list = []
        for idx, s, e in ranges:
            t = threading.Thread(target=worker, args=(idx, s, e))
            threads_list.append(t)
            t.start()
        for t in threads_list: t.join()

        if task.error_message or task._cancel_flag:
            for p in part_files:
                if os.path.exists(p): os.remove(p)
            task.status = "failed" if task.error_message else "cancelled"
            return

        task.status = "merging"
        with open(task.filepath, "wb") as final_f:
            for p in part_files:
                if os.path.exists(p):
                    with open(p, "rb") as pf: final_f.write(pf.read())
                    os.remove(p)
        task.status = "completed"

manager = DownloadManager()
