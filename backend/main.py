import asyncio
import json
import os
import shutil
import threading
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from database import (
    init_db,
    insert_upload,
    insert_meal_items,
    get_history,
    get_meal,
    update_meal_correction,
    delete_meal,
    clear_history,
)
from pipeline import run_pipeline, get_macros_for_food
from segment_client import SegmentServiceUnavailable

_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()


def _add_job_event(job_id: str, event_type: str, data: dict) -> None:
    with _jobs_lock:
        if job_id in _jobs:
            _jobs[job_id]["events"].append({"type": event_type, "data": data})
            if event_type in ("result", "error"):
                _jobs[job_id]["status"] = "done" if event_type == "result" else "error"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="FoodVision API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = Path(__file__).parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)


def _build_upload_payload(path: Path, result: dict) -> dict:
    """Build the same payload as the legacy synchronous upload response."""
    annotated_path_str = result.get("annotated_image_path")
    image_path_for_db = annotated_path_str or str(path)
    if annotated_path_str and annotated_path_str != str(path):
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass

    totals = result["totals"]
    items = result["items"]
    first_label = result.get("original_label") or (items[0]["name"] if items else "")
    corrected_label = items[0]["name"] if items else ""

    meal_id = insert_upload(
        image_path=image_path_for_db,
        original_label=first_label,
        corrected_label=corrected_label,
        calories=totals["calories"],
        protein=totals["protein"],
        carbs=totals["carbs"],
        fat=totals["fat"],
        raw_response=result.get("raw_response"),
    )
    insert_meal_items(meal_id, items)

    response_items = []
    for it in items:
        resp_item = {"name": it["name"], "quantity": it["quantity"], "macros": it["macros"]}
        if it.get("segment_image_path"):
            resp_item["segment_image_url"] = f"/api/uploads/{Path(it['segment_image_path']).name}"
        response_items.append(resp_item)

    payload = {
        "meal_id": meal_id,
        "image_path": image_path_for_db,
        "image_url": f"/api/uploads/{Path(image_path_for_db).name}",
        "totals": totals,
        "items": response_items,
        "regions": result.get("regions", []),
        "original_label": result.get("original_label"),
    }
    if result.get("annotated_image_path"):
        payload["annotated_image_url"] = f"/api/uploads/{Path(result['annotated_image_path']).name}"
    return payload


DEEP_SCAN_UNAVAILABLE_MSG = "Deep Scan engine is currently unavailable. Please use Fast Scan."


def _run_job(job_id: str, path: Path, scan_mode: str = "fast") -> None:
    def on_progress(stage: str, progress: int) -> None:
        _add_job_event(job_id, "progress", {"stage": stage, "progress": progress})

    try:
        result = run_pipeline(path, progress_callback=on_progress, scan_mode=scan_mode)
        payload = _build_upload_payload(path, result)
        _add_job_event(job_id, "result", payload)
    except SegmentServiceUnavailable:
        _add_job_event(job_id, "error", {"message": DEEP_SCAN_UNAVAILABLE_MSG})
    except Exception as e:
        _add_job_event(job_id, "error", {"message": str(e)})


@app.post("/api/upload")
async def upload_and_analyze(
    file: UploadFile = File(...),
    scan_mode: str = Form("fast"),
):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(400, "File must be an image")

    scan_mode = (scan_mode or "fast").strip().lower()
    if scan_mode not in ("fast", "deep"):
        scan_mode = "fast"

    if scan_mode == "deep":
        api_url = os.getenv("DEEP_SCAN_API_URL", "").strip()
        if not api_url:
            raise HTTPException(
                503,
                detail=DEEP_SCAN_UNAVAILABLE_MSG,
            )

    ext = Path(file.filename or "img").suffix or ".jpg"
    path = UPLOAD_DIR / f"{uuid.uuid4().hex}{ext}"
    try:
        with path.open("wb") as f:
            shutil.copyfileobj(file.file, f)
    except Exception as e:
        raise HTTPException(500, f"Failed to save file: {e}")

    job_id = uuid.uuid4().hex
    with _jobs_lock:
        _jobs[job_id] = {"status": "running", "events": []}

    thread = threading.Thread(target=_run_job, args=(job_id, path, scan_mode), daemon=True)
    thread.start()

    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}/progress")
async def job_progress_sse(job_id: str):
    with _jobs_lock:
        if job_id not in _jobs:
            raise HTTPException(404, "Job not found")

    async def event_stream():
        last_sent = 0
        poll_interval = 0.2
        timeout_sec = 150
        waited = 0.0
        while waited < timeout_sec:
            await asyncio.sleep(poll_interval)
            waited += poll_interval
            with _jobs_lock:
                if job_id not in _jobs:
                    break
                job = _jobs[job_id]
                events_list = job["events"]
            for i in range(last_sent, len(events_list)):
                ev = events_list[i]
                payload = json.dumps({"type": ev["type"], **ev["data"]})
                yield f"data: {payload}\n\n"
                if ev["type"] in ("result", "error"):
                    return
            last_sent = len(events_list)
            with _jobs_lock:
                if job_id in _jobs and _jobs[job_id]["status"] != "running":
                    break
        yield "data: " + json.dumps({"type": "error", "message": "Request timed out"}) + "\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-store",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


class CorrectBody(BaseModel):
    meal_id: int
    new_label: str


@app.post("/api/correct")
def correct_meal(body: CorrectBody):
    new_label = (body.new_label or "").strip()
    if not new_label:
        raise HTTPException(400, "new_label is required and cannot be empty")

    meal = get_meal(body.meal_id)
    if not meal:
        raise HTTPException(404, f"Meal {body.meal_id} not found")

    item_result = get_macros_for_food(new_label, quantity=1.0)
    items = [
        {
            "name": item_result["name"],
            "quantity": item_result["quantity"],
            "macros": item_result["macros"],
        }
    ]
    totals = {
        "calories": item_result["macros"]["calories"],
        "protein": item_result["macros"]["protein"],
        "carbs": item_result["macros"]["carbs"],
        "fat": item_result["macros"]["fat"],
    }

    update_meal_correction(
        meal_id=body.meal_id,
        corrected_label=item_result["name"],
        calories=totals["calories"],
        protein=totals["protein"],
        carbs=totals["carbs"],
        fat=totals["fat"],
        items=items,
    )

    return {
        "status": "success",
        "totals": totals,
        "items": items,
    }


@app.get("/api/history")
def history(limit: int = 50):
    items = get_history(limit=limit)
    for item in items:
        if item.get("image_path"):
            item["image_url"] = f"/api/uploads/{Path(item['image_path']).name}"
    return {"items": items}


@app.delete("/api/history/{meal_id}")
def delete_history_item(meal_id: int):
    image_paths = delete_meal(meal_id)
    for p in image_paths:
        try:
            img_path = Path(p)
            img_path.unlink(missing_ok=True)
        except Exception:
            pass
    return {"status": "deleted", "meal_id": meal_id}


@app.delete("/api/history")
def clear_history_endpoint():
    image_paths = clear_history()
    for p in image_paths:
        try:
            img_path = Path(p)
            img_path.unlink(missing_ok=True)
        except Exception:
            pass
    return {"status": "cleared"}


@app.get("/api/health")
def health():
    return {"status": "ok"}


app.mount("/api/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")
