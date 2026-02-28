import os
import base64
import concurrent.futures
import shutil
import uuid
import requests
from pathlib import Path
from typing import Callable
from dotenv import load_dotenv
import cv2
import numpy as np
from PIL import Image
import supervision as sv

from database import (
    normalize_food_name,
    get_food_from_cache,
    insert_food_cache,
)

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_BASE = "https://openrouter.ai/api/v1"
USDA_API_KEY = os.getenv("USDA_API_KEY")
USDA_BASE = "https://api.nal.usda.gov/fdc/v1"
BASE_UNIT = "100g"
FAST_SCAN_MODEL = os.getenv("FAST_SCAN_MODEL", "openai/gpt-4o")
DEEP_SCAN_MODEL = os.getenv("DEEP_SCAN_MODEL", "qwen/qwen-vl-plus")

NON_FOOD_BLOCKLIST = {
    "plate", "plates", "non_food", "table", "cutlery", "fork", "knife", "spoon",
    "napkin", "container", "bowl", "cup", "glass", "unknown",
}


def _titanium_trapdoor(label: str) -> bool:
    key = normalize_food_name(label)
    if not key:
        return True
    return key in NON_FOOD_BLOCKLIST


def segment_food(image_path: str | Path, output_dir: str | Path | None = None) -> dict:
    path = Path(image_path)
    output_dir = Path(output_dir) if output_dir else path.parent
    use_grounded_sam = os.getenv("GROUNDED_SAM_ENABLED", "").strip().lower() in ("1", "true", "yes")

    if use_grounded_sam:
        try:
            from grounded_sam import run_grounded_sam
            out = run_grounded_sam(str(path), output_dir)
            return out
        except Exception:
            pass
    crop_paths = []
    regions = []
    try:
        with Image.open(path) as im:
            w, h = im.size
        crop_paths.append(path)
        regions.append({"bbox": [0, 0, w, h]})
    except Exception:
        crop_paths.append(path)
        regions.append({"bbox": [0, 0, 1, 1]})
    return {"crop_paths": crop_paths, "regions": regions}


_MASK_PALETTE_HEX = [
    "#8b5cf6", "#ec4899", "#10b981", "#f59e0b", "#3b82f6",
    "#ef4444", "#14b8a6", "#a855f7",
]


def draw_segmentation_on_image(
    image_path: str | Path,
    regions: list[dict],
    labels: list[str],
    output_path: str | Path,
) -> Path:
    path = Path(image_path)
    out = Path(output_path)
    image = cv2.imread(str(path))
    if image is None:
        raise ValueError(f"Could not read image: {path}")

    if not regions:
        cv2.imwrite(str(out), image)
        return out

    xyxy = np.array([r["bbox"] for r in regions], dtype=np.float32)
    masks = None
    if all(isinstance(r.get("mask"), np.ndarray) for r in regions):
        masks = np.stack([r["mask"] for r in regions]).astype(bool)
    detections = sv.Detections(
        xyxy=xyxy,
        mask=masks,
        class_id=np.arange(len(xyxy)),
        confidence=np.ones(len(xyxy)),
    )

    scene = image.copy()
    if detections.mask is not None:
        for i in range(len(detections)):
            single = sv.Detections(
                xyxy=detections.xyxy[i : i + 1],
                mask=detections.mask[i : i + 1],
                class_id=detections.class_id[i : i + 1],
                confidence=detections.confidence[i : i + 1],
            )
            color_hex = _MASK_PALETTE_HEX[i % len(_MASK_PALETTE_HEX)]
            mask_annotator = sv.MaskAnnotator(color=sv.Color.from_hex(color_hex), opacity=0.4)
            scene = mask_annotator.annotate(scene=scene, detections=single)
        detections = sv.Detections(
            xyxy=xyxy,
            mask=masks,
            class_id=np.arange(len(xyxy)),
            confidence=np.ones(len(xyxy)),
        )
    box_annotator = sv.BoxAnnotator(color=sv.Color.from_hex("#10b981"), thickness=2)
    scene = box_annotator.annotate(scene=scene, detections=detections)

    if labels and len(labels) == len(regions):
        label_annotator = sv.LabelAnnotator(
            text_scale=0.5,
            text_thickness=1,
            text_position=sv.Position.TOP_LEFT,
        )
        display_labels = [lbl.replace("_", " ").strip() for lbl in labels]
        scene = label_annotator.annotate(
            scene=scene,
            detections=detections,
            labels=display_labels,
        )

    cv2.imwrite(str(out), scene)
    return out


def image_to_base64(path: str | Path) -> str:
    with open(path, "rb") as f:
        return base64.standard_b64encode(f.read()).decode("utf-8")


