"""The crate's one encoder and one strict decoder (ADR-047 D2)."""

from __future__ import annotations

import pytest
from aero.crate._canonical import (
    MAX_DEPTH,
    dumps_document,
    is_fixed_point,
    json_equal,
    loads_strict,
)
from aero.crate.errors import CrateFormatError, CrateNonFiniteError

pytestmark = pytest.mark.stage_21

FLOAT_ZOO = [
    5e-324,
    2.2250738585072014e-308,
    1.7976931348623157e308,
    -0.0,
    0.1 + 0.2,
    1e-7,
    1e16,
    46.37208685252852,
    0.4654573059064542,
]


def test_float_zoo_round_trips_bit_for_bit() -> None:
    data = dumps_document({"zoo": FLOAT_ZOO})
    back = loads_strict(data, what="zoo")
    assert [x.hex() for x in back["zoo"]] == [x.hex() for x in FLOAT_ZOO]
    assert is_fixed_point(data, back)


def test_the_encoding_is_canonical() -> None:
    data = dumps_document({"b": 1, "a": [1.0, "ü"]})
    assert data == b'{\n  "a": [\n    1.0,\n    "\\u00fc"\n  ],\n  "b": 1\n}\n'


@pytest.mark.parametrize(
    ("raw", "error"),
    [
        (b'{"a": NaN}', CrateNonFiniteError),
        (b'{"a": Infinity}', CrateNonFiniteError),
        (b'{"a": -Infinity}', CrateNonFiniteError),
        (b'{"a": 1e999}', CrateNonFiniteError),
        (b'{"a": 1, "a": 2}', CrateFormatError),
        (b'\xef\xbb\xbf{"a": 1}', CrateFormatError),
        (b'{"a": 1}\r\n', CrateFormatError),
        (b'{"a": "\xff"}', CrateFormatError),
        (b'{"a": ', CrateFormatError),
        (b"[" * (MAX_DEPTH + 1) + b"]" * (MAX_DEPTH + 1), CrateFormatError),
    ],
)
def test_strict_parse_refuses(raw: bytes, error: type[Exception]) -> None:
    with pytest.raises(error):
        loads_strict(raw, what="t")


def test_the_encoder_refuses_non_finite_numbers() -> None:
    with pytest.raises(CrateNonFiniteError):
        dumps_document({"a": float("nan")})


def test_json_equal_distinguishes_types_and_signed_zero() -> None:
    assert json_equal({"a": [1.0, 2]}, {"a": [1.0, 2]})
    assert not json_equal(1, 1.0)
    assert not json_equal(True, 1)
    assert not json_equal(0.0, -0.0)
    assert not json_equal({"a": 1}, {"a": 1, "b": 2})


def test_a_non_canonical_document_is_not_a_fixed_point() -> None:
    assert not is_fixed_point(b'{"a":1}\n', {"a": 1})
