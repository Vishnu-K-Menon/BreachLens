"""Full corpus generation (`breachlens generate`), layout per ADR-047:

    <out>/docs/          30 PDFs (9 scanned) + 1 exact duplicate + 8 spreadsheets
    <out>/truth/         gt_*.csv + manifest.json
    <out>/../column_corpus/   column-classifier training tables
    <out>/../scale/large_claims.csv

Only `docs/`, `truth/`, `column_corpus/` and `scale/` are replaced; nothing else under the
output directory is touched.
"""

from __future__ import annotations

import logging
import shutil
import zlib
from dataclasses import dataclass
from pathlib import Path

from breachlens.synth.casting import WAGE_STATEMENT, cast_pdfs
from breachlens.synth.column_corpus import build_column_corpus
from breachlens.synth.ground_truth import TruthSummary, build_truth, write_truth
from breachlens.synth.people import build_population, check_reuse_cap, read_pool
from breachlens.synth.records import DocRecord, Rendered
from breachlens.synth.render_pdf import render_pdf
from breachlens.synth.render_sheets import render_all_sheets
from breachlens.synth.scale import write_large_claims
from breachlens.synth.scanify import scanify
from breachlens.synth.settings import SynthSettings

logger = logging.getLogger(__name__)


@dataclass
class GenerateResult:
    out_dir: Path
    truth: TruthSummary
    truth_files: list[Path]


def _reset(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True)


def generate_corpus(
    settings: SynthSettings, root: Path, out_dir: Path, *, corpus_only: bool = False
) -> GenerateResult:
    """Write the corpus. `corpus_only` writes docs/ + truth/ only and leaves the shared
    column corpus and scale file alone (used for held-out corpora)."""
    cfg = settings.config
    docs, truth = out_dir / "docs", out_dir / "truth"
    column_dir, scale_dir = out_dir.parent / "column_corpus", out_dir.parent / "scale"
    for d in (docs, truth) if corpus_only else (docs, truth, column_dir):
        _reset(d)
    pool = read_pool(root / "data" / "reference" / "address_pool.csv")
    pop = build_population(settings, pool)
    check_reuse_cap(pop, cfg.max_unrelated_households_per_address)

    rendered = Rendered()
    plans = cast_pdfs(pop, settings)
    for plan in plans:
        rendered.extend(render_pdf(plan, pop, docs, cfg.seed))
        if plan.scan:
            scanify(
                docs / plan.doc_file,
                docs / plan.doc_file,
                cfg.pdf.scan,
                seed=zlib.crc32(f"{cfg.seed}:{plan.doc_file}".encode()),
            )
    logger.info("rendered %d PDFs (%d scanned)", len(plans), sum(p.scan for p in plans))

    # P25: one byte-identical copy of a wage statement.
    src = [p for p in plans if p.doc_type == WAGE_STATEMENT][2]
    dup_file = src.doc_file.replace(".pdf", "_copy.pdf")
    shutil.copyfile(docs / src.doc_file, docs / dup_file)
    rendered.docs.append(
        DocRecord(
            dup_file,
            "PDF",
            src.doc_type,
            src.doc_date,
            scanned=src.scan,
            duplicate_of=src.doc_file,
            planted={"P25"},
        )
    )

    rendered.extend(render_all_sheets(pop, settings, docs))
    logger.info("rendered 8 spreadsheets")
    if corpus_only:
        columns = scale = {"skipped": "corpus_only (held-out corpus)"}
    else:
        columns = build_column_corpus(
            settings, root / "config" / "column_corpus_aliases.yaml", column_dir
        )
        logger.info("column corpus: %d tables, %d columns", columns["tables"], columns["columns"])
        scale = write_large_claims(settings, scale_dir / "large_claims.csv")
    summary = build_truth(pop, settings, rendered, docs, {"column_corpus": columns, "scale": scale})
    files = write_truth(summary, truth)
    return GenerateResult(out_dir, summary, files)
