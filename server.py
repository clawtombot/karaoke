"""
PHANTOM Karaoke Pipeline — FastAPI Backend
Runs on port 8001. Accepts audio uploads, spawns pipeline.py as subprocess,
provides status polling and output download.

Run: python server.py
"""

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

PORT = int(os.getenv("PORT", "8001"))
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "./uploads"))
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "./outputs"))
TMP_DIR = Path(os.getenv("TMP_DIR", "./tmp"))

for d in [UPLOAD_DIR, OUTPUT_DIR, TMP_DIR]:
    d.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="PHANTOM Karaoke Server", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory job store: {job_id: {status, output_path, error, ...}}
jobs: dict[str, dict] = {}


@app.get("/")
def root():
    return {"status": "ok", "service": "PHANTOM Karaoke Server"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/process")
async def process(
    file: UploadFile = File(...),
    title: str = Form(...),
    artist: str = Form(...),
):
    """
    Accept audio file upload and kick off pipeline.
    Returns job_id for polling.
    """
    job_id = str(uuid.uuid4())

    # Save upload
    ext = Path(file.filename).suffix or ".mp3"
    upload_path = UPLOAD_DIR / f"{job_id}{ext}"
    output_path = OUTPUT_DIR / f"{job_id}.mp4"

    contents = await file.read()
    upload_path.write_bytes(contents)

    jobs[job_id] = {
        "status": "queued",
        "title": title,
        "artist": artist,
        "input": str(upload_path),
        "output": str(output_path),
        "error": None,
    }

    # Spawn pipeline subprocess
    _spawn_pipeline(job_id, str(upload_path), str(output_path), title, artist)

    return {"job_id": job_id, "status": "queued"}


def _spawn_pipeline(job_id, input_path, output_path, title, artist):
    """Spawn pipeline.py as a subprocess and update job status asynchronously."""
    import threading

    def _run():
        jobs[job_id]["status"] = "processing"
        pipeline_script = Path(__file__).parent / "pipeline.py"
        cmd = [
            sys.executable, str(pipeline_script),
            "--input", input_path,
            "--output", output_path,
            "--title", title,
            "--artist", artist,
            "--tmp", str(TMP_DIR / job_id),
        ]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=3600,  # 1 hour max
            )
            if result.returncode == 0:
                jobs[job_id]["status"] = "complete"
            else:
                jobs[job_id]["status"] = "error"
                jobs[job_id]["error"] = result.stderr[-2000:] if result.stderr else "Unknown error"
        except subprocess.TimeoutExpired:
            jobs[job_id]["status"] = "error"
            jobs[job_id]["error"] = "Pipeline timed out (1 hour limit)"
        except Exception as e:
            jobs[job_id]["status"] = "error"
            jobs[job_id]["error"] = str(e)

    t = threading.Thread(target=_run, daemon=True)
    t.start()


@app.get("/api/status/{job_id}")
def get_status(job_id: str):
    """Poll job status."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    job = jobs[job_id]
    resp = {
        "job_id": job_id,
        "status": job["status"],
        "title": job.get("title"),
        "artist": job.get("artist"),
    }
    if job["status"] == "error":
        resp["error"] = job.get("error")
    if job["status"] == "complete":
        resp["download_url"] = f"/api/download/{job_id}"
    return resp


@app.get("/api/download/{job_id}")
def download(job_id: str):
    """Download completed MP4."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    job = jobs[job_id]
    if job["status"] != "complete":
        raise HTTPException(status_code=400, detail=f"Job status: {job['status']}")
    output_path = Path(job["output"])
    if not output_path.exists():
        raise HTTPException(status_code=404, detail="Output file not found")
    title = job.get("title", "karaoke")
    filename = f"{title.replace(' ', '_')}_karaoke.mp4"
    return FileResponse(str(output_path), media_type="video/mp4", filename=filename)


@app.get("/api/jobs")
def list_jobs():
    """List all jobs and their statuses."""
    return [
        {"job_id": jid, "status": j["status"], "title": j.get("title")}
        for jid, j in jobs.items()
    ]


if __name__ == "__main__":
    print(f"PHANTOM Karaoke Server starting on port {PORT}")
    print(f"Lab frontend: https://thomasnguyens-macbook-pro-1.tail4fc6de.ts.net/karaoke/")
    uvicorn.run(app, host="0.0.0.0", port=PORT)
