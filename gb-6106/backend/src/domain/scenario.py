import re

from .fixtures import FIXTURES
from .page import HEADER_BYTES, SlottedPage


CONFIG = {
    "title": "砺光玻璃·压模履历槽页检修",
    "team": "砺光玻璃 C4 线 7 人工装与质保小组",
    "description": "撤销空跑、补录压模复测，在清班前验证单页压实和追溯槽号。",
    "direction": "槽式页空间管理与压实",
    "mechanism": "定长槽目录、UTF-8 字节数组、页内更新迁移与压实，活记录的槽号保持稳定。",
    "modules": ["模具交班", "压模变更单", "槽页重放", "追溯地址表"],
    "unit": "压模变更单",
    "max_parameter": 4096,
    "parameter_label": "模拟页容量（字节，16–4096）",
    "default_parameter": 192,
    "facts": ["活槽位", "拒绝操作", "最大碎片"],
    "palette": 6,
    "fixture": "C4#03 · GM-C4-P07",
}

ACTIONS = {"insert": "录入", "delete": "撤销", "update": "补记", "compact": "整理"}


def validate(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("operations"), list):
        raise ValueError("operations 必须是操作列表")
    operations = payload["operations"]
    if not 1 <= len(operations) <= 100:
        raise ValueError("每单允许 1 至 100 条操作")
    for step, operation in enumerate(operations, 1):
        if not isinstance(operation, dict):
            raise ValueError(f"第 {step} 步必须是对象")
        action = operation.get("op")
        if not isinstance(action, str) or action not in ACTIONS:
            raise ValueError(f"第 {step} 步不支持该操作")
        if action != "compact":
            key = operation.get("key")
            if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,24}", key):
                raise ValueError(f"第 {step} 步记录号须为 1 至 24 位字母、数字、下划线或连字符")
        if action in {"insert", "update"}:
            note = operation.get("note")
            if not isinstance(note, str) or not note or len(note) > 1000:
                raise ValueError(f"第 {step} 步备注须为 1 至 1000 个字符")
            try:
                note.encode()
            except UnicodeEncodeError:
                raise ValueError(f"第 {step} 步备注不是有效 UTF-8 文本") from None


def apply_operation(page, operation, step=None):
    """Apply one operation and return its replay row.

    ValueError is deliberately left to the caller. Lenient replay counts it as a
    denied operation; continuation orders use strict all-or-nothing replay.
    """
    action = operation["op"]
    key = "" if action == "compact" else operation["key"]
    prior = page.find(key)
    pointer = page.slots[prior].offset if prior is not None else None
    slot_id = prior
    message = "完成"
    try:
        if action == "compact":
            page.compact()
            compacted = True
        elif action == "delete":
            slot_id = page.delete(key)
            compacted = False
        else:
            write = page.insert if action == "insert" else page.update
            slot_id, compacted = write(key, operation["note"].encode())
            if compacted:
                message = "压实后落盘"
    except ValueError:
        raise
    slot = page.slots[slot_id] if slot_id is not None else None
    return {
        "步骤": step, "操作": ACTIONS[action], "履历": key, "槽号": slot_id,
        "原偏移": pointer, "现偏移": slot.offset if slot else None,
        "记录字节": slot.length if slot else None, "连续空闲": page.contiguous,
        "碎片字节": page.fragmented, "结果": message,
    }


def trace_rows(page):
    rows = []
    for index, item in enumerate(page.slots):
        if item:
            rows.append({
                "步骤": None, "操作": "追溯地址", "履历": item.key, "槽号": index,
                "原偏移": None, "现偏移": item.offset, "记录字节": item.length,
                "连续空闲": page.contiguous, "碎片字节": page.fragmented,
                "结果": page.read(index).decode(),
            })
    return rows


def build_result(page, rows, *, denied=0, compactions=0, peak_waste=0):
    rows = [*rows, *trace_rows(page)]
    live = sum(item is not None for item in page.slots)
    return {
        "summary": f"最终保留 {live} 条履历，压实 {compactions} 次，拒绝 {denied} 条操作。",
        "metrics": {"活槽位": live, "拒绝操作": denied, "最大碎片": peak_waste,
                    "压实次数": compactions, "剩余字节": page.free},
        "rows": rows,
    }


def run_detailed(payload, parameter, db=None, *, base_snapshot=None, strict=False):
    validate(payload)
    if base_snapshot is not None:
        if isinstance(base_snapshot, SlottedPage):
            page = base_snapshot.clone()
        else:
            page = SlottedPage.from_snapshot(base_snapshot)
        if parameter is not None and int(parameter) != page.size:
            raise ValueError(f"续单必须沿用底稿页容量 {page.size} 字节")
    else:
        if parameter < HEADER_BYTES:
            raise ValueError(f"至少需要 {HEADER_BYTES} 字节页头")
        page = SlottedPage(parameter)
    denied = 0
    peak_waste = 0
    compactions = 0
    rows = []
    for step, operation in enumerate(payload["operations"], 1):
        try:
            row = apply_operation(page, operation, step)
            if operation["op"] in {"insert", "update"} and row["结果"] == "压实后落盘":
                compactions += 1
            elif operation["op"] == "compact":
                compactions += 1
        except ValueError as exc:
            if strict:
                raise
            denied += 1
            action = operation["op"]
            key = "" if action == "compact" else operation.get("key", "")
            prior = page.find(key) if key else None
            slot_id = prior
            slot = page.slots[slot_id] if slot_id is not None else None
            row = {
                "步骤": step, "操作": ACTIONS[action], "履历": key, "槽号": slot_id,
                "原偏移": slot.offset if slot else None,
                "现偏移": slot.offset if slot else None,
                "记录字节": slot.length if slot else None, "连续空闲": page.contiguous,
                "碎片字节": page.fragmented, "结果": str(exc),
            }
        peak_waste = max(peak_waste, page.fragmented)
        rows.append(row)
    return build_result(
        page, rows, denied=denied, compactions=compactions, peak_waste=peak_waste
    ), page


def run(payload, parameter=None, db=None, **kwargs):
    return run_detailed(payload, parameter, db, **kwargs)[0]


def continue_run(payload, base_snapshot=None, parameter=None, db=None, **kwargs):
    """Strict continuation replay for callers that use the scenario module."""
    kwargs.setdefault("strict", True)
    return run(payload, parameter, db, base_snapshot=base_snapshot, **kwargs)
