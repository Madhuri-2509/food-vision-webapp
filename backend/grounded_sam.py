
from __future__ import annotations

from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image

_grounding_dino_processor = None
_grounding_dino_model = None
_sam_processor = None
_sam_model = None
_device = None


def _get_device():
    global _device
    if _device is None:
        try:
            import torch
            _device = "cuda" if torch.cuda.is_available() else "cpu"
        except Exception:
            _device = "cpu"
    return _device


def _load_grounding_dino():
    global _grounding_dino_processor, _grounding_dino_model
    if _grounding_dino_model is not None:
        return
    import torch
    from transformers import AutoProcessor, AutoModelForZeroShotObjectDetection
    model_id = "IDEA-Research/grounding-dino-tiny"
    _grounding_dino_processor = AutoProcessor.from_pretrained(model_id)
    _grounding_dino_model = AutoModelForZeroShotObjectDetection.from_pretrained(model_id).to(_get_device())
    _grounding_dino_model.eval()


def _load_sam():
    global _sam_processor, _sam_model
    if _sam_model is not None:
        return
    import torch
    from transformers import SamModel, SamProcessor
    model_id = "facebook/sam-vit-base" 
    _sam_processor = SamProcessor.from_pretrained(model_id)
    _sam_model = SamModel.from_pretrained(model_id).to(_get_device())
    _sam_model.eval()


def preload_grounded_sam() -> None:
    _load_grounding_dino()
    _load_sam()


def _get_boxes_grounding_dino(image: Image.Image, text_prompt: str, box_threshold: float = 0.35):
    _load_grounding_dino()
    import torch
    text_labels = [[t.strip() for t in text_prompt.split(".") if t.strip()]]
    inputs = _grounding_dino_processor(images=image, text=text_labels, return_tensors="pt").to(_grounding_dino_model.device)
    with torch.no_grad():
        outputs = _grounding_dino_model(**inputs)
    h, w = image.size[1], image.size[0]
    results = _grounding_dino_processor.post_process_grounded_object_detection(
        outputs,
        inputs["input_ids"],
        threshold=box_threshold,
        target_sizes=[(h, w)],
    )
    result = results[0]
    boxes = result["boxes"].cpu().numpy()
    scores = result["scores"].cpu().numpy()
    return boxes, scores


def _get_masks_sam(image: Image.Image, boxes_xyxy: np.ndarray):
    _load_sam()
    import torch
    h, w = np.array(image).shape[:2]
    masks_list = []
    for box in boxes_xyxy:
        x1, y1, x2, y2 = box
        pad = 2
        x1 = max(0, x1 - pad)
        y1 = max(0, y1 - pad)
        x2 = min(w, x2 + pad)
        y2 = min(h, y2 + pad)
        input_boxes = [[[x1, y1, x2, y2]]]
        inputs = _sam_processor(image, input_boxes=input_boxes, return_tensors="pt").to(_sam_model.device)
        with torch.no_grad():
            outputs = _sam_model(**inputs)
        masks = _sam_processor.image_processor.post_process_masks(
            outputs.pred_masks.cpu(),
            inputs["original_sizes"].cpu(),
            inputs["reshaped_input_sizes"].cpu(),
        )
        mask = masks[0].squeeze().numpy()
        if mask.ndim == 3:
            mask = mask[0]
        mask_pil = Image.fromarray((mask > 0).astype(np.uint8) * 255).resize((w, h), Image.BILINEAR)
        mask_np = (np.array(mask_pil) > 127).astype(bool)
        masks_list.append(mask_np)
    return masks_list


def run_grounded_sam(
    image_path: str | Path,
    output_dir: str | Path,
    text_prompt: str = "food . dish . plate . bowl . meal . sandwich . burger . fries . pizza .",
    box_threshold: float = 0.35,
    min_box_area: int = 500,
) -> dict[str, Any]:
    path = Path(image_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    image_pil = Image.open(path).convert("RGB")
    image_np = np.array(image_pil)
    h, w = image_np.shape[:2]

    boxes_xyxy, scores = _get_boxes_grounding_dino(image_pil, text_prompt, box_threshold)
    if len(boxes_xyxy) == 0:
        return {"crop_paths": [path], "regions": [{"bbox": [0, 0, w, h]}]}

    areas = (boxes_xyxy[:, 2] - boxes_xyxy[:, 0]) * (boxes_xyxy[:, 3] - boxes_xyxy[:, 1])
    keep = areas >= min_box_area
    boxes_xyxy = boxes_xyxy[keep]
    scores = scores[keep]
    if len(boxes_xyxy) == 0:
        return {"crop_paths": [path], "regions": [{"bbox": [0, 0, w, h]}]}

    try:
        masks_list = _get_masks_sam(image_pil, boxes_xyxy)
    except Exception:
        masks_list = [None] * len(boxes_xyxy)

    crop_paths = []
    regions = []
    stem = path.stem
    ext = path.suffix or ".jpg"

    for i, (box, mask) in enumerate(zip(boxes_xyxy, masks_list)):
        x1, y1, x2, y2 = [int(round(x)) for x in box]
        x1, x2 = max(0, x1), min(w, x2)
        y1, y2 = max(0, y1), min(h, y2)
        if x2 <= x1 or y2 <= y1:
            continue
        region = {"bbox": [float(x1), float(y1), float(x2), float(y2)]}
        if mask is not None:
            region["mask"] = mask  

        if mask is not None:
            crop = image_np.copy()
            crop[~mask] = 255 
            crop = crop[y1:y2, x1:x2]
            mask_crop = mask[y1:y2, x1:x2]
            crop[~mask_crop] = 255
        else:
            crop = image_np[y1:y2, x1:x2]
        crop_path = output_dir / f"{stem}_seg_{i}{ext}"
        cv2.imwrite(str(crop_path), cv2.cvtColor(crop, cv2.COLOR_RGB2BGR))
        crop_paths.append(crop_path)
        regions.append(region)

    if not crop_paths:
        return {"crop_paths": [path], "regions": [{"bbox": [0, 0, w, h]}]}
    return {"crop_paths": crop_paths, "regions": regions}
