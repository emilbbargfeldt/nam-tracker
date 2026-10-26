"""Known-answer tests for the layer 2 keyword filter, with two mutants."""

from pathlib import Path

import time

import pytest

from core.quotecheck import _normalize
from studies.nam.extract import keywords


def _codes(text):
    return {code for code, hits in keywords.match_page(text).items() if hits}


A_FORMS = [
    "organ-\non-a-chip",
    "organ\u2010on\u2010a\u2010chip",
    "organ\u2013on\u2013a\u2013chip",
    "organ on\na chip",
    "three-\ndimensional",
    "stem cell-\nderived",
    "hiPS-CMs",
    "3D liver model",
    "liver chip",
    "air-liquid interface",
    "The  cells  were   grown  in  an  organ   on  a  chip  system",
]


@pytest.mark.parametrize("text", A_FORMS)
def test_a_matches_form(text):
    assert "A" in _codes(text)


def test_a_negative():
    assert "A" not in _codes("2D monolayer of HEK293 cells")


@pytest.mark.parametrize("code, positive, negative", [
    ("A", "Liver organoids were used.", "2D monolayer of HEK293 cells"),
    ("B", "A PBPK model was built.", "Given by oral gavage."),
    ("C", "The Ames test was negative.", "Liver organoids were used."),
    ("D", "The study was waived.", "Dose escalation was performed."),
    ("S", "Beagle dogs received the dose.", "Human volunteers received it."),
])
def test_code_positive_and_negative(code, positive, negative):
    assert code in _codes(positive)
    assert code not in _codes(negative)


def test_all_codes_are_keys_and_offsets_are_in_normalized_text():
    text = "organ-\non-a-chip in rats"
    hits = keywords.match_page(text)
    assert set(hits) == set("ABCDS")
    page = _normalize(text)
    template, start, end = hits["S"][0]
    assert page[start:end] == "rats"


def test_normalization_pin():
    # keywords.py relies on this behaviour; if it changes, re-check the lists.
    assert _normalize("organ-\non-a-chip") == "organon-a-chip"
    assert _normalize("a  b\nc") == "a b c"


def test_normalization_pin_soft_hyphen():
    # U+00AD is removed by the normalization, so SEP does not need to hold it.
    assert _normalize("organ\u00adon-a-chip") == "organon-a-chip"
    assert _normalize("three\u00ad\ndimensional") == "threedimensional"


def test_normalization_pin_unicode_hyphens():
    # U+2010, U+2011 and U+2013 become "-", so SEP's Unicode part is redundant.
    for ch in ("\u2010", "\u2011", "\u2013"):
        assert _normalize("organ%son-a-chip" % ch) == "organ-on-a-chip"


def test_keywords_file_is_ascii():
    data = Path(keywords.__file__).read_bytes()
    assert all(b < 128 for b in data)


def _with(monkeypatch, compiled):
    monkeypatch.setattr(keywords, "_COMPILED", compiled)


def test_mutant_without_a_patterns_is_caught(monkeypatch):
    templates = dict(keywords.TEMPLATES, A=[])
    _with(monkeypatch, keywords._build(keywords.SEP, templates))
    for text in A_FORMS:
        assert "A" not in _codes(text), text
    # and the real tests above would fail: the positive form is not found
    with pytest.raises(AssertionError):
        test_a_matches_form("3D liver model")


def _templates(text):
    return {t for t, _, _ in keywords.match_page(text)["A"]}


# form -> the specific template that must lose it under a rigid separator
_RIGID = {
    "organ-\non-a-chip": r"organs?SEPon(SEPa)?SEPchips?",
    "three-\ndimensional": r"threeSEPdimensional",
    "stem cell-\nderived": r"stemSEPcells?SEPderived",
}


@pytest.mark.parametrize("text, template", sorted(_RIGID.items()))
def test_mutant_rigid_separator_is_caught(monkeypatch, text, template):
    assert template in _templates(text)  # real SEP finds it
    _with(monkeypatch, keywords._build("[- ]"))
    assert template not in _templates(text)  # SEP = "[- ]" loses it


