from __future__ import annotations

from typing import Tuple

from model_base import ModelLoadError, ModelModuleBase


class NudenetModule(ModelModuleBase):
    """Placeholder NudeNet-based detector.

    Real implementation can swap in NudeNet classifier safely thanks to the
    shared interface.
    """

    @property
    def name(self) -> str:
        return "nudenet"

    def load(self) -> None:
        try:
            import nudenet  # noqa: F401  # pragma: no cover - optional dep
        except Exception as exc:
            raise ModelLoadError("Thiếu dependency nudenet hoặc chưa cài đặt.") from exc

        raise ModelLoadError("Module NudeNet chưa được triển khai logic inference.")

    def check_image(self, image_path: str) -> Tuple[bool, bool, dict]:  # pragma: no cover - not used until implemented
        raise RuntimeError("Module NudeNet chưa load thành công hoặc chưa triển khai.")
