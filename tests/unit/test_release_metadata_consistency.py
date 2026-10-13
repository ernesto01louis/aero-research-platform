"""Release metadata agrees with itself and is valid (Stage 21; ADR-049 H-24, R3, R5).

These tests cover:
- CITATION.cff validity (cffconvert), run in the required pytest job;
- title, licence, author and concept DOI agreeing across CITATION.cff, .zenodo.json, pyproject
  and the paper;
- Zenodo-specific rules;
- the paper's JOSS shape.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.stage_21

REPO = Path(__file__).resolve().parents[2]
CFF = yaml.safe_load((REPO / "CITATION.cff").read_text(encoding="utf-8"))
ZENODO = json.loads((REPO / ".zenodo.json").read_text(encoding="utf-8"))
PYPROJECT = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
PAPER = (REPO / "paper" / "paper.md").read_text(encoding="utf-8")
FRONT = yaml.safe_load(PAPER.split("---", 2)[1])
BODY = PAPER.split("---", 2)[2]
CONCEPT_DOI = "10.5281/zenodo.20292712"
L1 = (
    "The optimizer has never been run on a flapping-wing case, and v0.1.0 makes no flapping-wing "
    "optimization claim."
)
JOSS_SECTIONS = (
    "Summary",
    "Statement of need",
    "State of the field",
    "Software design",
    "Demonstrated scope and limitations at v0.1.0",
    "Research impact statement",
    "AI usage disclosure",
    "Acknowledgements",
    "References",
)


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", text))


def test_citation_cff_validates() -> None:
    exe = shutil.which("cffconvert") or str(Path(sys.executable).with_name("cffconvert"))
    r = subprocess.run(
        [exe, "--validate", "-i", str(REPO / "CITATION.cff")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 0, r.stdout + r.stderr


def test_one_title_one_licence_one_author_one_doi() -> None:
    assert CFF["title"] == ZENODO["title"] == "aero-research-platform"
    assert CFF["license"] == PYPROJECT["project"]["license"] == "GPL-3.0-or-later"
    assert ZENODO["license"] == "gpl-3.0-or-later"
    author = CFF["authors"][0]
    full = f"{author['given-names']} {author['family-names']}"
    assert FRONT["authors"][0]["name"] == full
    assert ZENODO["creators"][0]["name"] == f"{author['family-names']}, {author['given-names']}"
    assert CFF["doi"] == CONCEPT_DOI


def test_the_limitation_travels_with_the_metadata() -> None:
    assert L1 in _flat(CFF["abstract"])
    assert L1 in _flat(ZENODO["description"])


def test_zenodo_takes_version_and_date_from_the_release() -> None:
    # Zenodo reads both from the tag and the GitHub Release; a stale value here would win.
    assert "version" not in ZENODO and "publication_date" not in ZENODO
    assert ZENODO["upload_type"] == "software" and ZENODO["access_right"] == "open"


def test_no_operator_placeholder_is_published() -> None:
    # While operator metadata is a sentinel, its key is absent from the published metadata.
    assert "<<OPERATOR-" not in (REPO / "CITATION.cff").read_text(encoding="utf-8")
    assert "<<OPERATOR-" not in (REPO / ".zenodo.json").read_text(encoding="utf-8")
    meta = tomllib.loads((REPO / "docs/release/operator-metadata.toml").read_text(encoding="utf-8"))
    if str(meta["orcid"]).startswith("<<OPERATOR-"):
        assert "orcid" not in CFF["authors"][0] and "orcid" not in ZENODO["creators"][0]
    if str(meta["affiliation"]).startswith("<<OPERATOR-"):
        assert "affiliation" not in CFF["authors"][0] and "affiliation" not in ZENODO["creators"][0]


def test_the_paper_has_the_joss_shape() -> None:
    headings = re.findall(r"^# (.+?)\s*$", BODY, re.M)
    assert headings == list(JOSS_SECTIONS)
    assert "`" not in FRONT["title"]
    assert re.fullmatch(r"\d{1,2} [A-Z][a-z]+ \d{4}", str(FRONT["date"]))
    assert FRONT["bibliography"] == "paper.bib"
    assert FRONT["authors"][0]["corresponding"] is True
    words = len(re.findall(r"\b\w[\w'-]*\b", BODY))
    assert 750 <= words <= 1750, words


def test_every_citation_resolves_and_every_entry_is_cited() -> None:
    bib = (REPO / "paper" / "paper.bib").read_text(encoding="utf-8")
    keys = set(re.findall(r"@([A-Za-z0-9_:\-]+)", BODY))
    entries = set(re.findall(r"^@\w+\{([^,]+),", bib, re.M))
    assert keys - entries == set() and entries - keys == set()
    # Every DOI is the bare form (JOSS links it).
    assert not re.search(r"doi\s*=\s*\{https?://", bib)


def test_the_ai_disclosure_is_generated_not_written() -> None:
    block = re.search(r"<!-- AI-INVENTORY:START -->(.*?)<!-- AI-INVENTORY:END -->", PAPER, re.S)
    assert block is not None and "scripts/ai_usage_inventory.py" in block.group(1)
    assert "<<OPERATOR-AI-HUMAN-REVIEW>>" in PAPER or "AI usage disclosure" in PAPER
