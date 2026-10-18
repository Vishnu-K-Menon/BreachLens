"""Label-anchored field extraction from YAML templates (ADR-007).

One template per document type and layout (`config/doc_templates/*.yaml`). Each field
names a printed label and where its value sits relative to it:

- `right`  same line, tokens to the right of the label, stopping at a gap or at the next
           label on that line
- `below`  the next `lines` lines under the label, inside the label's column (from the
           label's left edge to the next label on the label's line)
- `inline` a regex with one capture group, matched against each line's text
- `block`  the lines that follow an anchor line (`inline` regex), e.g. a letter's address

Labels are matched as whole words, case-insensitive; for OCR text a fuzzy match
(rapidfuzz) is the fallback. Values then get OCR character repair (`shape` / `charset`),
an optional `pattern`, and parsing (`digits`, `date`, `year_end`). Every field reports a
diagnostic status so extraction failures can be explained.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict
from rapidfuzz import fuzz

from breachlens.ingest.tokens import Line, Token, group_lines

OK, LABEL_NOT_FOUND, NO_VALUE, PATTERN_MISS, PARSE_FAIL = (
    "OK",
    "LABEL_NOT_FOUND",
    "NO_VALUE",
    "PATTERN_MISS",
    "PARSE_FAIL",
)
FUZZY_MIN = 88.0
DIGIT_FIX = {
    "O": "0",
    "o": "0",
    "D": "0",
    "Q": "0",
    "I": "1",
    "l": "1",
    "|": "1",
    "i": "1",
    "S": "5",
    "s": "5",
    "B": "8",
    "Z": "2",
    "z": "2",
    "G": "6",
    "T": "7",
}
LETTER_FIX = {"0": "O", "1": "I", "2": "Z", "5": "S", "8": "B", "6": "G", "4": "A"}


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class FieldSpec(_Strict):
    label: str | None = None
    label_regex: str | None = None
    # Shorter fallbacks when OCR loses part of the label (tried after `label`).
    alt_labels: list[str] = []
    direction: Literal["right", "below", "inline", "block"] = "right"
    lines: int = 1
    max_distance: float = 40.0
    pattern: str | None = None
    findall: bool = False
    shape: str | None = None
    charset: Literal["digits"] | None = None
    parse: Literal["text", "digits", "date", "year_end"] = "text"
    formats: list[str] = []
    inline: str | None = None


class IdentifierSpec(FieldSpec):
    kind: Literal["EIN", "NPI", "PROVIDER_TIN"]


class PersonSpec(_Strict):
    name_order: Literal["FIRST_LAST", "LAST_COMMA_FIRST"] = "FIRST_LAST"
    compose_name: str | None = None
    skip_if_name: list[str] = ["SAME"]
    merge_into_if_absent: str | None = None
    block_name_address: FieldSpec | None = None
    fields: dict[str, FieldSpec] = {}


class Keyword(_Strict):
    text: str
    weight: float = 1.0


class DocDateSpec(_Strict):
    field: str | None = None
    rule: FieldSpec | None = None


class Template(_Strict):
    doc_type: str
    layout: str
    keywords: list[Keyword]
    min_score: float | None = None
    doc_date: DocDateSpec = DocDateSpec()
    document: dict[str, FieldSpec] = {}
    persons: dict[str, PersonSpec]
    identifiers: list[IdentifierSpec] = []
    # Printed labels that are not extracted but bound neighbouring values (box edges).
    boundaries: list[str] = []

    @property
    def name(self) -> str:
        return f"{self.doc_type}_{self.layout}"

    def all_specs(self) -> list[FieldSpec]:
        out = list(self.document.values()) + list(self.identifiers)
        for p in self.persons.values():
            out += list(p.fields.values())
        return out


def load_templates(directory: Path) -> list[Template]:
    out = []
    for path in sorted(directory.glob("*.yaml")):
        with path.open(encoding="utf-8") as fh:
            out.append(Template.model_validate(yaml.safe_load(fh)))
    if not out:
        raise ValueError(f"no templates in {directory}")
    return out


# ---- text helpers -------------------------------------------------------------------
def norm(s: str) -> str:
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return " ".join(s.split())


def label_regex(spec: FieldSpec) -> re.Pattern[str] | None:
    if spec.label_regex:
        return re.compile(spec.label_regex, re.I)
    if spec.label:
        words = [re.escape(w) for w in norm(spec.label).split()]
        # \s* between words: OCR often drops the space ("Employee'sname").
        return re.compile(r"(?<![\w'])" + r"\s*".join(words) + r"(?![\w'])", re.I)
    return None


def repair_shape(value: str, shape: str) -> str:
    """Per-position OCR repair: 'L' wants a letter, 'D' a digit, '*' ends the shape."""
    out, k = [], 0
    for ch in value:
        if not ch.isalnum():
            out.append(ch)
            continue
        want = shape[k] if k < len(shape) else "*"
        if want == "*":
            out.append(ch)
            k = len(shape) + 1
            continue
        if want == "L" and ch.isdigit():
            ch = LETTER_FIX.get(ch, ch)
        elif want == "D" and not ch.isdigit():
            ch = DIGIT_FIX.get(ch, ch)
        out.append(ch)
        k += 1
    return "".join(out)


STRAY_MARKS = set("~^`'\"")


def repair_digits(value: str) -> str:
    """Letters that OCR confuses with digits become digits; stray marks (~ ^ ` ' ") go."""
    return "".join(
        DIGIT_FIX.get(ch, ch) if ch.isalpha() or ch == "|" else ch
        for ch in value
        if ch not in STRAY_MARKS
    )


def parse_date(text: str, formats: list[str], as_of: date) -> date | None:
    """Try `formats`; a 2-digit year pivots on `as_of` (yy > as_of_yy -> 19yy, else 20yy)."""
    s = norm(text)
    for fmt in formats:
        try:
            dt = datetime.strptime(s, fmt).date()
        except ValueError:
            continue
        if "%y" in fmt:
            yy = dt.year % 100
            dt = dt.replace(year=(1900 if yy > as_of.year % 100 else 2000) + yy)
        return dt
    return None


# ---- page model -----------------------------------------------------------------------
@dataclass(frozen=True)
class Hit:
    line: int
    x0: float
    x1: float
    top: float
    bottom: float


@dataclass
class Value:
    text: str
    conf: float


@dataclass
class Page:
    tokens: list[Token]
    ocr: bool
    lines: list[Line] = field(init=False)

    def __post_init__(self) -> None:
        self.lines = group_lines(self.tokens)

    def find(self, spec: FieldSpec) -> Hit | None:
        hit = self._find_one(spec)
        for alt in spec.alt_labels:
            if hit is not None:
                break
            hit = self._find_one(FieldSpec(label=alt))
        return hit

    def _find_one(self, spec: FieldSpec) -> Hit | None:
        rx = label_regex(spec)
        if rx is None:
            return None
        for i, line in enumerate(self.lines):
            m = rx.search(norm(line.text))
            if m:
                toks = line.tokens_in(m.start(), m.end())
                if toks:
                    return Hit(
                        i,
                        toks[0].x0,
                        toks[-1].x1,
                        min(t.top for t in toks),
                        max(t.bottom for t in toks),
                    )
        if self.ocr and spec.label and not spec.label_regex:
            return self._fuzzy(spec.label)
        return None

    def _fuzzy(self, label: str) -> Hit | None:
        best: tuple[float, int, int, int] | None = None
        target = norm(label).lower()
        for i, line in enumerate(self.lines):
            al = fuzz.partial_ratio_alignment(target, norm(line.text).lower())
            if al is not None and al.score >= FUZZY_MIN and (best is None or al.score > best[0]):
                best = (al.score, i, al.dest_start, al.dest_end)
        if best is None:
            return None
        _, i, a, b = best
        toks = self.lines[i].tokens_in(a, b)
        if not toks:
            return None
        return Hit(
            i, toks[0].x0, toks[-1].x1, min(t.top for t in toks), max(t.bottom for t in toks)
        )


class Extractor:
    """Runs one template over one page of tokens."""

    def __init__(self, template: Template, page: Page, as_of: date) -> None:
        self.t, self.page, self.as_of = template, page, as_of
        self.hits: dict[int, Hit | None] = {}
        self._keep: list[FieldSpec] = []
        self.last_raw = ""
        for spec in template.all_specs():
            if spec.label or spec.label_regex:
                self.hits[id(spec)] = page.find(spec)
        for text in template.boundaries:
            spec = FieldSpec(label=text)
            self.hits[id(spec)] = page.find(spec)
            self._keep.append(spec)  # keep ids stable while the extractor lives
        self.label_spans = [h for h in self.hits.values() if h is not None]

    def _stop_x(self, hit: Hit, region_bottom: float | None = None) -> float:
        """Right edge of a value: the nearest label to the right on the label's line, or,
        for `below` values, any label to the right that overlaps the value region."""
        xs = [h.x0 for h in self.label_spans if h.line == hit.line and h.x0 > hit.x1 + 1]
        if region_bottom is not None:
            xs += [
                h.x0
                for h in self.label_spans
                if h.x0 > hit.x0 + 20 and h.top < region_bottom and h.bottom > hit.top - 2
            ]
        return min(xs) if xs else 10_000.0

    def _line_stop(self, hit: Hit, line: Line, near: float = 14.0) -> float:
        """Right edge for one value line under `hit`: labels on the label's line, plus
        labels to the right that sit vertically close to this value line (box edges)."""
        xs = [h.x0 for h in self.label_spans if h.line == hit.line and h.x0 > hit.x1 + 1]
        xs += [
            h.x0
            for h in self.label_spans
            if h.x0 > hit.x0 + 20 and h.top < line.bottom + near and h.bottom > line.top - near
        ]
        return min(xs) if xs else 10_000.0

    def _is_label_token(self, line_idx: int, tok: Token) -> bool:
        return any(
            h.line == line_idx and h.x0 - 0.5 <= tok.x0 <= h.x1 + 0.5 for h in self.label_spans
        )

    def _collect(self, spec: FieldSpec, hit: Hit) -> list[list[Token]]:
        lines = self.page.lines
        stop = self._stop_x(hit)
        if spec.direction == "right":
            row = [t for t in lines[hit.line].tokens if t.x0 >= hit.x1 - 0.5 and t.x1 <= stop + 2]
            row = [t for t in row if not self._is_label_token(hit.line, t)]
            out: list[Token] = []
            last_x1 = hit.x1
            for t in row:
                if t.x0 - last_x1 > spec.max_distance:
                    break
                out.append(t)
                last_x1 = t.x1
            return [out] if out else []
        # below
        groups: list[list[Token]] = []
        prev_bottom = hit.bottom
        for j in range(hit.line + 1, len(lines)):
            line = lines[j]
            if line.top - prev_bottom > spec.max_distance:
                break
            stop = self._line_stop(hit, line)
            col = [t for t in line.tokens if hit.x0 - 8 <= t.x0 and t.x1 <= stop + 2]
            if not col:
                continue
            if all(self._is_label_token(j, t) for t in col):
                break
            groups.append([t for t in col if not self._is_label_token(j, t)])
            prev_bottom = line.bottom
            if len(groups) >= spec.lines:
                break
        return groups

    def _inline(self, spec: FieldSpec) -> tuple[Value | None, int | None]:
        rx = re.compile(spec.inline or "", re.I)
        for i, line in enumerate(self.page.lines):
            m = rx.search(norm(line.text))
            if m:
                g = 1 if m.groups() else 0
                toks = line.tokens_in(m.start(g), m.end(g)) or line.tokens
                return Value(m.group(g), _conf(toks)), i
        return None, None

    def block(self, spec: FieldSpec) -> tuple[list[Value], str]:
        """Lines after an anchor line (e.g. the date line of a letter)."""
        _, idx = self._inline(spec)
        if idx is None:
            return [], LABEL_NOT_FOUND
        lines, out = self.page.lines, []
        prev = lines[idx]
        for j in range(idx + 1, min(idx + 1 + spec.lines, len(lines))):
            # The first block line may sit further below the anchor; later lines must be
            # contiguous (gap <= max_distance).
            limit = spec.max_distance * 4 if not out else spec.max_distance
            if lines[j].top - prev.bottom > limit:
                break
            out.append(Value(norm(lines[j].text), _conf(lines[j].tokens)))
            prev = lines[j]
        return out, (OK if out else NO_VALUE)

    def value(self, spec: FieldSpec) -> tuple[str | None, float, str]:
        """(value, confidence, diagnostic status) for one field. The printed text of the
        last call is kept in `last_raw` (date fields keep it as `_raw_<field>`)."""
        self.last_raw = ""
        if spec.direction == "inline":
            v, _ = self._inline(spec)
            if v is None:
                return None, 0.0, LABEL_NOT_FOUND
            text, conf = v.text, v.conf
            self.last_raw = text
        else:
            if id(spec) not in self.hits:  # a spec not seen at construction: find it now
                self.hits[id(spec)] = self.page.find(spec)
                self._keep.append(spec)
            hit = self.hits[id(spec)]
            if hit is None:
                return None, 0.0, LABEL_NOT_FOUND
            groups = self._collect(spec, hit)
            if not groups or not any(groups):
                return None, 0.0, NO_VALUE
            text = "\n".join(" ".join(t.text for t in g) for g in groups if g)
            conf = _conf([t for g in groups for t in g])
            self.last_raw = text
        return self._finish(spec, text, conf)

    def _finish(self, spec: FieldSpec, text: str, conf: float) -> tuple[str | None, float, str]:
        if spec.charset == "digits":
            text = repair_digits(text)
        if spec.pattern:
            if spec.findall:
                words = [repair_shape(w, spec.shape) if spec.shape else w for w in text.split()]
                found = [m.group(0) for w in words for m in re.finditer(spec.pattern, w)]
                if not found:
                    return None, conf, PATTERN_MISS
                text = ";".join(found)
            else:
                cand = text
                m = None
                if spec.shape:  # repair word by word: the shape describes one word
                    for w in text.split():
                        m = re.search(spec.pattern, repair_shape(w, spec.shape))
                        if m:
                            break
                else:
                    m = re.search(spec.pattern, cand)
                if not m and spec.charset == "digits":  # OCR split a number: "6 6-8637 94 0"
                    m = re.search(spec.pattern, re.sub(r"\s+", "", cand))
                if not m:
                    return None, conf, PATTERN_MISS
                text = m.group(0)
        elif spec.shape:
            text = repair_shape(text, spec.shape)
        if spec.parse == "digits":
            text = re.sub(r"\D", "", text)
            if not text:
                return None, conf, PARSE_FAIL
        elif spec.parse in {"date", "year_end"}:
            if spec.parse == "year_end":
                m = re.search(r"\d{4}", text)
                return (f"{m.group(0)}-12-31", conf, OK) if m else (None, conf, PARSE_FAIL)
            d = parse_date(text, spec.formats, self.as_of)
            if d is None:
                return None, conf, PARSE_FAIL
            text = d.isoformat()
        return norm(text) if "\n" not in text else text, conf, OK


def _conf(tokens: list[Token]) -> float:
    return round(sum(t.conf for t in tokens) / len(tokens), 4) if tokens else 0.0


@dataclass
class Extracted:
    template: Template
    persons: dict[str, dict[str, str]]
    confidence: dict[str, dict[str, float]]
    identifiers: list[tuple[str, str, float]]
    doc_date: str | None
    diagnostics: list[tuple[str, str, str]]


def extract(template: Template, tokens: list[Token], ocr: bool, as_of: date) -> Extracted:
    page = Page(tokens, ocr)
    ex = Extractor(template, page, as_of)
    diags: list[tuple[str, str, str]] = []
    doc_vals: dict[str, str] = {}
    doc_conf: dict[str, float] = {}
    for name, spec in template.document.items():
        v, c, st = ex.value(spec)
        diags.append(("DOCUMENT", name, st))
        if v is not None:
            doc_vals[name], doc_conf[name] = v, c
    persons: dict[str, dict[str, str]] = {}
    confs: dict[str, dict[str, float]] = {}
    absent: dict[str, dict[str, str]] = {}
    for role, pspec in template.persons.items():
        vals: dict[str, str] = {}
        cf: dict[str, float] = {}
        if pspec.block_name_address:
            block, st = ex.block(pspec.block_name_address)
            diags.append((role, "raw_name", st))
            if block:
                vals["raw_name"], cf["raw_name"] = block[0].text, block[0].conf
                if len(block) > 1:
                    vals["raw_address"] = "\n".join(v.text for v in block[1:])
                    cf["raw_address"] = _conf_values(block[1:])
        for name, spec in pspec.fields.items():
            v, c, st = ex.value(spec)
            diags.append((role, name, st))
            if v is not None:
                vals[name], cf[name] = v, c
                if spec.parse == "date" and ex.last_raw:
                    vals[f"_raw_{name}"] = norm(ex.last_raw)
        if pspec.compose_name:
            parts = {k: vals.pop(k, "") for k in re.findall(r"{(\w+)}", pspec.compose_name)}
            composed = norm(pspec.compose_name.format(**parts)).strip(" ,")
            if any(parts.values()):
                vals["raw_name"] = composed
                cf["raw_name"] = min(cf.pop(k, 1.0) for k in parts)
        name = norm(vals.get("raw_name", ""))
        if not name or name.upper() in {s.upper() for s in pspec.skip_if_name}:
            if pspec.merge_into_if_absent:
                absent[pspec.merge_into_if_absent] = {
                    k: v for k, v in vals.items() if k != "raw_name"
                }
            continue
        vals["name_order_detected"] = pspec.name_order
        persons[role], confs[role] = vals, cf
    for role, extra in absent.items():
        if role in persons:
            for k, v in extra.items():
                persons[role].setdefault(k, v)
    for role in persons:
        for k, v in doc_vals.items():
            persons[role].setdefault(k, v)
            confs[role].setdefault(k, doc_conf[k])
    idents = []
    for spec in template.identifiers:
        v, c, st = ex.value(spec)
        diags.append(("IDENTIFIER", spec.kind, st))
        if v is not None:
            idents.append((spec.kind, v, c))
    doc_date = None
    dd = template.doc_date
    if dd.field:
        doc_date = next((p.get(dd.field) for p in persons.values() if p.get(dd.field)), None)
    elif dd.rule:
        doc_date, _, st = ex.value(dd.rule)
        diags.append(("DOCUMENT", "doc_date", st))
    return Extracted(template, persons, confs, idents, doc_date, diags)


def _conf_values(values: list[Value]) -> float:
    return round(sum(v.conf for v in values) / len(values), 4) if values else 0.0
