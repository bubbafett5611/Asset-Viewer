"""Smart media search: parse field queries and extract normalized generation fields.

Supported syntax (case-insensitive, AND-combined):
    plain words            each must appear in the filename, path or metadata
    "quoted phrase"        exact substring
    -word / -field:value   exclude matches
    model:  lora:  sampler:  scheduler:  seed:  steps:  cfg:  prompt:  neg:
    model:=exact_name      whole-value match instead of "contains"
    name:  folder:  ext:
    size>2mb  size<500kb   file size bounds (b, kb, mb, gb)
    after:2026-11-01  before:2026-11-18  on:2026-11-12   local dates (also today / yesterday)
    is:fav                 favorites only
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
import os
import re
import shlex
from typing import Any

FIELD_ALIASES = {
    "model": "model",
    "checkpoint": "model",
    "ckpt": "model",
    "lora": "lora",
    "loras": "lora",
    "sampler": "sampler",
    "scheduler": "scheduler",
    "seed": "seed",
    "steps": "steps",
    "cfg": "cfg",
    "prompt": "prompt",
    "positive": "prompt",
    "neg": "negative",
    "negative": "negative",
    "name": "name",
    "file": "name",
    "folder": "folder",
    "path": "folder",
    "ext": "ext",
    "type": "ext",
}
EXACT_FIELDS = {"seed", "steps", "cfg", "ext"}
MODEL_KEYS = ("model_name", "model", "ckpt_name", "checkpoint", "checkpoint_name", "sd_model_name", "base_model")
SIZE_PATTERN = re.compile(r"^size(<=|>=|<|>)(\d+(?:\.\d+)?)(b|kb|mb|gb)?$")
SIZE_UNITS = {"b": 1, "kb": 1024, "mb": 1024**2, "gb": 1024**3, None: 1}
DATE_FIELDS = {"after", "before", "on", "since", "until"}


@dataclass
class ParsedQuery:
    terms: list[str] = field(default_factory=list)
    excluded_terms: list[str] = field(default_factory=list)
    fields: list[tuple[str, str]] = field(default_factory=list)
    excluded_fields: list[tuple[str, str]] = field(default_factory=list)
    min_size: int | None = None
    max_size: int | None = None
    after_ts: float | None = None
    before_ts: float | None = None
    favorites_only: bool = False

    @property
    def needs_generation(self) -> bool:
        generation_fields = {"model", "lora", "sampler", "scheduler", "seed", "steps", "cfg", "prompt", "negative"}
        return any(name in generation_fields for name, _ in self.fields + self.excluded_fields)

    @property
    def is_empty(self) -> bool:
        return not (
            self.terms
            or self.excluded_terms
            or self.fields
            or self.excluded_fields
            or self.min_size is not None
            or self.max_size is not None
            or self.after_ts is not None
            or self.before_ts is not None
            or self.favorites_only
        )


def _parse_day(value: str) -> date | None:
    lowered = value.lower()
    today = date.today()
    if lowered == "today":
        return today
    if lowered == "yesterday":
        return today - timedelta(days=1)
    for pattern in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m"):
        try:
            parsed = datetime.strptime(value, pattern).date()
            return parsed
        except ValueError:
            continue
    return None


def _day_start(day: date) -> float:
    return datetime(day.year, day.month, day.day).timestamp()


def _tokenize(query: str) -> list[str]:
    try:
        return shlex.split(query, posix=True)
    except ValueError:
        # Unbalanced quotes: drop them and fall back to whitespace splitting.
        return query.replace('"', "").split()


def parse_query(query: str) -> ParsedQuery:
    parsed = ParsedQuery()
    for raw_token in _tokenize(str(query or "").strip()):
        token = raw_token.strip()
        if not token:
            continue
        negate = token.startswith("-") and len(token) > 1
        body = token[1:] if negate else token
        lowered = body.lower()

        size_match = SIZE_PATTERN.match(lowered)
        if size_match and not negate:
            operator, number, unit = size_match.groups()
            bytes_value = int(float(number) * SIZE_UNITS[unit])
            if operator.startswith(">"):
                parsed.min_size = bytes_value
            else:
                parsed.max_size = bytes_value
            continue

        if ":" in body:
            key, _, value = body.partition(":")
            key = key.lower()
            value = value.strip()
            if key == "is" and value.lower() in {"fav", "favorite", "favorites", "starred"} and not negate:
                parsed.favorites_only = True
                continue
            if key in DATE_FIELDS and not negate:
                day = _parse_day(value)
                if day is not None:
                    if len(value) == 7 and key == "on":  # on:2026-11 = whole month
                        next_month = (day.replace(day=28) + timedelta(days=4)).replace(day=1)
                        parsed.after_ts, parsed.before_ts = _day_start(day), _day_start(next_month)
                    elif key in {"after", "since"}:
                        parsed.after_ts = _day_start(day)
                    elif key in {"before", "until"}:
                        parsed.before_ts = _day_start(day)
                    else:
                        parsed.after_ts, parsed.before_ts = _day_start(day), _day_start(day + timedelta(days=1))
                    continue
            canonical = FIELD_ALIASES.get(key)
            if canonical and value:
                (parsed.excluded_fields if negate else parsed.fields).append((canonical, value.lower()))
                continue

        (parsed.excluded_terms if negate else parsed.terms).append(lowered)
    return parsed


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _lora_name(value: Any) -> str:
    if isinstance(value, dict):
        value = value.get("name") or value.get("lora_name") or ""
    name = _as_text(value).replace("\\", "/").rsplit("/", 1)[-1]
    return re.sub(r"\.(safetensors|ckpt|pt|pth)$", "", name, flags=re.IGNORECASE)


def generation_fields(metadata_summary: dict[str, Any] | None) -> dict[str, Any]:
    """Normalized generation fields from an indexed metadata summary (Bubba metadata wins)."""
    embedded = (metadata_summary or {}).get("metadata")
    if not isinstance(embedded, dict):
        return {}
    sources = [source for source in (embedded.get("bubba_metadata"), embedded.get("generation")) if isinstance(source, dict)]
    if not sources:
        return {}

    def first(*keys: str) -> str:
        for source in sources:
            for key in keys:
                text = _as_text(source.get(key))
                if text:
                    return text
        return ""

    loras: list[str] = []
    for source in sources:
        raw = source.get("loras")
        if isinstance(raw, list) and raw:
            loras = [name for name in (_lora_name(item) for item in raw) if name]
            break
        if isinstance(raw, str) and raw.strip():
            loras = [name for name in (_lora_name(item) for item in raw.split(",")) if name]
            break

    return {
        "model": first(*MODEL_KEYS),
        "loras": loras,
        "sampler": first("sampler_name", "sampler"),
        "scheduler": first("scheduler"),
        "seed": first("seed", "seeds"),
        "steps": first("steps", "num_steps"),
        "cfg": first("cfg", "cfg_scale"),
        "prompt": first("positive_prompt", "prompt"),
        "negative": first("negative_prompt", "negative"),
    }


def _field_values(name: str, row: dict[str, Any], generation: dict[str, Any]) -> list[str]:
    if name == "lora":
        return [value.lower() for value in generation.get("loras") or []]
    if name == "name":
        return [str(row.get("name") or "").lower()]
    if name == "folder":
        relative = str(row.get("relative_path") or "").replace("\\", "/")
        return [os.path.dirname(relative).lower()]
    if name == "ext":
        return [str(row.get("extension") or "").lower().lstrip(".")]
    return [str(generation.get(name) or "").lower()]


def _field_matches(name: str, value: str, row: dict[str, Any], generation: dict[str, Any]) -> bool:
    candidates = _field_values(name, row, generation)
    if value.startswith("=") and len(value) > 1:  # model:=name -> whole-value match
        return any(candidate == value[1:] for candidate in candidates)
    if name in EXACT_FIELDS:
        target = value.lstrip(".") if name == "ext" else value
        return any(candidate == target for candidate in candidates)
    return any(value in candidate for candidate in candidates if candidate)


def row_matches(
    parsed: ParsedQuery,
    row: dict[str, Any],
    search_text: str,
    generation: dict[str, Any] | None = None,
) -> bool:
    """Apply a parsed query to one indexed row. `row` needs name, relative_path, extension, size_bytes, modified_ts."""
    for term in parsed.terms:
        if term not in search_text:
            return False
    for term in parsed.excluded_terms:
        if term in search_text:
            return False
    size_bytes = int(row.get("size_bytes") or 0)
    if parsed.min_size is not None and size_bytes <= parsed.min_size:
        return False
    if parsed.max_size is not None and size_bytes >= parsed.max_size:
        return False
    modified_ts = float(row.get("modified_ts") or 0)
    if parsed.after_ts is not None and modified_ts < parsed.after_ts:
        return False
    if parsed.before_ts is not None and modified_ts >= parsed.before_ts:
        return False
    generation = generation or {}
    for name, value in parsed.fields:
        if not _field_matches(name, value, row, generation):
            return False
    for name, value in parsed.excluded_fields:
        if _field_matches(name, value, row, generation):
            return False
    return True


PROMPT_BRACKETS_PATTERN = re.compile(r"[()\[\]{}]")
PROMPT_WEIGHT_PATTERN = re.compile(r":\s*-?\d+(?:\.\d+)?\s*$")
PROMPT_STOP_TAGS = {"", "break", "masterpiece", "best quality", "high quality", "highres", "absurdres"}


def prompt_tags(prompt: str) -> list[str]:
    tags = []
    for part in re.split(r"[,\n]", prompt or ""):
        tag = re.sub(r"<lora:[^>]*>", "", part)
        tag = PROMPT_WEIGHT_PATTERN.sub("", PROMPT_BRACKETS_PATTERN.sub("", tag).strip()).strip().lower()
        if tag and tag not in PROMPT_STOP_TAGS and len(tag) <= 60 and not tag.startswith(("score_", "embedding:")):
            tags.append(tag)
    return tags


def build_facets(rows: list[dict[str, Any]], top: int = 25) -> dict[str, Any]:
    """Usage counts across rows. Each row needs modified_ts and a `generation` dict."""
    counters = {name: Counter() for name in ("models", "loras", "samplers", "schedulers", "prompt_tags")}
    days: Counter = Counter()
    with_generation = 0
    for row in rows:
        days[datetime.fromtimestamp(float(row.get("modified_ts") or 0)).strftime("%Y-%m-%d")] += 1
        generation = row.get("generation") or {}
        if not generation:
            continue
        with_generation += 1
        if generation.get("model"):
            counters["models"][generation["model"]] += 1
        for lora in set(generation.get("loras") or []):
            counters["loras"][lora] += 1
        if generation.get("sampler"):
            counters["samplers"][generation["sampler"]] += 1
        if generation.get("scheduler"):
            counters["schedulers"][generation["scheduler"]] += 1
        for tag in set(prompt_tags(generation.get("prompt") or "")):
            counters["prompt_tags"][tag] += 1

    def ranked(counter: Counter, limit: int = top) -> list[dict[str, Any]]:
        return [{"value": value, "count": count} for value, count in counter.most_common(limit)]

    return {
        "total": len(rows),
        "with_generation": with_generation,
        "models": ranked(counters["models"]),
        "loras": ranked(counters["loras"]),
        "samplers": ranked(counters["samplers"]),
        "schedulers": ranked(counters["schedulers"]),
        "prompt_tags": ranked(counters["prompt_tags"], 40),
        "days": [{"day": day, "count": days[day]} for day in sorted(days, reverse=True)],
    }
