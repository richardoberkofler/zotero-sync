import pytest

from zotero_sync.filenames import sanitize


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("normal-name", "normal-name"),
        ('a/b\\c:d*e?f"g<h>i|j', "a-b-c-d-e-f-g-h-i-j"),
        ("  spaced  ", "spaced"),
    ],
)
def test_sanitize_strips_illegal_chars(raw: str, expected: str) -> None:
    assert sanitize(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Smith, John Jr.", "Smith, John Jr"),
        ("trailing space ", "trailing space"),
        ("trailing dots...", "trailing dots"),
        ("mixed. . ", "mixed"),
    ],
)
def test_sanitize_strips_trailing_dots_and_spaces(raw: str, expected: str) -> None:
    assert sanitize(raw) == expected


@pytest.mark.parametrize(
    "reserved",
    [
        "CON",
        "PRN",
        "AUX",
        "NUL",
        "COM1",
        "COM9",
        "LPT1",
        "LPT9",
        "con",
        "Nul",
        "com3",
        "CON.md",
        "nul.txt",
        "Lpt3.md",
    ],
)
def test_sanitize_escapes_reserved_device_names(reserved: str) -> None:
    result = sanitize(reserved)
    assert result != reserved
    stem = result.split(".")[0]
    assert stem.upper() not in {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{i}" for i in range(1, 10)),
        *(f"LPT{i}" for i in range(1, 10)),
    }


@pytest.mark.parametrize(
    "non_reserved",
    ["COM10", "LPT0", "COMPANY", "CONTAINER", "AUXILIARY", "NULL"],
)
def test_sanitize_leaves_non_reserved_lookalikes_untouched(non_reserved: str) -> None:
    assert sanitize(non_reserved) == non_reserved
