"""The self-checks that make the rest of the repo trustworthy.

If these fail, no number this tool prints should be quoted anywhere.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from ina_sim.physics.ns import load_parameterizations
from ina_sim.references import get_reference, load_references
from ina_sim.validation.runner import load_anchors, run_validation

REPO_ROOT = Path(__file__).resolve().parents[1]
REPORT = run_validation()


def test_every_validation_anchor_passes():
    failures = [r for r in REPORT.results if r.status == "fail"]
    assert not failures, "\n".join(f"{r.id}: {r.detail}" for r in failures)


def test_validation_suite_is_not_empty_or_all_skipped():
    assert REPORT.n_pass >= 4
    assert REPORT.n_skip == 0


@pytest.mark.parametrize("result", REPORT.results, ids=lambda r: r.id)
def test_each_anchor_reports_a_citation_and_a_claim(result):
    assert result.citation and "(" in result.citation
    assert len(result.claim) > 40, "an anchor must say what it is testing and why"


@pytest.mark.parametrize("anchor", load_anchors(), ids=lambda a: a["id"])
def test_every_anchor_cites_a_known_reference(anchor):
    assert anchor["reference"] in load_references()


def test_kaolinite_anchor_is_independent_of_the_shipped_coefficients():
    """The anchor value comes from the paper's prose, not from its equation."""
    anchor = next(a for a in load_anchors() if a["id"] == "kaolinite_rate_at_239k")
    assert "10^5" in anchor["claim"]
    result = next(r for r in REPORT.results if r.id == "kaolinite_rate_at_239k")
    assert abs(result.residual) < result.tolerance


def test_agi_uncertainty_band_is_not_overconfident():
    """A band that does not contain the measurements is a false precision claim."""
    one_sigma = next(r for r in REPORT.results if r.id == "agi_band_covers_measurements")
    two_sigma = next(
        r for r in REPORT.results if r.id == "agi_band_covers_measurements_2sigma"
    )
    assert one_sigma.residual >= 0.6
    assert two_sigma.residual >= 0.94


def test_every_reference_is_locatable():
    """Journal articles need a DOI or URL; books are located by publisher."""
    for key, ref in load_references().items():
        assert ref.authors and ref.year and ref.title, key
        if ref.journal:
            assert ref.doi or ref.url, f"{key} must be findable by DOI or URL"
        else:
            assert ref.publisher, f"{key} must name a publisher"
        assert ref.access in {"verbatim", "derived", "textbook"}, key


def test_every_reference_explains_how_it_is_used():
    for key, ref in load_references().items():
        assert ref.note and len(ref.note) > 30, f"{key} needs a usage note"


def test_no_orphan_references():
    """Every reference must be reachable from a parameterization, an anchor or
    a module that names it, so the bibliography cannot drift into decoration."""
    used = {p.reference for p in load_parameterizations().values()}
    used |= {a["reference"] for a in load_anchors()}
    # Referenced from code rather than data files.
    used |= {"vali1971", "vali2015", "hoose2012", "atkinson2013", "koop2000",
             "crc_handbook", "alduchov1996", "hiranuma2015"}
    orphans = set(load_references()) - used
    assert not orphans, f"unused references: {sorted(orphans)}"


def test_paywalled_sources_record_where_the_number_was_read():
    """Anything not open access must say how it was verified."""
    for key, ref in load_references().items():
        if not ref.open_access and ref.access == "verbatim":
            assert ref.note, key


def test_agi_derived_fit_matches_its_dataset():
    """The shipped AgI coefficients must still be what the script produces."""
    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "tools" / "fit_agi_ns.py"), "--check"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_derived_parameterizations_reference_an_existing_dataset():
    for param in load_parameterizations().values():
        if param.status != "derived":
            continue
        assert (REPO_ROOT / param.dataset).is_file(), param.dataset
        assert (REPO_ROOT / param.derivation).is_file(), param.derivation


def test_reference_citation_formatting():
    ref = get_reference("harrison2019")
    assert ref.short() == "Harrison et al. (2019)"
    assert "doi:10.5194/acp-19-11343-2019" in ref.citation()
    # Two-author papers must not claim "et al.".
    assert get_reference("pruppacher1997").short() == "Pruppacher and Klett (1997)"


def test_generated_docs_are_current():
    """docs/VALIDATION.md and docs/REFERENCES.md are written from the live
    registry, so a stale table is a build failure rather than a quiet lie."""
    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "tools" / "gen_docs.py"), "--check"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
