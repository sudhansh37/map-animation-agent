"""Optional local open-source text-to-image (SD-Turbo on CPU).

Runs entirely locally / inside GitHub Actions - no paid image API. It is
off by default (ENABLE_IMAGE_GEN=false) and is always best-effort: if it
fails, the pipeline simply continues with the map scenes only.
"""
import os
from pathlib import Path

_PIPE = None
MODEL_ID = "stabilityai/sd-turbo"


def enabled() -> bool:
    return os.getenv("ENABLE_IMAGE_GEN", "false").strip().lower() in ("1", "true", "yes")


def _pipe():
    global _PIPE
    if _PIPE is None:
        import torch
        from diffusers import AutoPipelineForText2Image

        _PIPE = AutoPipelineForText2Image.from_pretrained(MODEL_ID, torch_dtype=torch.float32)
        _PIPE.set_progress_bar_config(disable=True)
        _PIPE.to("cpu")
    return _PIPE


def generate(prompt: str, out_path, width: int = 512, height: int = 768) -> str | None:
    """Generate one image. Returns the path, or None on any failure."""
    try:
        pipe = _pipe()
        image = pipe(
            prompt=prompt,
            num_inference_steps=2,
            guidance_scale=0.0,
            width=width,
            height=height,
        ).images[0]
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        image.save(out_path)
        return str(out_path)
    except Exception as exc:  # noqa: BLE001 - never break the video for this
        print(f"[image_engine] Skipping image ({exc})")
        return None
