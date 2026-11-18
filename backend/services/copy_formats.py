"""Clipboard formats for an image: ComfyUI workflow JSON, an A1111 `parameters` block and a LoRA stack."""

from __future__ import annotations

import json
import re
from typing import Any

from services.asset_viewer_metadata import coerce_bubba_metadata, has_bubba_generation_metadata

LORA_EXTENSION_PATTERN = re.compile(r"\.(safetensors|ckpt|pt|pth)$", re.IGNORECASE)


def _strength(value: float) -> str:
    return f"{float(value):g}"


def lora_stack(loras: list[str], strengths: list[list[float]]) -> str:
    """`<lora:name:weight>` tags, one per LoRA. A1111 takes text-encoder then UNet weight when they differ."""
    tags = []
    for index, raw_name in enumerate(loras or []):
        name = LORA_EXTENSION_PATTERN.sub("", str(raw_name).replace("\\", "/").rsplit("/", 1)[-1]).strip()
        if not name:
            continue
        model_strength, clip_strength = (strengths[index] if index < len(strengths) else None) or [1.0, 1.0]
        if float(model_strength) == float(clip_strength):
            tags.append(f"<lora:{name}:{_strength(model_strength)}>")
        else:
            tags.append(f"<lora:{name}:{_strength(clip_strength)}:{_strength(model_strength)}>")
    return " ".join(tags)


def _a1111_sampler(sampler: str, scheduler: str) -> str:
    sampler = str(sampler or "").strip()
    scheduler = str(scheduler or "").strip()
    if not sampler:
        return ""
    if scheduler and scheduler.lower() not in {"normal", "simple"}:
        return f"{sampler}_{scheduler}"
    return sampler


def a1111_parameters(metadata: dict[str, Any]) -> str:
    """An A1111-style `parameters` block from Bubba metadata (the LoRA stack is appended to the prompt)."""
    if not has_bubba_generation_metadata(metadata):
        return ""
    prompt = str(metadata.get("positive_prompt") or "").strip()
    stack = lora_stack(metadata.get("loras") or [], metadata.get("lora_strengths") or [])
    if stack and "<lora:" not in prompt:
        prompt = f"{prompt} {stack}".strip()
    lines = [prompt]
    negative = str(metadata.get("negative_prompt") or "").strip()
    if negative:
        lines.append(f"Negative prompt: {negative}")
    fields = []
    if metadata.get("steps"):
        fields.append(f"Steps: {metadata['steps']}")
    sampler = _a1111_sampler(metadata.get("sampler_name"), metadata.get("scheduler"))
    if sampler:
        fields.append(f"Sampler: {sampler}")
    if metadata.get("cfg"):
        fields.append(f"CFG scale: {_strength(metadata['cfg'])}")
    if metadata.get("seed"):
        fields.append(f"Seed: {metadata['seed']}")
    if metadata.get("width") and metadata.get("height"):
        fields.append(f"Size: {metadata['width']}x{metadata['height']}")
    if metadata.get("model_name"):
        fields.append(f"Model: {metadata['model_name']}")
    if metadata.get("vae_name"):
        fields.append(f"VAE: {metadata['vae_name']}")
    if metadata.get("denoise") and float(metadata["denoise"]) < 1:
        fields.append(f"Denoising strength: {_strength(metadata['denoise'])}")
    if metadata.get("clip_skip"):
        fields.append(f"Clip skip: {metadata['clip_skip']}")
    if fields:
        lines.append(", ".join(fields))
    return "\n".join(lines).strip()


def _lora_stack_from_parameters(parameters: str) -> str:
    return " ".join(dict.fromkeys(re.findall(r"<lora:[^>]+>", parameters or "")))


def copy_formats_from_png_info(info: dict[str, Any]) -> dict[str, str]:
    """Build every clipboard format from a PNG's text chunks. Missing formats are empty strings."""
    workflow = ""
    raw_workflow = info.get("workflow")
    if isinstance(raw_workflow, str) and raw_workflow.strip():
        try:
            parsed = json.loads(raw_workflow)
            if isinstance(parsed, dict) and parsed.get("nodes") is not None:
                workflow = json.dumps(parsed, ensure_ascii=False)
        except (ValueError, TypeError):
            workflow = ""

    bubba = coerce_bubba_metadata(info.get("bubba_metadata")) if info.get("bubba_metadata") else {}
    existing_parameters = str(info.get("parameters") or "").strip()
    parameters = a1111_parameters(bubba) if bubba else ""
    parameters = parameters or existing_parameters
    stack = lora_stack(bubba.get("loras") or [], bubba.get("lora_strengths") or []) if bubba else ""
    stack = stack or _lora_stack_from_parameters(existing_parameters)
    return {"workflow": workflow, "parameters": parameters, "lora_stack": stack}
