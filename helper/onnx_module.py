from __future__ import annotations

from typing import Tuple

from model_base import ModelLoadError, ModelModuleBase


class OnnxModule(ModelModuleBase):
    """Placeholder ONNX-based detector.

    This module is structured so real ONNX runtime logic can be plugged in
    later. For now it fails fast with a clear error to keep the UI responsive.
    """

    @property
    def name(self) -> str:
        return "onnx_runtime"

    def load(self) -> None:
        # Deferred import to keep startup resilient if dependencies are missing.
        try:
            import onnxruntime  # noqa: F401  # pragma: no cover - optional dep
        except Exception as exc:
            raise ModelLoadError(
                "Thiếu dependency onnxruntime hoặc chưa được cấu hình."
            ) from exc

        raise ModelLoadError("Module ONNX chưa được triển khai logic inference.")

    def check_image(self, image_path: str) -> Tuple[bool, bool, dict]:  # pragma: no cover - not used until implemented
        raise RuntimeError("Module ONNX chưa load thành công hoặc chưa triển khai.")
