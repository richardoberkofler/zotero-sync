import re

ILLEGAL_CHARS = re.compile(r'[/\\:*?"<>|]')


def sanitize(name: str) -> str:
    return ILLEGAL_CHARS.sub("-", name).strip()
