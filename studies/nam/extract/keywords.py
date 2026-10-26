"""Layer 2: keyword search that selects candidate pages per code (A, B, C, D, S).

Runs locally on page text. No network, no model, no file writes. Matching
is done on the text after the quotecheck normalization (NFKC, line-end
hyphens removed, blank runs collapsed to one space). Offsets returned by
match_page therefore refer to the normalized text, not to the raw page text.

Patterns are written with the token SEP where a word boundary may hold a
hyphen, a Unicode hyphen or dash, or white space (or nothing, because the
normalization joins words split by "-" at a line end). SEP is defined once
and substituted by _build. The list is deliberately broad: only sensitivity
for A matters, and false hits are rejected by the model in the next step.
"""

import re

from core.quotecheck import _normalize

SEP = r"[-\u2010\u2011\u2013\s]?"

CODES = ("A", "B", "C", "D", "S")

# A: advanced human in vitro models
_A = [
    r"organoid", r"spheroid", r"\b3SEPD\b", r"threeSEPdimensional",
    r"organs?SEPon(SEPa)?SEPchips?", r"\w{1,40}SEPchips?\b",
    r"microphysiolog", r"\bMPS\b", r"microfluidic",
    r"\bh?iPSCs?\b", r"\bh?iPS\b", r"iPSSEPCMs?", r"inducedSEPpluripotent",
    r"stemSEPcells?SEPderived", r"\bESCSEPderived", r"embryonicSEPstemSEPcell",
    r"cardiomyocyte", r"\bCiPA\b",
    r"precisionSEPcut", r"\bPCLS\b", r"tissueSEPslices?", r"exSEPvivoSEPhuman",
    r"humanSEP\w+SEPexplants?",
    r"reconstructedSEPhuman", r"reconstitutedSEPhuman", r"humanSEPskinSEPmodels?",
    r"EpiDerm", r"EpiSkin", r"EpiOcular", r"EpiAirway", r"MatTek",
    r"airSEPliquidSEPinterface", r"\bALI\b",
    r"coSEPcultures?", r"sandwichSEPcultured", r"primarySEPhumanSEPhepatocytes?",
    r"tissueSEPengineered", r"bioprint", r"scaffold", r"microtissue",
    r"humanSEPtissueSEPmodels?", r"3SEPD(SEPbio)?SEPprinted",
]

# B: in silico
_B = [
    r"PBPK", r"physiologicallySEPbased", r"inSEPsilico", r"\(?Q\)?SAR\b",
    r"computationalSEPmodels?", r"readSEPacross", r"machineSEPlearning",
    r"\bDerek\b", r"SarahSEPNexus", r"CASESEPUltra", r"Leadscope",
    r"modelSEPinformed",
]

# C: routine in vitro
_C = [
    r"hERG", r"\bAmes\b", r"bacterialSEPreverseSEPmutation",
    r"chromosom\w*SEPaberration", r"micronucle", r"mouseSEPlymphoma",
    r"receptorSEPbinding", r"offSEPtarget", r"safetySEPpanel", r"cytotoxic",
    r"phototox", r"3T3", r"inSEPvitro",
]

# D: omitted animal study
_D = [
    r"waive", r"waiver", r"not(SEPbeen)?SEPconducted",
    r"(were|was)SEPnotSEPperformed", r"notSEPrequired", r"notSEPnecessary",
    r"noSEP(pharmacologicallySEP)?relevantSEPspecies", r"relevantSEPspecies",
    r"weightSEPofSEPevidence", r"ICHSEPS6", r"ICHSEPS9", r"ICHSEPM3",
    r"carcinogenicitySEPassessment", r"\b3Rs\b", r"reduc\w*SEPanimal",
    r"animalSEPuse",
]

# S: animal species
_S = [
    r"\brats?\b", r"\bmouse\b", r"\bmice\b", r"murine", r"\bdogs?\b",
    r"beagle", r"canine", r"miniSEPpigs?", r"\bpigs?\b", r"porcine",
    r"rabbit", r"monkey", r"nonSEPhumanSEPprimates?", r"\bNHPs?\b",
    r"cynomolgus", r"rhesus", r"marmoset", r"guineaSEPpigs?", r"hamster",
    r"ferret", r"zebrafish",
]

TEMPLATES = {"A": _A, "B": _B, "C": _C, "D": _D, "S": _S}


def _build(sep, templates=None):
    """Compile the templates with sep substituted for SEP, per code."""
    templates = TEMPLATES if templates is None else templates
    return {
        code: [(t, re.compile(t.replace("SEP", sep), re.IGNORECASE))
               for t in templates[code]]
        for code in CODES
    }


_COMPILED = _build(SEP)


def match_page(text):
    """Return {code: [(pattern, start, end), ...]} for one page of text.

    All five codes are always keys. pattern is the template as written in
    this file (with SEP). start and end are offsets in the normalized text
    (quotecheck normalization), not in the raw page text.
    """
    page = _normalize(text)
    return {
        code: [(template, m.start(), m.end())
               for template, rx in _COMPILED[code]
               for m in rx.finditer(page)]
        for code in CODES
    }