def test_rigid_separator_still_matches_unicode_hyphen_forms(monkeypatch):
    # quotecheck normalization maps U+2010 and U+2013 to "-" before matching,
    # so a rigid "[- ]" separator cannot be caught by those forms; the unicode
    # part of SEP is defence in depth.
    _with(monkeypatch, keywords._build("[- ]"))
    for text in ["organ\u2010on\u2010a\u2010chip", "organ\u2013on\u2013a\u2013chip"]:
        assert r"organs?SEPon(SEPa)?SEPchips?" in _templates(text)


# One positive example per A template; each is matched by that template
# compiled alone (with the real SEP), so the test is per pattern, not per code.
A_EXAMPLES = {
    r"organoid": "liver organoids",
    r"spheroid": "tumour spheroids",
    r"\b3SEPD\b": "3D liver model",
    r"threeSEPdimensional": "three-\ndimensional culture",
    r"organs?SEPon(SEPa)?SEPchips?": "organ-on-a-chip",
    r"\w{1,40}SEPchips?\b": "liver chip",
    r"microphysiolog": "microphysiological system",
    r"\bMPS\b": "an MPS platform",
    r"microfluidic": "microfluidic device",
    r"\bh?iPSCs?\b": "hiPSCs were used",
    r"\bh?iPS\b": "iPS cells",
    r"iPSSEPCMs?": "iPS-CMs",
    r"inducedSEPpluripotent": "induced pluripotent stem cells",
    r"stemSEPcells?SEPderived": "stem cell-\nderived",
    r"\bESCSEPderived": "ESC-derived neurons",
    r"embryonicSEPstemSEPcell": "embryonic stem cell",
    r"cardiomyocyte": "cardiomyocytes",
    r"\bCiPA\b": "the CiPA initiative",
    r"precisionSEPcut": "precision-cut slices",
    r"\bPCLS\b": "PCLS were incubated",
    r"tissueSEPslices?": "tissue slices",
    r"exSEPvivoSEPhuman": "ex vivo human tissue",
    r"humanSEP\w+SEPexplants?": "human skin explants",
    r"reconstructedSEPhuman": "reconstructed human epidermis",
    r"reconstitutedSEPhuman": "reconstituted human tissue",
    r"humanSEPskinSEPmodels?": "human skin model",
    r"EpiDerm": "EpiDerm test",
    r"EpiSkin": "EpiSkin test",
    r"EpiOcular": "EpiOcular test",
    r"EpiAirway": "EpiAirway test",
    r"MatTek": "from MatTek",
    r"airSEPliquidSEPinterface": "air-liquid interface",
    r"\bALI\b": "ALI culture",
    r"coSEPcultures?": "co-culture",
    r"sandwichSEPcultured": "sandwich cultured",
    r"primarySEPhumanSEPhepatocytes?": "primary human hepatocytes",
    r"tissueSEPengineered": "tissue-engineered",
    r"bioprint": "bioprinted",
    r"scaffold": "a scaffold",
    r"microtissue": "microtissues",
    r"humanSEPtissueSEPmodels?": "human tissue model",
    r"3SEPD(SEPbio)?SEPprinted": "3D bioprinted",
}


def test_a_examples_cover_every_a_template():
    assert set(A_EXAMPLES) == set(keywords.TEMPLATES["A"])


@pytest.mark.parametrize("template", keywords.TEMPLATES["A"])
def test_a_template_matches_its_example(template):
    only = {code: [] for code in keywords.CODES}
    only["A"] = [template]
    compiled = keywords._build(keywords.SEP, only)
    page = _normalize(A_EXAMPLES[template])
    assert compiled["A"][0][1].search(page)


def test_pathological_pages_are_fast():
    n = 20000
    for page in ["a" * n, ("a-" * n)[:n], ("a " * n)[:n], ("chip" * n)[:n]]:
        start = time.perf_counter()
        keywords.match_page(page)
        assert time.perf_counter() - start < 0.5
