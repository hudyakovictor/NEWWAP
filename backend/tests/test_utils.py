from core.utils import parse_date_from_name, stable_photo_id
from pathlib import Path


def test_parse_date_ignores_suffix():
    date_str, parsed = parse_date_from_name("2001_04_10-3.jpg")
    assert date_str == "2001-04-10"
    assert parsed is not None


def test_stable_photo_id_is_deterministic():
    root = Path("/tmp/root")
    path = root / "a" / "photo.jpg"
    assert stable_photo_id("main", path, root) == stable_photo_id("main", path, root)

