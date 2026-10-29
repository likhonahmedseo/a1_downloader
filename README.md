# NexaDrop

NexaDrop is a local-first internet downloader web app. It has two lanes:

- Direct HTTP/HTTPS file inspection and streaming download, including large-file friendly streaming.
- An optional `yt-dlp` media-extractor API for media pages where you own the content or have permission to download it.

## Run locally

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn app:app --reload --host 127.0.0.1 --port 8000
```

Then open `http://127.0.0.1:8000`.

On Windows, you can double-click `start_app.bat` to create the environment, install dependencies on the first run, open the app, and start the server automatically.

The extractor lane is included in `requirements.txt`; `start_app.bat` checks and installs it every time it starts. Production deployments should add authentication, rate limits, a background job queue, disk quotas, malware scanning, and stricter outbound egress controls before exposing the server publicly.

## Scope note

The app is designed for direct files and media that the user owns or is authorized to download. Some platforms prohibit third-party downloading or require their own approved APIs/download features; the app does not bypass DRM, logins, or access controls.
