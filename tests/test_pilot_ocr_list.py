import json

import pytest

from studies.nam.pilot import ocr_list


def test_a1_doc_ids_union_sorted_unique(tmp_path):
    (tmp_path / "batch1.json").write_text(json.dumps(
        {"draws": [{"doc": "B", "page": "1"}, {"doc": "A", "page": "2"}]}))
    (tmp_path / "batch2.json").write_text(json.dumps(
        {"draws": [{"doc": "A", "page": "9"}, {"doc": "C", "page": "3"}]}))
    (tmp_path / "batch1.rc").write_text("ignored")
    assert ocr_list.a1_doc_ids(tmp_path) == ["A", "B", "C"]


def test_collect_known_answer_and_todo():
    raw = {"A": ("pa", 10, [2, 3, 7]), "B": ("pb", 4, []), "C": None}
    rows = ocr_list.collect(["A", "B", "C"], raw.get,
                            lambda doc, pages: {3: "text"} if doc == "A" else {})
    assert rows[0] == {"doc": "A", "pdf": "pa", "layer1": 10,
                       "low": [2, 3, 7], "todo": [2, 7]}
    assert rows[1]["low"] == [] and rows[1]["todo"] == []
    assert rows[2]["missing"] is True and rows[2]["low"] == []
    assert ocr_list.totals(rows) == {"documents": 3, "missing": 1, "layer1": 14,
                                     "low": 3, "todo": 2}


def test_totals_empty():
    assert ocr_list.totals([]) == {"documents": 0, "missing": 0, "layer1": 0,
                                   "low": 0, "todo": 0}


def test_write_new_refuses_to_overwrite(tmp_path):
    path = tmp_path / "m.json"
    ocr_list.write_new(path, {"x": 1})
    assert json.loads(path.read_text()) == {"x": 1}
    with pytest.raises(FileExistsError):
        ocr_list.write_new(path, {"x": 2})
    assert json.loads(path.read_text()) == {"x": 1}
    assert not list(tmp_path.glob("*.tmp"))


def test_bad_tag_runs_nothing(capsys):
    assert ocr_list.main(["../x"]) == 2
    assert ocr_list.main([]) == 2
    assert ocr_list.main(["caf\u00e9"]) == 2


class FakeFetcher:
    root = None


@pytest.fixture
def wired(tmp_path, monkeypatch):
    """main() with fakes: root in tmp_path, two a1 docs, one a2 doc."""
    FakeFetcher.root = tmp_path
    monkeypatch.setattr(ocr_list, "Fetcher", FakeFetcher)
    monkeypatch.setattr(ocr_list.spikein, "read_only_fetcher", lambda cls: cls)
    items = {"D1": {}, "D2": {}, "D3": {}}
    monkeypatch.setattr(ocr_list.spikein, "real_loader", lambda f: (items, None))
    raw = {"D1": ("p1", 10, [1, 2]), "D2": ("p2", 5, []), "D3": ("p3", 8, [4])}
    monkeypatch.setattr(ocr_list, "make_raw_loader",
                        lambda f, it: (raw.get, lambda doc, pages: {}))
    monkeypatch.setattr(ocr_list, "a1_doc_ids", lambda d: ["D1", "D2"])
    monkeypatch.setattr(ocr_list, "a2_doc_ids", lambda f, it, load: ["D3"])
    return tmp_path


def test_main_writes_manifest_and_prints_counts_only(wired, capsys):
    assert ocr_list.main(["r0"]) == 0
    out = capsys.readouterr().out
    assert "a1: documents 2" in out and "below 100 chars 2" in out
    assert "a2: documents 1" in out and "below 100 chars 1" in out
    data = json.loads((wired / "pilot" / "ocr_manifest_r0.json").read_text())
    assert data["parts"]["a1"][0]["low"] == [1, 2]
    assert data["parts"]["a2"][0]["todo"] == [4]
    assert not list((wired / "pilot").glob("*.tmp"))


def test_main_unknown_a1_id_exits_2_without_writing(wired, monkeypatch):
    monkeypatch.setattr(ocr_list, "a1_doc_ids", lambda d: ["D1", "NOPE"])
    assert ocr_list.main(["r0"]) == 2
    assert not (wired / "pilot").exists()


def test_main_same_tag_twice_is_refused(wired, capsys):
    assert ocr_list.main(["r0"]) == 0
    first = (wired / "pilot" / "ocr_manifest_r0.json").read_text()
    assert ocr_list.main(["r0"]) == 2
    assert (wired / "pilot" / "ocr_manifest_r0.json").read_text() == first


def test_main_spike_error_exits_2_without_writing(wired, monkeypatch):
    def boom(f, it, load):
        raise ocr_list.spikein.SpikeError("codes differ")
    monkeypatch.setattr(ocr_list, "a2_doc_ids", boom)
    assert ocr_list.main(["r0"]) == 2
    assert not (wired / "pilot").exists()
