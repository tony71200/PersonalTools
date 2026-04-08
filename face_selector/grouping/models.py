from __future__ import annotations

from PIL import Image

from .types import Config, RuntimeModels
from .utils import log

try:
    from insightface.app import FaceAnalysis
except Exception as exc:  # pragma: no cover
    raise RuntimeError(
        "Không import được insightface. Cài: pip install insightface onnxruntime hoặc onnxruntime-gpu"
    ) from exc


def load_models(cfg: Config) -> RuntimeModels:
    det_exc = None
    try:
        det_model = FaceAnalysis(name=cfg.det_model_name, providers=["CUDAExecutionProvider", "CPUExecutionProvider"])
        det_model.prepare(ctx_id=0, det_size=cfg.det_size)
    except Exception as exc:
        det_exc = exc
        det_model = FaceAnalysis(name=cfg.det_model_name, providers=["CPUExecutionProvider"])
        det_model.prepare(ctx_id=0, det_size=cfg.det_size)

    clip_model = None
    clip_processor = None
    clip_device = "cpu"
    clip_enabled = False

    if cfg.enable_clip:
        try:
            import torch
            from transformers import CLIPImageProcessor, CLIPModel

            clip_device = "cuda" if torch.cuda.is_available() else "cpu"
            clip_model = CLIPModel.from_pretrained(
                cfg.clip_model_name,
                cache_dir=cfg.clip_cache_dir,
                use_safetensors=True,
            ).to(clip_device).eval()
            clip_processor = CLIPImageProcessor.from_pretrained(
                cfg.clip_model_name,
                cache_dir=cfg.clip_cache_dir,
            )
            clip_enabled = True
        except Exception as exc:
            log(f"[WARN] Không load được CLIP, fallback không semantic grouping: {exc}", cfg.verbose)

    faiss_enabled = False
    if cfg.enable_faiss:
        try:
            import faiss  # noqa: F401
            faiss_enabled = True
        except Exception as exc:
            log(f"[WARN] Không load được FAISS, fallback grouping thường: {exc}", cfg.verbose)

    if det_exc is not None:
        log(f"[WARN] InsightFace CUDA fallback CPU: {det_exc}", cfg.verbose)

    return RuntimeModels(
        det_model=det_model,
        clip_model=clip_model,
        clip_processor=clip_processor,
        clip_device=clip_device,
        clip_enabled=clip_enabled,
        faiss_enabled=faiss_enabled,
    )


def read_rgb_pil(path):
    with Image.open(path) as img:
        return img.convert("RGB").copy()
