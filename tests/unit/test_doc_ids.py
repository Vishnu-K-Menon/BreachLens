from breachlens.ingest.doc_ids import assign_doc_ids, relative_files


def test_ids_follow_sorted_posix_paths():
    ids = assign_doc_ids(["sheets/b.xlsx", "pdf/a.pdf", "pdf/A.pdf", "pdf/a.pdf"])
    assert ids == {"pdf/A.pdf": "D0001", "pdf/a.pdf": "D0002", "sheets/b.xlsx": "D0003"}


def test_relative_files_are_posix_and_sorted(tmp_path):
    (tmp_path / "sheets").mkdir()
    (tmp_path / "pdf").mkdir()
    for name in ["sheets/z.csv", "pdf/b.pdf", "pdf/a.pdf"]:
        (tmp_path / name).write_text("x", encoding="utf-8")
    assert relative_files(tmp_path) == ["pdf/a.pdf", "pdf/b.pdf", "sheets/z.csv"]