def get_food_label_from_image(
    image_path: str | Path,
    model: str | None = None,
) -> str:
    if not OPENROUTER_API_KEY:
        return "NON_FOOD"

    model = model or FAST_SCAN_MODEL
    b64 = image_to_base64(image_path)
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Identify the edible food in this image. Reply ONLY with a comma-separated list of the core food items (e.g., 'burger, french fries, soda'). If there is absolutely no edible food in the image, reply EXACTLY with 'NON_FOOD'.",
                    },
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                ],
            }
        ],
        "max_tokens": 64,
        "temperature": 0.1,
    }
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }
    try:
        r = requests.post(f"{OPENROUTER_BASE}/chat/completions", json=payload, headers=headers, timeout=30)
        r.raise_for_status()
        data = r.json()
        label = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        return label or "NON_FOOD"
    except Exception:
        return "NON_FOOD"


def _fetch_macros_from_usda(label: str) -> tuple[str, float, float, float, float, str, bool]:
    raw_response = ""
    corrected = label
    calories = protein = carbs = fat = 0.0
    macros_incomplete = False

    def _query_usda(query: str) -> tuple[str, float, float, float, float, str]:
        local_raw = ""
        local_corrected = query
        cal = prot = carb = fat_val = 0.0
        if not USDA_API_KEY:
            return local_corrected, cal, prot, carb, fat_val, local_raw
        try:
            r = requests.get(
                f"{USDA_BASE}/foods/search",
                params={"api_key": USDA_API_KEY, "query": query, "pageSize": 1},
                timeout=10,
            )
            r.raise_for_status()
            data = r.json()
            local_raw = str(data)
            foods = data.get("foods", [])
            if foods:
                f = foods[0]
                local_corrected = f.get("description", query)
                nutrients = {n.get("nutrientName"): n.get("value") for n in f.get("foodNutrients", [])}
                cal = float(nutrients.get("Energy", 0) or 0)
                prot = float(nutrients.get("Protein", 0) or 0)
                carb = float(nutrients.get("Carbohydrate, by difference", 0) or 0)
                fat_val = float(nutrients.get("Total lipid (fat)", 0) or 0)
        except Exception as e:
            local_raw = str(e)
        return local_corrected, cal, prot, carb, fat_val, local_raw

    human_label = label.replace("_", " ").strip() or label
    corrected, calories, protein, carbs, fat, raw_response = _query_usda(human_label)

    if calories == 0.0 and protein == 0.0 and carbs == 0.0 and fat == 0.0:
        parts = human_label.split()
        if len(parts) > 1:
            simple = parts[-1]
            corrected2, cal2, prot2, carb2, fat2, raw2 = _query_usda(simple)
            if any(v != 0.0 for v in (cal2, prot2, carb2, fat2)):
                corrected, calories, protein, carbs, fat = corrected2, cal2, prot2, carb2, fat2
                raw_response = raw2

    if calories == 0.0 and protein == 0.0 and carbs == 0.0 and fat == 0.0:
        macros_incomplete = True

    return corrected, calories, protein, carbs, fat, raw_response, macros_incomplete


def get_macros_for_food(label: str, quantity: float = 1.0) -> dict:
    key = normalize_food_name(label)
    if not key:
        key = "unknown"

    cached = get_food_from_cache(key)
    if cached:
        c = cached
        corrected = c["corrected_label"]
        cal = c["calories"] * quantity
        prot = c["protein"] * quantity
        carb = c["carbs"] * quantity
        fat_g = c["fat"] * quantity
        return {
            "name": key,
            "quantity": quantity,
            "macros": {"calories": cal, "protein": prot, "carbs": carb, "fat": fat_g},
            "raw_response": "",
            "macros_incomplete": False,
        }

    corrected, cal_100, prot_100, carb_100, fat_100, raw_response, macros_incomplete = _fetch_macros_from_usda(label)
    insert_food_cache(
        name=key,
        corrected_label=corrected,
        calories=cal_100,
        protein=prot_100,
        carbs=carb_100,
        fat=fat_100,
        base_unit=BASE_UNIT,
    )

    return {
        "name": key,
        "quantity": quantity,
        "macros": {
            "calories": cal_100 * quantity,
            "protein": prot_100 * quantity,
            "carbs": carb_100 * quantity,
            "fat": fat_100 * quantity,
        },
        "raw_response": raw_response,
        "macros_incomplete": macros_incomplete,
    }


