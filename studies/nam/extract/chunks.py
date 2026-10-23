"""Split the layer 1 pages of a document into chunks of at most about 50,000
tokens (characters / 4), with an overlap of one page."""
import hashlib

MAX_CHARS = 200000


def render(page_no, text):
    return "=== Page %d ===\n%s\n" % (page_no, text.strip("\n"))


def chunk_pages(pages, page_numbers, max_chars=MAX_CHARS):
    """pages: texts, page n at index n-1; page_numbers: the pages to read, in
    order. Returns [{"index", "pages", "text", "hash"}]. Each chunk starts with
    the last page of the previous one when both fit; a single page above the
    limit is a chunk of its own."""
    sizes = {p: len(render(p, pages[p - 1])) for p in page_numbers}
    groups, cur, size, i = [], [], 0, 0
    while i < len(page_numbers):
        p = page_numbers[i]
        if cur and size + sizes[p] > max_chars:
            groups.append(cur)
            last = cur[-1]
            cur = [last] if sizes[last] + sizes[p] <= max_chars else []
            size = sum(sizes[x] for x in cur)
            continue
        cur.append(p)
        size += sizes[p]
        i += 1
    if cur:
        groups.append(cur)
    out = []
    for n, group in enumerate(groups, 1):
        text = "".join(render(p, pages[p - 1]) for p in group)
        out.append({"index": n, "pages": group, "text": text,
                    "hash": hashlib.sha256(text.encode()).hexdigest()})
    return out
