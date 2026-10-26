"""Draw the 20 PubMed abstracts for the PREREG v7 spike-in set (a2).

Random, seeded draw via NCBI E-utilities, 4 abstracts per MeSH term. The
filters are humans, English, abstract present, publication year 2015-2026; the
draw never filters on text. A term is sliced by publication year because
esearch cannot page past 10000 records. At most 3 calls per second. Writes
PMID and abstract to $NAM_DATA/spikeins/ (not in the repo). Read-only.

Usage: NAM_DATA=... python -I -m studies.nam.pilot.spikein_draw [--batch N]

Fill rule (PREREG v7): --batch N also draws batches 1..N of 5 abstracts (one per
term, same rotation, same seed) after the 20; only batch N is written, to
$NAM_DATA/spikeins/abstracts_batchN*. At most 8 batches (60 drawn in total).
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
MAX_BATCHES = 8
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


class TermDraw:
    """Seeded stream of abstracts for one MeSH term; next() continues it."""

    def __init__(self, fetcher, mesh, seed=SEED, per_term=PER_TERM):
        self.fetcher, self.mesh = fetcher, mesh
        self.counts = year_counts(fetcher, mesh)
        self.total = sum(self.counts.values())
        if self.total < per_term:
            raise RuntimeError("too few records for %s" % mesh)
        self.rng = random.Random("%d:%s" % (seed, "|".join(mesh)))
        self.seen = set()

    def next(self, taken):
        while True:
            if len(self.seen) >= self.total:
                raise RuntimeError("no more records to draw for %s" % self.mesh)
            index = self.rng.randrange(self.total)
            if index in self.seen:
                continue
            self.seen.add(index)
            year, offset = locate(self.counts, index)
            q = query(self.mesh, year)
            ids = esearch(self.fetcher, q, retstart=offset, retmax=1)["idlist"]
            if not ids:
                raise RuntimeError("empty idlist at offset %d of %s" % (offset, q))
            pmid = ids[0]
            if pmid in taken:
                continue
            taken.add(pmid)
            url = efetch_url(pmid)
            text = abstract_of(self.fetcher.get_bytes(url))
            if not text:
                raise RuntimeError("no abstract for PMID %s (delete cache file %s)"
                                   % (pmid, self.fetcher.path_for(url).name))
            return {"pmid": pmid, "mesh": self.mesh, "year": year,
                    "index": index, "offset": offset, "query": q,
                    "abstract": text}


def draw_term(fetcher, mesh, taken, per_term=PER_TERM, seed=SEED):
    stream = TermDraw(fetcher, mesh, seed, per_term)
    return [stream.next(taken) for _ in range(per_term)], stream.counts


def draw_all(fetcher, batches=0, terms=TERMS, seed=SEED, per_term=PER_TERM):
    """(base rows, [batch rows ...], counts by term).

    The base set is drawn exactly as before (per_term rows per term, terms in
    order). Each batch then takes one more row per term in the same term
    rotation, continuing each term's stream, so the base set never changes.
    """
    taken, streams, base = set(), [], []
    for mesh in terms:
        stream = TermDraw(fetcher, mesh, seed, per_term)
        streams.append(stream)
        base.extend(stream.next(taken) for _ in range(per_term))
    out = [[stream.next(taken) for stream in streams] for _ in range(batches)]
    return base, out, [s.counts for s in streams]


def coding_text(rows, seed):
    """PMID and abstract only, shuffled with the seed to hide the term order."""
    rows = list(rows)
    random.Random(seed).shuffle(rows)
    return "\n\n".join("PMID %s\n%s" % (r["pmid"], r["abstract"])
                        for r in rows) + "\n"


def write_rows(path, rows):
    with open(path, "w") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    batch = 0
    if argv:
        if (len(argv) != 2 or argv[0] != "--batch"
                or argv[1] not in map(str, range(1, MAX_BATCHES + 1))):
            print("usage: spikein_draw [--batch 1..%d] (nothing run)" % MAX_BATCHES)
            return 2
        batch = int(argv[1])
    out_dir = data_dir() / "spikeins"
    out_dir.mkdir(parents=True, exist_ok=True)
    first = out_dir / "abstracts.jsonl"
    if not batch and first.exists():
        print("abstracts.jsonl exists: base set not drawn again (nothing run)")
        return 2
    if batch and not first.exists():
        print("abstracts.jsonl missing: --batch needs the base set (nothing run)")
        return 2
    target = out_dir / ("abstracts_batch%d.jsonl" % batch)
    if batch and target.exists():
        print("batch %d exists (nothing run)" % batch)
        return 2
    fetcher = Fetcher(min_interval=MIN_INTERVAL_S)
    base, batches, counts = draw_all(fetcher, batches=batch)
    record = {"seed": SEED, "date": date.today().isoformat(),
              "terms": [{"mesh": m, "counts_by_year": c}
                        for m, c in zip(TERMS, counts)]}
    if not batch:
        write_rows(out_dir / "abstracts.jsonl", base)
        (out_dir / "draw.json").write_text(json.dumps(record, indent=1))
        (out_dir / "abstracts_for_coding.txt").write_text(coding_text(base, SEED))
        print("drew %d abstracts" % len(base))
        return 0
    old = [json.loads(line)["pmid"] for line in first.open()]
    if old != [r["pmid"] for r in base]:
        raise RuntimeError("the first %d abstracts differ from abstracts.jsonl"
                           % len(old))
    saved = json.loads((out_dir / "draw.json").read_text())["terms"]
    if [t["counts_by_year"] for t in saved] != [
            {str(y): n for y, n in c.items()} for c in counts]:
        raise RuntimeError("counts by year differ from draw.json (keep the cache)")
    rows = batches[batch - 1]
    write_rows(target, rows)
    (out_dir / ("draw_batch%d.json" % batch)).write_text(json.dumps(record, indent=1))
    (out_dir / ("abstracts_batch%d_for_coding.txt" % batch)).write_text(
        coding_text(rows, "%d:batch%d" % (SEED, batch)))
    print("drew batch %d: %d abstracts" % (batch, len(rows)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
