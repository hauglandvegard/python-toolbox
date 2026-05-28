"""Tests for the Response dataclass."""

from dataclasses import FrozenInstanceError

import pytest

from toolbox.fetcher import Response


def test_response_is_frozen() -> None:
    r = Response(url="https://x", status_code=200, headers={}, content=b"")
    with pytest.raises(FrozenInstanceError):
        r.url = "https://y"  # type: ignore[misc]


def test_response_uses_slots() -> None:
    assert hasattr(Response, "__slots__")
    assert set(Response.__slots__) == {"url", "status_code", "headers", "content"}


def test_text_decodes_utf8_default() -> None:
    r = Response(url="https://x", status_code=200, headers={}, content=b"ole")
    assert r.text == "ole"


def test_text_uses_charset_from_content_type() -> None:
    body = "olé".encode("latin-1")
    r = Response(
        url="https://x",
        status_code=200,
        headers={"content-type": "text/html; charset=latin-1"},
        content=body,
    )
    assert r.text == "olé"


def test_text_handles_mixed_case_header() -> None:
    body = "olé".encode("latin-1")
    r = Response(
        url="https://x",
        status_code=200,
        headers={"Content-Type": "text/html; charset=latin-1"},
        content=body,
    )
    assert r.text == "olé"


def test_text_falls_back_on_bad_charset() -> None:
    r = Response(
        url="https://x",
        status_code=200,
        headers={"content-type": "text/html; charset=fake-encoding"},
        content=b"hello",
    )
    # should NOT raise; falls back to utf-8 with errors="replace"
    assert r.text == "hello"


def test_response_equality_by_value() -> None:
    a = Response(url="https://x", status_code=200, headers={"k": "v"}, content=b"a")
    b = Response(url="https://x", status_code=200, headers={"k": "v"}, content=b"a")
    assert a == b
