"""Thin wrapper around the Anthropic SDK used by every TerraKernel stage.

Responsibilities
- One place that talks to the model, so usage, cost and failures are recorded uniformly.
- A content-addressed response cache. With ``TK_LLM_MODE=replay`` a whole build or
  evaluation can be re-run offline and byte-for-byte reproducibly.
- Structured output that works on gateways that differ from the official API. The
  strategies are tried in order and the first that works is remembered:
    1. ``output_config.format`` (official structured outputs), accepted only if the
       reply is valid JSON for the schema;
    2. legacy ``output_format`` with the ``structured-outputs-2025-11-13`` beta;
    3. a strict "submit" tool the model is asked to call;
    4. plain text containing JSON, validated and retried with the error message.
  Whatever strategy produced it, the result is validated with pydantic.

Credentials are never read or logged here; the SDK resolves them from the environment.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypeVar

import anthropic
from pydantic import BaseModel, ValidationError

from terrakernel.config import MODEL_PRICES, Settings, get_settings

T = TypeVar("T", bound=BaseModel)

STRATEGIES = ("output_config", "legacy_output_format", "submit_tool", "text_json")
LEGACY_BETA = "structured-outputs-2025-11-13"
CACHE_VERSION = "1"


class LLMError(RuntimeError):
    """A model call failed in a way the caller should surface."""


class ReplayMiss(LLMError):
    """Replay mode was requested but no stored response matches the request."""


class Refusal(LLMError):
    """The model declined the request (stop_reason == 'refusal')."""


@dataclass
class Usage:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cached_responses: int = 0
    cost_usd: float = 0.0
    by_model: dict[str, dict[str, float]] = field(default_factory=dict)

    def add(self, model: str, usage: dict[str, Any], from_cache: bool) -> None:
        if from_cache:
            self.cached_responses += 1
            return
        inp = int(usage.get("input_tokens") or 0)
        out = int(usage.get("output_tokens") or 0)
        cr = int(usage.get("cache_read_input_tokens") or 0)
        cw = int(usage.get("cache_creation_input_tokens") or 0)
        self.calls += 1
        self.input_tokens += inp
        self.output_tokens += out
        self.cache_read_tokens += cr
        self.cache_write_tokens += cw
        cost = estimate_cost(model, inp, out, cr, cw)
        self.cost_usd += cost
        m = self.by_model.setdefault(model, {"calls": 0, "input": 0, "output": 0, "cost_usd": 0.0})
        m["calls"] += 1
        m["input"] += inp + cr + cw
        m["output"] += out
        m["cost_usd"] += cost

    def as_dict(self) -> dict[str, Any]:
        return {
            "calls": self.calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cache_write_tokens": self.cache_write_tokens,
            "cached_responses": self.cached_responses,
            "cost_usd_estimate": round(self.cost_usd, 4),
            "by_model": self.by_model,
        }


def estimate_cost(model: str, inp: int, out: int, cache_read: int = 0, cache_write: int = 0) -> float:
    price = MODEL_PRICES.get(model)
    if not price:
        return 0.0
    pi, po, pcr, pcw = price
    return (inp * pi + out * po + cache_read * pcr + cache_write * pcw) / 1_000_000


def _canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def extract_json(text: str) -> Any:
    """Parse the first JSON object or array found in ``text``."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.S)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    starts = [i for i in (text.find("{"), text.find("[")) if i >= 0]
    if not starts:
        raise ValueError("no JSON object found in model output")
    start = min(starts)
    decoder = json.JSONDecoder()
    obj, _ = decoder.raw_decode(text[start:])
    return obj


def strict_schema(model_cls: type[BaseModel]) -> dict[str, Any]:
    """JSON Schema for ``model_cls`` in the shape structured-output APIs expect.

    References are inlined, every object gets ``additionalProperties: false`` and every
    property is listed in ``required`` (optional fields become nullable).
    """
    schema = model_cls.model_json_schema()
    defs = schema.pop("$defs", {})

    def resolve(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                name = node["$ref"].split("/")[-1]
                return resolve(copy.deepcopy(defs[name]))
            if isinstance(node.get("additionalProperties"), dict):
                raise ValueError(
                    f"{model_cls.__name__}: free-form dict fields cannot be used with strict structured output; "
                    "use a list of name/value objects instead"
                )
            out = {k: resolve(v) for k, v in node.items() if k not in ("title", "default")}
            if out.get("type") == "object" or "properties" in out:
                props = out.get("properties", {})
                out["type"] = "object"
                out["properties"] = props
                out["required"] = list(props.keys())
                out["additionalProperties"] = False
            return out
        if isinstance(node, list):
            return [resolve(x) for x in node]
        return node

    return resolve(schema)


class LLMClient:
    """Synchronous model client with caching, usage accounting and structured output."""

    def __init__(self, settings: Settings | None = None, cache_dir: Path | None = None):
        self.settings = settings or get_settings()
        self.cache_dir = cache_dir or self.settings.llm_cache_dir
        if self.cache_dir:
            Path(self.cache_dir).mkdir(parents=True, exist_ok=True)
        self.usage = Usage()
        self._client: anthropic.Anthropic | None = None
        self._lock = threading.Lock()
        self._strategy: str | None = self.settings.structured_strategy or None
        self._sem = threading.Semaphore(max(1, self.settings.max_concurrency))

    # ------------------------------------------------------------------ plumbing
    @property
    def client(self) -> anthropic.Anthropic:
        if self._client is None:
            self._client = anthropic.Anthropic(timeout=self.settings.request_timeout_s, max_retries=4)
        return self._client

    def _cache_path(self, key: str) -> Path | None:
        if not self.cache_dir:
            return None
        return Path(self.cache_dir) / key[:2] / f"{key}.json"

    @staticmethod
    def request_key(params: dict[str, Any]) -> str:
        return hashlib.sha256((CACHE_VERSION + _canonical(params)).encode()).hexdigest()

    def raw_create(self, **params: Any) -> dict[str, Any]:
        """Call ``messages.create`` (with caching) and return the response as a plain dict.

        ``params`` may include ``extra_headers`` / ``extra_body``; they are part of the
        cache key so different strategies never share an entry.
        """
        namespace = params.pop("cache_namespace", None)
        mode = self.settings.llm_mode
        key = self.request_key({**params, "_namespace": namespace} if namespace else params)
        path = self._cache_path(key)
        if path and mode in ("replay", "auto") and path.exists():
            data = json.loads(path.read_text())
            self.usage.add(params.get("model", ""), data.get("usage", {}), from_cache=True)
            return data
        if mode == "replay":
            raise ReplayMiss(f"no cached response for request {key[:12]} (TK_LLM_MODE=replay)")

        with self._sem:
            t0 = time.time()
            try:
                resp = self.client.messages.create(**params)
            except anthropic.APIStatusError as e:
                raise LLMError(f"model call failed with HTTP {e.status_code}: {e.message}") from e
            except anthropic.APIConnectionError as e:
                raise LLMError(f"model call failed: cannot reach the API ({e.__class__.__name__})") from e
            elapsed = time.time() - t0
        data = resp.model_dump(mode="json")
        data["_elapsed_s"] = round(elapsed, 3)
        with self._lock:
            self.usage.add(data.get("model") or params.get("model", ""), data.get("usage", {}), from_cache=False)
        if path and mode in ("record", "auto"):
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False))
            tmp.replace(path)
        return data

    @staticmethod
    def text_of(data: dict[str, Any]) -> str:
        return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")

    @staticmethod
    def check_stop(data: dict[str, Any]) -> None:
        reason = data.get("stop_reason")
        if reason == "refusal":
            details = data.get("stop_details") or {}
            raise Refusal(f"model declined the request (category={details.get('category')})")

    # ------------------------------------------------------------------ text
    def text(
        self,
        prompt: str | list[dict[str, Any]],
        *,
        system: str | None = None,
        model: str | None = None,
        max_tokens: int = 8000,
    ) -> str:
        content = prompt if isinstance(prompt, list) else [{"type": "text", "text": prompt}]
        params: dict[str, Any] = {
            "model": model or self.settings.model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": content}],
        }
        if system:
            params["system"] = [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]
        data = self.raw_create(**params)
        self.check_stop(data)
        return self.text_of(data)

    # ------------------------------------------------------------------ structured
    def structured(
        self,
        prompt: str | list[dict[str, Any]],
        output: type[T],
        *,
        system: str | None = None,
        model: str | None = None,
        max_tokens: int = 16000,
        retries: int = 1,
        tool_name: str = "submit_result",
        tool_description: str = "Submit the final structured result.",
    ) -> T:
        """Ask for a reply matching ``output`` and return it validated."""
        schema = strict_schema(output)
        content = prompt if isinstance(prompt, list) else [{"type": "text", "text": prompt}]
        base: dict[str, Any] = {
            "model": model or self.settings.model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": content}],
        }
        if system:
            base["system"] = [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]

        last_error: Exception | None = None
        for strategy in self._strategy_order():
            attempt_messages = base["messages"]
            for _attempt in range(retries + 1):
                params = self._params_for(strategy, base, attempt_messages, schema, tool_name, tool_description)
                data: dict[str, Any] = {}
                try:
                    data = self.raw_create(**params)
                    self.check_stop(data)
                    payload = self._payload(strategy, data, tool_name)
                    return output.model_validate(payload)
                except (Refusal, ReplayMiss):
                    raise
                except (ValueError, ValidationError) as e:
                    last_error = e
                    reply = self.text_of(data) if data else ""
                    if strategy == "submit_tool" and data:
                        reply = reply or json.dumps(
                            [b.get("input") for b in data.get("content", []) if b.get("type") == "tool_use"]
                        )
                    attempt_messages = base["messages"] + [
                        {"role": "assistant", "content": reply or "(no usable output)"},
                        {
                            "role": "user",
                            "content": "Your previous reply did not match the required JSON schema: "
                            f"{str(e)[:1500]}\nReply again with the complete corrected result.",
                        },
                    ]
                except LLMError as e:
                    last_error = e
                    break
        raise LLMError(f"structured output failed after all strategies: {last_error}")

    def _strategy_order(self) -> list[str]:
        """Pinned strategy first, then the remaining fallbacks (never re-trying an ignored one)."""
        if self._strategy is None:
            self._strategy = self.probe_structured()
        fallbacks = [s for s in STRATEGIES if s not in (self._strategy, "output_config")]
        return [self._strategy, *fallbacks]

    def probe_structured(self, model: str = "claude-haiku-5-5") -> str:
        """Find out which structured-output mechanism this endpoint honors.

        The probe prompt deliberately never mentions JSON: a strategy only counts as
        working if the endpoint itself enforces the schema.
        """
        schema = {
            "type": "object",
            "properties": {"color": {"type": "string"}},
            "required": ["color"],
            "additionalProperties": False,
        }
        base = {
            "model": model,
            "max_tokens": 1024,
            "messages": [{"role": "user", "content": "Name one primary color."}],
        }
        for strategy in ("output_config", "legacy_output_format"):
            params = self._params_for(strategy, base, base["messages"], schema, "submit_result", "")
            try:
                data = self.raw_create(**params)
                payload = json.loads(self.text_of(data).strip())
                if isinstance(payload, dict) and isinstance(payload.get("color"), str):
                    return strategy
            except (LLMError, ValueError):
                continue
        return "submit_tool"

    @staticmethod
    def _params_for(
        strategy: str,
        base: dict[str, Any],
        messages: list[dict[str, Any]],
        schema: dict[str, Any],
        tool_name: str,
        tool_description: str,
    ) -> dict[str, Any]:
        params = dict(base)
        params["messages"] = messages
        if strategy == "output_config":
            params["output_config"] = {"format": {"type": "json_schema", "schema": schema}}
        elif strategy == "legacy_output_format":
            params["extra_body"] = {"output_format": {"type": "json_schema", "schema": schema}}
            params["extra_headers"] = {"anthropic-beta": LEGACY_BETA}
        elif strategy == "submit_tool":
            params["tools"] = [
                {"name": tool_name, "description": tool_description, "strict": True, "input_schema": schema}
            ]
            sys_text = (
                f"Respond only by calling the `{tool_name}` tool exactly once with the complete result. "
                f"No other tools exist."
            )
            existing = base.get("system")
            params["system"] = (existing or []) + [{"type": "text", "text": sys_text}]
        elif strategy == "text_json":
            instr = (
                "Reply with only a JSON value that validates against this JSON Schema, with no prose:\n"
                + json.dumps(schema, ensure_ascii=False)
            )
            existing = base.get("system")
            params["system"] = (existing or []) + [{"type": "text", "text": instr}]
        return params

    def _payload(self, strategy: str, data: dict[str, Any], tool_name: str) -> Any:
        if data.get("stop_reason") == "max_tokens":
            raise ValueError("output was truncated at max_tokens")
        if strategy == "submit_tool":
            for block in data.get("content", []):
                if block.get("type") == "tool_use" and block.get("name") == tool_name:
                    return block.get("input")
            raise ValueError(f"the model did not call {tool_name}")
        return extract_json(self.text_of(data))

    @property
    def strategy(self) -> str | None:
        return self._strategy
