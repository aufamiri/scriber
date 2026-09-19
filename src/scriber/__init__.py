import os

import debugpy
import pymupdf
from PIL import Image
from surya.inference import SuryaInferenceManager
from surya.layout import LayoutPredictor


def main() -> None:
    # Open a port for IntelliJ to connect to
    # debugpy.listen(("127.0.0.1", 5399))
    # print(" Waiting for IntelliJ debugger to attach on port 5678...")
    # debugpy.wait_for_client()  # This pauses execution until you connect

    temp_folder_path = '/Volumes/hippocampus/projects/scriber/test-data/temp'
    try:
        os.makedirs(temp_folder_path, exist_ok=True)
    except OSError as e:
        print(f"error: failed to create temp folder: {e}")
        return

    layout_predictor = LayoutPredictor(SuryaInferenceManager())

    file_dest_path = []
    layout_predictions_result = []
    try:
        doc = pymupdf.open("/Volumes/hippocampus/projects/scriber/test-data/Bumi.pdf")
    except Exception as e:
        print(f"error: failed to open PDF: {e}")
        return
    # TODO: get pdf title from here

    for i, page in enumerate(doc.pages()):
        # TODO: somehow get the doc DPI here
        pix = page.get_pixmap(dpi=200)
        # TODO: new ideas, maybe instead of saving to png, we can directly insert this into surya ?
        temp_file_dest = os.path.join(temp_folder_path, f'page{i}.png')
        pix.save(temp_file_dest)
        file_dest_path.append(temp_file_dest)

    for file_path in file_dest_path:
        layout_predictions = layout_predictor([Image.open(file_path)])
        layout_predictions_result.append(layout_predictions)

    doc.close()
