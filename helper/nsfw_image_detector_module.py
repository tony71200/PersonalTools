from __future__ import annotations

import os
from typing import Tuple

from PIL import Image

from model_base import ModelLoadError, ModelModuleBase


class NSFWImageDetectorModule(ModelModuleBase):
    """Wrapper around the ``nsfw_image_detector`` package."""

    def __init__(self):
        self.detector = None

    @property
    def name(self) -> str:
        return "nsfw_image_detector"

    def load(self) -> None:
        try:
            from nsfw_image_detector import NSFWDetector  # type: ignore
        except Exception as exc:  # pragma: no cover - import safety
            raise ModelLoadError(f"Không thể import nsfw_image_detector: {exc}") from exc

        try:
            self.detector = NSFWDetector()
        except Exception as exc:
            raise ModelLoadError(f"Lỗi khởi tạo NSFWDetector: {exc}") from exc

    def check_image(self, image_path: str) -> Tuple[bool, bool, dict]:
        if self.detector is None:
            raise RuntimeError("Module chưa được load.")

        image = Image.open(image_path)
        proba_dict = self.detector.predict_proba(image)[0]
        high_risk = proba_dict.get("high", 0)
        medium_risk = proba_dict.get("medium", 0)
        low_risk = proba_dict.get("low", 0)

        is_unsafe = high_risk > 0.7 and medium_risk > 0.6 and low_risk > 0.5
        is_low_risk = low_risk > 0.9
        return is_unsafe, is_low_risk, proba_dict


def ensure_default_weights():  # pragma: no cover - helper only
    """Convenience helper to describe expected weight location if needed."""
    expected_files = ["saved_model.tflite", "640m.onnx"]
    missing = [f for f in expected_files if not os.path.exists(f)]
    if missing:
        print(f"Thiếu file model: {', '.join(missing)}")
