"""Crate reading refuses unsafe archives and directories before parsing anything (ADR-047 D1)."""

from __future__ import annotations

import io
import os
import stat
import sys
import zipfile
from pathlib import Path

import pytest
from aero.crate import CrateError, CrateFormatError, CratePathError, pack_crate, verify_crate
from aero.crate.members import MAX_MEMBER_BYTES, check_member_name, read_members

from tests.unit._crate_fixtures import built

pytestmark = pytest.mark.stage_21


def _zip(entries: list[tuple[str, bytes]], **kw: object) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_STORED) as zf:
        for name, data in entries:
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            for k, v in kw.items():
                setattr(info, k, v)
            zf.writestr(info, data)
    return buf.getvalue()


def _members_zip_with(extra: tuple[str, bytes] | None = None, **kw: object) -> bytes:
    entries = sorted(built("evidence_only").items())
    if extra is not None:
        entries.append(extra)
    return _zip(entries, **kw)


@pytest.mark.parametrize(
    "name",
    [
        "../escape.json",
        "/abs.json",
        "evidence\\win.json",
        "evidence/../../x",
        "evidence/./x",
        "evidence//x",
        "a\x00b",
        "UPPER.json",
        "evidence/.DS_Store",
        "__MACOSX/x",
        "evidence/con.json",
        "evidence/stage20_adr045_r3.json",
        "evidence/stage20_n3_confirmation.json",
        "unknown.json",
        "other/x.json",
        "evidence/a/b.json",
        "c:x",
    ],
)
def test_unsafe_names_are_refused(name: str) -> None:
    with pytest.raises(CratePathError):
        check_member_name(name)


@pytest.mark.parametrize("name", ["../escape.json", "/abs.json", "evidence/stage20_adr045_r3.json"])
def test_zip_slip_and_forbidden_names_are_refused_in_archives(name: str, tmp_path: Path) -> None:
    path = tmp_path / "evil.crate.zip"
    path.write_bytes(_members_zip_with((name, b"{}")))
    with pytest.raises(CratePathError):
        verify_crate(path)


def test_compressed_encrypted_symlink_and_directory_entries_are_refused(tmp_path: Path) -> None:
    path = tmp_path / "x.crate.zip"
    path.write_bytes(_members_zip_with(compress_type=zipfile.ZIP_DEFLATED))
    with pytest.raises(CrateFormatError, match="compressed"):
        verify_crate(path)
    path.write_bytes(_members_zip_with(external_attr=(stat.S_IFLNK | 0o777) << 16))
    with pytest.raises(CratePathError, match="regular"):
        verify_crate(path)
    path.write_bytes(_members_zip_with(("evidence/", b"")))
    with pytest.raises(CratePathError, match="directory"):
        verify_crate(path)
    raw = bytearray(_members_zip_with())
    raw[6] |= 0x01  # set the encryption bit in the first local header's flags
    # zipfile reads flags from the central directory; patch every central header too
    cd = raw.find(b"PK\x01\x02")
    while cd != -1:
        raw[cd + 8] |= 0x01
        cd = raw.find(b"PK\x01\x02", cd + 4)
    path.write_bytes(bytes(raw))
    with pytest.raises(CrateError):
        verify_crate(path)


def test_duplicate_and_case_colliding_entries_are_refused(tmp_path: Path) -> None:
    entries = sorted(built("evidence_only").items())
    path = tmp_path / "dup.crate.zip"
    with pytest.warns(UserWarning):  # zipfile warns about the duplicate name
        path.write_bytes(_zip([*entries, entries[0]]))
    with pytest.raises(CratePathError, match="duplicate"):
        verify_crate(path)


def test_comment_prepended_data_and_corruption_are_refused(tmp_path: Path) -> None:
    good = pack_crate(built("evidence_only"))
    path = tmp_path / "x.crate.zip"
    buf = io.BytesIO(good)
    with zipfile.ZipFile(buf, "a") as zf:
        zf.comment = b"hello"
    path.write_bytes(buf.getvalue())
    with pytest.raises(CrateFormatError, match="comment"):
        verify_crate(path)
    path.write_bytes(b"GARBAGE" + good)
    with pytest.raises(CrateFormatError):
        verify_crate(path)
    corrupt = bytearray(good)
    idx = corrupt.find(b'"no-claim"')
    corrupt[idx + 1] ^= 0x01  # stored bytes: a CRC mismatch
    path.write_bytes(bytes(corrupt))
    with pytest.raises(CrateError):
        verify_crate(path)


def test_oversize_member_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "big.crate.zip"
    path.write_bytes(_members_zip_with(("evidence/big.bin", b"x" * (MAX_MEMBER_BYTES + 1))))
    with pytest.raises(CratePathError, match="exceeds"):
        verify_crate(path)


def test_too_many_members_are_refused(tmp_path: Path) -> None:
    extra = [(f"evidence/f{i:03d}.txt", b"x") for i in range(70)]
    path = tmp_path / "many.crate.zip"
    path.write_bytes(_zip(sorted([*built("evidence_only").items(), *extra])))
    with pytest.raises(CratePathError, match="members"):
        verify_crate(path)


def _write_dir(root: Path, members: dict[str, bytes]) -> None:
    for name, data in members.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX symlinks and FIFOs")
def test_directory_symlinks_fifos_junk_and_strays_are_refused(tmp_path: Path) -> None:
    members = built("evidence_only")
    base = tmp_path / "c"
    _write_dir(base, members)
    assert read_members(base) == members

    link = tmp_path / "link"
    _write_dir(link, members)
    os.remove(link / "evidence" / "synthetic_nogo.json")
    os.symlink(base / "evidence" / "synthetic_nogo.json", link / "evidence" / "synthetic_nogo.json")
    with pytest.raises(CratePathError, match="symlink"):
        read_members(link)

    fifo = tmp_path / "fifo"
    _write_dir(fifo, members)
    os.mkfifo(fifo / "evidence" / "pipe.txt")
    with pytest.raises(CratePathError):
        read_members(fifo)

    junk = tmp_path / "junk"
    _write_dir(junk, members)
    (junk / ".DS_Store").write_bytes(b"x")
    with pytest.raises(CratePathError, match="junk"):
        read_members(junk)

    stray = tmp_path / "stray"
    _write_dir(stray, members)
    (stray / "notes").mkdir()
    with pytest.raises(CratePathError):
        read_members(stray)

    whole_link = tmp_path / "whole"
    os.symlink(base, whole_link)
    with pytest.raises(CratePathError, match="symlink"):
        read_members(whole_link)
