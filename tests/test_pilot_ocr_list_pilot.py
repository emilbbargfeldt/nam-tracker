import json

from studies.nam.pilot import draw, ocr_list_pilot


def test_pilot_counts_known_answer():
    raw = {"A": ("pa", 10, [2, 3, 7]), "B": ("pb", 4, []), "C": None}
    t = ocr_list_pilot.pilot_counts(
        raw, raw.get, lambda doc, pages: {3: "x"} if doc == "A" else {})
    assert t == {"documents": 3, "missing": 1, "layer1": 14, "low": 3,
                 "todo": 2, "in_cache": 1}


def test_main_prints_only_counts_and_writes_nothing(tmp_path, monkeypatch, capsys):
    out = tmp_path / "pilot.json"
    out.write_text(json.dumps({"items": [
        {"authority": "FDA", "year": 2020, "name": "Drug One", "id": 1,
         "url": "u1", "format": "f"}]}))
    monkeypatch.setattr(draw, "OUT", out)
    monkeypatch.setattr(ocr_list_pilot.spikein, "read_only_fetcher",
                        lambda cls: (lambda: object()))
    monkeypatch.setattr(ocr_list_pilot.ocr_list, "make_raw_loader",
                        lambda f, items: (lambda d: ("p", 5, [1, 2]),
                                          lambda d, pages: {1: "x"}))
    before = sorted(p.name for p in tmp_path.iterdir())
    assert ocr_list_pilot.main([]) == 0
    text = capsys.readouterr().out
    assert "before OCR 2, in OCR cache 1, todo 1" in text
    assert len(text.strip().splitlines()) == 2
    assert sorted(p.name for p in tmp_path.iterdir()) == before


def test_main_rejects_arguments(capsys):
    assert ocr_list_pilot.main(["x"]) == 2