def run_pipeline(
    image_path: str | Path,
    progress_callback: Callable[[str, int], None] | None = None,
    scan_mode: str = "fast",
) -> dict:
    def report(stage: str, pct: int) -> None:
        if progress_callback:
            progress_callback(stage, pct)

    path = Path(image_path)
    output_dir = path.parent

    if scan_mode == "deep":
        return _run_pipeline_deep(path, output_dir, report)

    report("Analyzing image…", 10)
    original_label = get_food_label_from_image(path, model=FAST_SCAN_MODEL)

    report("Identifying food…", 45)

    if "NON_FOOD" in original_label.upper():
        return {
            "original_label": "Non-Food Item Detected",
            "items": [],
            "totals": {"calories": 0.0, "protein": 0.0, "carbs": 0.0, "fat": 0.0},
            "regions": [],
            "annotated_image_path": None,
            "raw_response": "The AI determined there is no edible food in this image.",
        }

    raw_labels = [label.strip() for label in original_label.split(",") if label.strip()]
    n_labels = len(raw_labels)

    items = []
    for i, label in enumerate(raw_labels):
        report("Looking up nutrition…", 50 + int((i / max(1, n_labels)) * 45))
        item_result = get_macros_for_food(label, quantity=1.0)
        items.append({
            "name": item_result["name"],
            "quantity": item_result["quantity"],
            "macros": item_result["macros"],
        })

    report("Done", 100)

    totals = {
        "calories": sum(i["macros"]["calories"] for i in items),
        "protein": sum(i["macros"]["protein"] for i in items),
        "carbs": sum(i["macros"]["carbs"] for i in items),
        "fat": sum(i["macros"]["fat"] for i in items),
    }

    return {
        "original_label": original_label,
        "items": items,
        "totals": totals,
        "regions": [],
        "annotated_image_path": None,
        "raw_response": f"AI detected: {original_label}",
    }


def _run_pipeline_deep(
    image_path: Path,
    output_dir: Path,
    report: Callable[[str, int], None],
) -> dict:
    from segment_client import segment_image_via_hf, SegmentServiceUnavailable

    report("Isolating items…", 5)
    try:
        annotated_img_str, crop_paths = segment_image_via_hf(str(image_path))
    except SegmentServiceUnavailable:
        raise
        
    annotated_src = Path(annotated_img_str)

    annotated_dst = output_dir / f"annotated_{image_path.stem}_{uuid.uuid4().hex[:8]}{annotated_src.suffix}"
    shutil.copy2(annotated_src, annotated_dst)

    copied_crops = []
    for i, cp in enumerate(crop_paths):
        dst = output_dir / f"crop_{image_path.stem}_{i}_{uuid.uuid4().hex[:6]}{Path(cp).suffix}"
        shutil.copy2(cp, dst)
        copied_crops.append(dst)

    if not copied_crops:
        report("Done", 100)
        return {
            "original_label": "No food segments detected",
            "items": [],
            "totals": {"calories": 0.0, "protein": 0.0, "carbs": 0.0, "fat": 0.0},
            "regions": [],
            "annotated_image_path": str(annotated_dst),
            "raw_response": "Segmentation found no distinct food regions.",
        }

    report("Identifying food…", 40)

    def process_single_crop(crop_path):
        label = get_food_label_from_image(crop_path, model=DEEP_SCAN_MODEL)
        local_items = []
        if "NON_FOOD" not in label.upper():
            for raw in (p.strip() for p in label.split(",") if p.strip()):
                key = normalize_food_name(raw)
                if not key or _titanium_trapdoor(raw):
                    continue
                item_result = get_macros_for_food(raw, quantity=1.0)
                local_items.append({
                    "name": item_result["name"],
                    "quantity": item_result["quantity"],
                    "macros": item_result["macros"],
                })
        return local_items

    items = []
    seen = set()
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        results = executor.map(process_single_crop, copied_crops)
        for result_list in results:
            for item in result_list:
                key = normalize_food_name(item["name"])
                if key and key not in seen:
                    seen.add(key)
                    items.append(item)

    if not items:
        report("Done", 100)
        return {
            "original_label": "No edible food detected in segments",
            "items": [],
            "totals": {"calories": 0.0, "protein": 0.0, "carbs": 0.0, "fat": 0.0},
            "regions": [],
            "annotated_image_path": str(annotated_dst),
            "raw_response": "AI did not identify edible food in the segmented regions.",
        }

    all_labels = [i["name"] for i in items]

    report("Done", 100)

    totals = {
        "calories": sum(i["macros"]["calories"] for i in items),
        "protein": sum(i["macros"]["protein"] for i in items),
        "carbs": sum(i["macros"]["carbs"] for i in items),
        "fat": sum(i["macros"]["fat"] for i in items),
    }

    return {
        "original_label": ", ".join(all_labels),
        "items": items,
        "totals": totals,
        "regions": [],
        "annotated_image_path": str(annotated_dst),
        "raw_response": f"Deep Scan detected: {', '.join(all_labels)}",
    }

