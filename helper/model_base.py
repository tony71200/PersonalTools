from __future__ import annotations

import abc
from typing import Tuple


class ModelLoadError(RuntimeError):
    """Raised when a model module cannot be loaded."""


class ModelModuleBase(abc.ABC):
    """Abstract base for model modules.

    Implementations should lazy-load heavy dependencies inside ``load`` to avoid
    blocking application startup if imports fail. ``check_image`` must return a
    tuple ``(is_unsafe, is_low_risk, proba_dict)`` similar to the existing
    pipeline.
    """

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Human readable module name."""

    @abc.abstractmethod
    def load(self) -> None:
        """Load model resources.

        Should raise ``ModelLoadError`` on failure so the UI can continue
        running without crashing.
        """

    @abc.abstractmethod
    def check_image(self, image_path: str) -> Tuple[bool, bool, dict]:
        """Run inference for an image.

        Returns ``is_unsafe``, ``is_low_risk``, and a probability dictionary.
        """

    def __repr__(self) -> str:  # pragma: no cover - convenience only
        return f"<ModelModule {self.name}>"
