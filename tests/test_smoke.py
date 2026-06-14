# Smoke test: keeps the suite non-empty while the skeleton is filled in.
# Imports only pure modules (no settings / DB), so it runs without an env.
from app.enums.base import BaseStrEnum


class _Color(BaseStrEnum):
    RED = "RED"
    GREEN = "GREEN"


def test_base_str_enum_list() -> None:
    assert _Color.list() == ["RED", "GREEN"]


def test_base_str_enum_is_str() -> None:
    assert _Color.RED == "RED"
