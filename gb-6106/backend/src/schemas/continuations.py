from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domain.scenario import ACTIONS


_ID_KEYS = (
    "base_run_id", "base_batch_id", "source_run_id", "source_batch_id",
    "parent_run_id", "parent_batch_id", "handover_run_id", "handover_batch_id",
    "draft_run_id", "draft_batch_id", "draft_id", "base_id", "batch_id", "run_id",
)
_KEY_KEYS = (
    "idempotency_key", "idempotencyKey", "idempotency-key",
    "request_id", "request_key", "client_token", "retry_key",
)
_OPERATION_KEYS = ("operations", "ops", "entries", "records", "items", "changes")


def _camel_to_snake(name):
    out = []
    for char in name:
        if char.isupper():
            out.append("_")
            out.append(char.lower())
        else:
            out.append(char)
    return "".join(out).lstrip("_")


def _normalize_operation(item, index):
    if isinstance(item, str):
        import hashlib
        suffix = hashlib.sha1(item.encode("utf-8")).hexdigest()[:10]
        return {"op": "insert", "key": f"N{index + 1}-{suffix}", "note": item}
    if not isinstance(item, dict):
        return item
    op = item.get("op") or item.get("action") or item.get("type") or "insert"
    inverse = {label: action for action, label in ACTIONS.items()}
    op = inverse.get(op, op)
    normalized = dict(item)
    normalized["op"] = op
    if "key" not in normalized:
        for alias in ("record_key", "record_id", "history_key", "履历", "编号"):
            if alias in normalized:
                normalized["key"] = normalized[alias]
                break
    if op in {"insert", "update"} and "note" not in normalized:
        for alias in ("content", "text", "remark", "备注"):
            if alias in normalized:
                normalized["note"] = normalized[alias]
                break
    return normalized


class ContinuationInput(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    base_run_id: Any = None
    case_id: int | str | None = None
    parameter: int | None = Field(default=None, ge=1, le=4096)
    idempotency_key: str | None = Field(default=None, max_length=128)
    operations: list[Any] | None = None
    dry_run: bool = False

    @model_validator(mode="before")
    @classmethod
    def normalize_request(cls, value):
        if isinstance(value, list):
            value = {"operations": value}
        if not isinstance(value, dict):
            return value
        data = {_camel_to_snake(str(key)): item for key, item in value.items()}

        for envelope in ("continuation", "order", "form"):
            inner = data.get(envelope)
            if isinstance(inner, dict):
                for key, item in inner.items():
                    data.setdefault(_camel_to_snake(str(key)), item)

        nested_payload = data.get("payload")
        operation_source = data
        if isinstance(nested_payload, dict):
            for key in _OPERATION_KEYS:
                if key in nested_payload:
                    operation_source = nested_payload
                    break

        if data.get("base_run_id") in (None, ""):
            base = data.get("base") or data.get("draft") or data.get("handover")
            if isinstance(base, dict):
                for key in ("run_id", "id", "batch_id", "base_run_id"):
                    if base.get(key) not in (None, ""):
                        data["base_run_id"] = base[key]
                        break
        if data.get("base_run_id") in (None, ""):
            for key in _ID_KEYS:
                if data.get(key) not in (None, ""):
                    data["base_run_id"] = data[key]
                    break

        if data.get("idempotency_key") in (None, ""):
            for key in _KEY_KEYS:
                if data.get(key) not in (None, ""):
                    data["idempotency_key"] = data[key]
                    break

        operations = None
        for key in _OPERATION_KEYS:
            operations = operation_source.get(key)
            if operations is not None:
                break
        if operations is None and isinstance(nested_payload, list):
            operations = nested_payload
        if operations is not None:
            data["operations"] = [_normalize_operation(item, i) for i, item in enumerate(operations)]
        return data
