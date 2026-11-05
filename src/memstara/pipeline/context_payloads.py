"""Bound provider payloads without mutating Motoro history or scientific results.

Large structured data is replaced by an explicit index, never a fabricated summary.
An execution-scoped read tool can recover individual JSON fields or text pages.
"""

import copy
import hashlib
import json
import re
from pathlib import Path

VERSION = "referenced_payloads_v1"
LIMIT = 16000
READ_WINDOW = 32000


def structured(value):
    """Expose JSON stored in text fields without inventing or summarizing evidence."""
    for _ in range(3):
        if not isinstance(value, str) or not value.lstrip().startswith(("{", "[")):
            break
        try:
            value = json.loads(value)
        except ValueError:
            break
    return value


def enabled(plan):
    return (plan or {}).get("context_payload_policy") == VERSION


def index(value, pointer="", depth=0):
    value = structured(value)
    if isinstance(value, dict):
        if depth >= 3 or len(value) > 60:
            return {"$pointer": pointer, "$keys": list(value)[:60], "$key_count": len(value)}
        return {key: index(item, pointer + "/" + key.replace("~", "~0").replace("/", "~1"), depth + 1)
                for key, item in value.items()}
    if isinstance(value, list):
        if len(value) <= 12 and all(not isinstance(item, (dict, list)) for item in value):
            return value
        return {"$pointer": pointer, "$items": len(value),
                "$sample": [index(item, pointer + "/" + str(i), depth + 1) for i, item in enumerate(value[:2])]}
    if isinstance(value, str) and len(value) > 600:
        return {"$pointer": pointer, "$characters": len(value), "$preview": value[:300]}
    return value


def reference(root, owner, content):
    from memstara.pipeline.request_evidence import redact, write_private

    content = redact(content)
    ref = hashlib.sha256((str(owner) + "\n" + content).encode()).hexdigest()
    directory = Path(root) / "context_payloads"
    if directory.is_symlink():
        raise ValueError("Context store must not be a symlink")
    path = directory / (ref + ".json")
    if path.is_symlink():
        raise ValueError("Context payload must not be a symlink")
    if not path.exists():
        write_private(path, {"owner": str(owner), "content": content})
    try:
        value = json.loads(content)
    except ValueError:
        value = content
    preview = index(value)
    if len(json.dumps(preview)) > LIMIT // 2:
        preview = {"$keys": list(value) if isinstance(value, dict) else None,
                   "$characters": len(content)}
    return json.dumps({"context_reference": ref, "partial_view": True, "index": preview,
                      "instruction": "This is an index, not the full evidence. Use read_context_payload with this reference and a JSON pointer to inspect omitted fields before relying on them. Never infer missing values or rerun a completed tool merely to recover its output."})


def read(root, ref, pointer="", offset=0, limit=8000):
    if not re.fullmatch(r"[0-9a-f]{64}", ref):
        raise ValueError("Invalid context reference")
    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 12000:
        raise ValueError("Use a nonnegative offset and a limit from 1 to 12000")
    directory = Path(root) / "context_payloads"
    path = directory / (ref + ".json")
    if directory.is_symlink() or path.is_symlink():
        raise ValueError("Context symlinks are not allowed")
    saved = json.loads(path.read_text())
    text = saved["content"]
    if hashlib.sha256((saved["owner"] + "\n" + text).encode()).hexdigest() != ref:
        raise ValueError("Context payload integrity check failed")
    selected = structured(text)
    if pointer:
        if not pointer.startswith("/"):
            raise ValueError("Use a JSON pointer starting with /")
        value = json.loads(text)
        for part in pointer[1:].split("/"):
            value = structured(value)
            part = part.replace("~1", "/").replace("~0", "~")
            if isinstance(value, list):
                if not part.isdigit():
                    raise ValueError("Invalid array index")
                value = value[int(part)]
            else:
                value = value[part]
        selected = structured(value)
        text = json.dumps(selected, ensure_ascii=False)
    result = {"reference": ref, "pointer": pointer, "offset": offset, "characters": len(text),
            "content": text[offset:offset + limit],
            "next_offset": offset + limit if offset + limit < len(text) else None}
    if offset == 0 and isinstance(selected, (dict, list)):
        preview = index(selected, pointer)
        if len(json.dumps(preview)) > 4000:
            preview = {"$pointer": pointer, "$keys": list(selected)[:60]} if isinstance(selected, dict) else {
                "$pointer": pointer, "$items": len(selected)}
        result["index"] = preview
        result["instruction"] = "Use exact field pointers from this index to read only needed evidence. " \
                                "For another page, keep reference and pointer unchanged and use next_offset."
    return result


def structured_text(text, root, owner):
    """Keep instructions around embedded JSON intact (e.g. predictor catalog)."""
    decoder = json.JSONDecoder()
    pieces = []
    cursor = 0
    scan = 0
    while scan < len(text):
        start = text.find("{", scan)
        if start < 0:
            break
        try:
            _, size = decoder.raw_decode(text[start:])
        except ValueError:
            scan = start + 1
            continue
        if size > LIMIT:
            pieces.extend((text[cursor:start], reference(root, owner, text[start:start + size])))
            cursor = start + size
        scan = start + size
    pieces.append(text[cursor:])
    return "".join(pieces)


def prepare(messages, context):
    result = copy.deepcopy(messages)
    tool_names = {call.get("id"): call.get("function", {}).get("name", "")
                  for message in result for call in message.get("tool_calls", [])}
    reader_ids = {key for key, name in tool_names.items() if name.endswith("read_context_payload")}
    # Retrieved evidence must not become a new opaque payload containing an old
    # payload. Retain a bounded recent window; older pages point straight to the
    # ORIGINAL reference and offset, never to a serialized response envelope.
    remaining = READ_WINDOW
    for message in reversed(result):
        if message.get("role") != "tool" or message.get("tool_call_id") not in reader_ids:
            continue
        content = message.get("content")
        if not isinstance(content, str):
            continue
        if len(content) <= remaining:
            remaining -= len(content)
            continue
        try:
            page = json.loads(content)
        except ValueError:
            continue
        if isinstance(page, dict) and all(k in page for k in ("reference", "pointer", "offset", "next_offset")):
            message["content"] = json.dumps({
                **{k: page[k] for k in ("reference", "pointer", "offset", "next_offset")},
                "content_omitted": True,
                "instruction": "Previously retrieved page omitted from this request's context. "
                "Read the SAME reference, pointer and offset again only if needed; do not rerun the source tool.",
            })
    latest_exchange = max((i for i, m in enumerate(result) if m.get("tool_calls")), default=0)
    for i, message in enumerate(result):
        # Never alter tool-call IDs/arguments, system instructions, or saved history.
        content = message.get("content")
        if message.get("role") == "tool" and message.get("tool_call_id") in reader_ids:
            continue
        threshold = 4000 if i < latest_exchange else LIMIT
        if message.get("role") == "tool" and isinstance(content, str) and len(content) > threshold:
            message["content"] = reference(context[0], context[1], content)
        elif message.get("role") == "user":
            if isinstance(content, str) and len(content) > LIMIT:
                message["content"] = structured_text(content, context[0], context[1])
            elif isinstance(content, list):
                for block in content:
                    if block.get("type") == "text" and len(block.get("text", "")) > LIMIT:
                        block["text"] = structured_text(block["text"], context[0], context[1])
    return result
