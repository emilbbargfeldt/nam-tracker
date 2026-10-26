"""Draw the 20 PubMed abstracts for the PREREG v7 spike-in set (a2).

Random, seeded draw via NCBI E-utilities, 4 abstracts per MeSH term. The
filters are humans, English, abstract present, publication year 2015-2026; the
draw never filters on text. A term is sliced by publication year because
esearch cannot page past 10000 records. At most 3 calls per second. Writes
PMID and abstract to $NAM_DATA/spikeins/ (not in the repo). Read-only.

Usage: NAM_DATA=... python -I -m studies.nam.pilot.spikein_draw
"""
import json
import random
import sys
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import date

from studies.nam.inventory.fetch import Fetcher, data_dir

SEED = 20261027
PER_TERM = 4
YEARS = range(2015, 2027)
MAX_PAGED = 9999
MIN_INTERVAL_S = 0.34
BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
TERMS = [
    ["Induced Pluripotent Stem Cells"],
    ["Organoids"],
    ["Microphysiological Systems", "Lab-On-A-Chip Devices"],
    ["Spheroids, Cellular"],
    ["Skin, Artificial"],
]


def query(mesh, year):
    terms = " OR ".join('"%s"[MeSH Terms]' % m for m in mesh)
    return ("(%s) AND humans[MeSH Terms] AND english[Language] "
            "AND hasabstract AND %d[pdat]" % (terms, year))


def esearch_url(term, retstart=0, retmax=0):
    params = {"db": "pubmed", "term": term, "retmode": "json",
              "retstart": retstart, "retmax": retmax, "sort": "pub_date",
              "tool": "nam-tracker"}
    return BASE + "esearch.fcgi?" + urllib.parse.urlencode(params)


def efetch_url(pmid):
    params = {"db": "pubmed", "id": pmid, "retmode": "xml",
              "tool": "nam-tracker"}
    return BASE + "efetch.fcgi?" + urllib.parse.urlencode(params)


def esearch(fetcher, term, retstart=0, retmax=0):
    url = esearch_url(term, retstart, retmax)
    result = json.loads(fetcher.get_bytes(url)).get("esearchresult")
    if (not result or "count" not in result
            or result.get("warninglist", {}).get("phrasesnotfound")
            or result.get("warninglist", {}).get("quotedphrasesnotfound")):
        raise RuntimeError("bad esearch response (delete cache file %s)"
                           % fetcher.path_for(url).name)
    return result


def year_counts(fetcher, mesh):
    counts = {}
    for year in YEARS:
        res = esearch(fetcher, query(mesh, year))
        counts[year] = int(res["count"])
        if counts[year] > MAX_PAGED:
            raise RuntimeError("more than %d records in one year slice" % MAX_PAGED)
    return counts


def locate(counts, index):
    """(year, offset in that year) of the record with global index."""
    for year in YEARS:
        if index < counts[year]:
            return year, index
        index -= counts[year]
    raise IndexError("index outside the counts")


def abstract_of(xml_bytes):
    """Abstract text of the first article, labelled parts joined by blank lines."""
    root = ET.fromstring(xml_bytes)
    parts = []
    article = root.find("./PubmedArticle")
    if article is None:
        return ""
    for node in article.findall("./MedlineCitation/Article/Abstract/AbstractText"):
        text = "".join(node.itertext()).strip()
        label = node.get("Label")
        parts.append("%s: %s" % (label, text) if label else text)
    return "\n\n".join(p for p in parts if p)


def draw_term(fetcher, mesh, taken, per_term=PER_TERM, seed=SEED):
    counts = year_counts(fetcher, mesh)
    total = sum(counts.values())
    if total < per_term:
        raise RuntimeError("too few records for %s" % mesh)
    rng = random.Random("%d:%s" % (seed, "|".join(mesh)))
    chosen, seen = [], set()
    while len(chosen) < per_term:
        if len(seen) >= total:
            raise RuntimeError("no more records to draw for %s" % mesh)
        index = rng.randrange(total)
        if index in seen:
            continue
        seen.add(index)
        year, offset = locate(counts, index)
        q = query(mesh, year)
        ids = esearch(fetcher, q, retstart=offset, retmax=1)["idlist"]
        if not ids:
            raise RuntimeError("empty idlist at offset %d of %s" % (offset, q))
        pmid = ids[0]
        if pmid in taken:
            continue
        taken.add(pmid)
        url = efetch_url(pmid)
        text = abstract_of(fetcher.get_bytes(url))
        if not text:
            raise RuntimeError("no abstract for PMID %s (delete cache file %s)"
                               % (pmid, fetcher.path_for(url).name))
        chosen.append({"pmid": pmid, "mesh": mesh, "year": year, "index": index,
                       "offset": offset, "query": q, "abstract": text})
    return chosen, counts


def main():
    out_dir = data_dir() / "spikeins"
    out_dir.mkdir(parents=True, exist_ok=True)
    fetcher = Fetcher(min_interval=MIN_INTERVAL_S)
    taken, drawn, record = set(), [], {"seed": SEED, "date": date.today().isoformat(),
                                      "terms": []}
    for mesh in TERMS:
        chosen, counts = draw_term(fetcher, mesh, taken)
        drawn.extend(chosen)
        record["terms"].append({"mesh": mesh, "counts_by_year": counts})
    with open(out_dir / "abstracts.jsonl", "w") as fh:
        for row in drawn:
            fh.write(json.dumps(row) + "\n")
    (out_dir / "draw.json").write_text(json.dumps(record, indent=1))
    print("drew %d abstracts" % len(drawn))
    return 0


if __name__ == "__main__":
    sys.exit(main())
