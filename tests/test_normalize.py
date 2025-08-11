import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from utils import normalize_text


def test_normalize_text_trim_and_ok():
    text, err = normalize_text("  abc  ", max_len=10)
    assert text == "abc"
    assert err is None


def test_normalize_text_removes_semicolon():
    text, err = normalize_text("ab;c", max_len=10)
    assert text == "abc"
    assert err is not None


def test_normalize_text_truncate_and_error():
    text, err = normalize_text("x" * 12, max_len=10)
    assert text == "x" * 10
    assert err is not None
