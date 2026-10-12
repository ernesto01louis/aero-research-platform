"""Result crates round-trip: write, move, read back, SAME numbers (ADR-047; Hard Rule 16).

Every payload shape is built in memory, verified, written to disk, and moved and renamed into a
path containing a space. It is then packed as a zip and read back. The result must equal the
original model, the numbers must be bit-identical, rebuilding must be byte-identical, and the
digest must be the same in every form.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from aero.crate import build_crate, pack_crate, verify_crate, verify_members, write_crate
from aero.crate._canonical import loads_strict

from tests.unit._crate_fixtures import SHAPES, built

pytestmark = pytest.mark.stage_21


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_build_is_deterministic(shape: str) -> None:
    assert built(shape) == built(shape)


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_write_move_read_back_same_numbers(shape: str, tmp_path: Path) -> None:
    spec = SHAPES[shape]()
    members = build_crate(spec)
    original = verify_members(members)
    first = write_crate(tmp_path / "out" / spec.crate_id, members)
    moved = tmp_path / "moved crate ü" / "received"
    moved.parent.mkdir()
    shutil.move(str(first.origin), str(moved))
    back = verify_crate(moved)
    assert back.digest == original.digest
    assert back.result == spec.result
    assert back.numbers() == original.numbers()
    assert json.dumps(back.numbers(), sort_keys=True) == json.dumps(
        original.numbers(), sort_keys=True
    )
    # Rewrite identity: what was read back, re-serialized, is the same bytes.
    assert back.members == members


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_zip_form_is_deterministic_and_equivalent(shape: str, tmp_path: Path) -> None:
    members = built(shape)
    zipped = pack_crate(members)
    assert zipped == pack_crate(built(shape))
    path = tmp_path / "x.crate.zip"
    path.write_bytes(zipped)
    from_zip = verify_crate(path)
    assert from_zip.digest == verify_members(members).digest
    assert from_zip.members == members


def test_floats_survive_bit_for_bit() -> None:
    members = built("steady_optimization")
    config_path = next(p for p in members if p.startswith("configs/"))
    cfg = loads_strict(members[config_path], what=config_path)
    assert cfg["tiny"].hex() == (1e-7).hex()
    assert cfg["huge"] == 1.7976931348623157e308
    result = verify_members(members).result
    assert result is not None
    assert result.quantities[0].value.hex() == (46.37208685252852).hex()


def test_ints_and_floats_stay_distinct() -> None:
    numbers = verify_members(built("steady_optimization")).numbers()["result"]
    assert numbers["/optimization/n_candidates"] == ["int", 74]
    assert numbers["/optimization/improvement/k"][0] == "float"


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_no_host_path_or_address_leaks_into_a_crate(shape: str) -> None:
    for name, data in built(shape).items():
        text = data.decode("utf-8", errors="replace")
        for needle in ("/root/", "/mnt/", "/home/", "192.168.", "aero-build", "aero-dev", "\\\\"):
            assert needle not in text, f"{name} contains {needle!r}"


def test_the_nested_legal_infinity_travels_as_a_string() -> None:
    members = built("independent_inf")
    assert b'"crosscheck_ratio": "Infinity"' in members["result.json"]
    result = verify_members(members).result
    assert result is not None
    assert result.improvement is not None


def test_config_preimage_hashes_to_its_name_with_coreutils_semantics() -> None:
    import hashlib

    for shape in SHAPES:
        for path, data in built(shape).items():
            if path.startswith("configs/"):
                assert hashlib.sha256(data).hexdigest() == path[len("configs/") : -len(".json")]
