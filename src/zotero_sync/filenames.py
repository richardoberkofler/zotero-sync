import re

ILLEGAL_CHARS = re.compile(r'[/\\:*?"<>|]')

# Windows reserved device names (case-insensitive), with or without an extension.
# Windows treats the name as reserved based on the stem alone, e.g. both "CON"
# and "CON.txt" are rejected.
RESERVED_NAMES = re.compile(
    r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])$",
    re.IGNORECASE,
)


def sanitize(name: str) -> str:
    cleaned = ILLEGAL_CHARS.sub("-", name).strip()
    # Windows silently strips trailing dots and spaces, which can cause a
    # sanitized name to not match the file actually created on disk, or two
    # different sanitized names to collide.
    cleaned = cleaned.rstrip(". ")
    stem, dot, ext = cleaned.partition(".")
    if RESERVED_NAMES.match(stem):
        cleaned = f"{stem}_{dot}{ext}"
    return cleaned
