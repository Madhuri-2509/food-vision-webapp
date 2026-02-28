from gradio_client import Client, handle_file
from PIL import Image
import shutil
import os

HF_SPACE_URL = "project-desk/food-segmentation-engine"

class SegmentServiceUnavailable(Exception):
    pass

def segment_image_via_hf(local_image_path: str):

    print(f"Connecting to Hugging Face Space: {HF_SPACE_URL}...")

    compressed_path = None
    try:
        base, ext = os.path.splitext(local_image_path)
        compressed_path = f"{base}_compressed.jpg"
        with Image.open(local_image_path) as img:
            img.thumbnail((800, 800))
            if img.mode != "RGB":
                img = img.convert("RGB")
            img.save(compressed_path, format="JPEG", quality=85)

        client = Client(HF_SPACE_URL)

        result = client.predict(
            image_path=handle_file(compressed_path),
            api_name="/process_image",
        )
        
        if isinstance(result[0], dict):
            annotated_tmp_path = result[0].get('path')
        else:
            annotated_tmp_path = result[0]
            
        raw_crops = result[1]
        clean_crops = []
        
        if isinstance(raw_crops, (list, tuple)):
            for c in raw_crops:
                if isinstance(c, dict):
                    clean_crops.append(c.get('path', c.get('name')))
                else:
                    clean_crops.append(c)
        elif isinstance(raw_crops, str):
            clean_crops.append(raw_crops)
            
        if not clean_crops:
            print("⚠️ No food items detected by Grounded-SAM.")
            return annotated_tmp_path, []


        if not annotated_tmp_path or not os.path.exists(annotated_tmp_path):
            print(f"❌ Error: Gradio temp file missing! Path: {annotated_tmp_path}")
            raise SegmentServiceUnavailable("Image generation failed on cloud.")

        filename = os.path.basename(str(local_image_path))
        base_dir = os.path.dirname(os.path.abspath(local_image_path))
        annotated_final_path = os.path.join(base_dir, f"annotated_{filename}")
        os.makedirs(base_dir, exist_ok=True)

        print(f"📦 Moving masked image to: {annotated_final_path}")
        shutil.copy(annotated_tmp_path, annotated_final_path)

        return annotated_final_path, clean_crops

    except Exception as e:
        print(f"❌ HF Segmentation API Error: {e}")
        raise SegmentServiceUnavailable("Deep Scan engine is currently unavailable. Please use Fast Scan.")
    finally:
        if compressed_path and os.path.exists(compressed_path):
            try:
                os.remove(compressed_path)
            except OSError:
                pass