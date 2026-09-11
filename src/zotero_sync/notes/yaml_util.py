from __future__ import annotations

import re

_QUOTED_ITEM_RE = re.compile(r'^  - "((?:[^"\\]|\\.)*)"\s*$')


def yaml_scalar(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    escaped = escaped.replace("\r\n", "\\n").replace("\n", "\\n").replace("\r", "\\n")
    return f'"{escaped}"'


def yaml_list(values: list[str]) -> str:
    if not values:
        return "[]"
    return "\n" + "\n".join(f"  - {yaml_scalar(v)}" for v in values)


def _unescape_scalar(raw: str) -> str:
    result = []
    i = 0
    while i < len(raw):
        ch = raw[i]
        if ch == "\\" and i + 1 < len(raw):
            nxt = raw[i + 1]
            result.append({"n": "\n", '"': '"', "\\": "\\"}.get(nxt, nxt))
            i += 2
        else:
            result.append(ch)
            i += 1
    return "".join(result)


def parse_yaml_list(text: str, field_name: str) -> list[str] | None:
    """Reads a list field back out of text written by yaml_list() — a
    narrow reader matching this module's own narrow writer (#24's
    design: no general YAML dependency for a format we fully control),
    not a general-purpose YAML parser. Returns None if the field isn't
    present at all (as opposed to present-but-empty, which is [])."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.rstrip() == f"{field_name}: []":
            return []
        if line.rstrip() == f"{field_name}:":
            items = []
            for item_line in lines[i + 1 :]:
                match = _QUOTED_ITEM_RE.match(item_line)
                if not match:
                    break
                items.append(_unescape_scalar(match.group(1)))
            return items
    return None
