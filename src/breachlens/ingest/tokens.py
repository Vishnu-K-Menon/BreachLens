"""Word tokens with boxes, shared by the text-layer and OCR paths, and line grouping.

Coordinates are PDF points with the origin at the top-left of the page. `conf` is 1.0
for text-layer words and Tesseract confidence / 100 for OCR words.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Token:
    text: str
    x0: float
    top: float
    x1: float
    bottom: float
    conf: float = 1.0
    page: int = 1

    @property
    def height(self) -> float:
        return max(self.bottom - self.top, 0.1)

    @property
    def mid_y(self) -> float:
        return (self.top + self.bottom) / 2


@dataclass
class Line:
    tokens: list[Token] = field(default_factory=list)

    @property
    def top(self) -> float:
        return min(t.top for t in self.tokens)

    @property
    def bottom(self) -> float:
        return max(t.bottom for t in self.tokens)

    @property
    def text(self) -> str:
        return " ".join(t.text for t in self.tokens)

    def spans(self) -> list[tuple[int, int]]:
        """Character span of each token inside `text`."""
        out, pos = [], 0
        for t in self.tokens:
            out.append((pos, pos + len(t.text)))
            pos += len(t.text) + 1
        return out

    def tokens_in(self, start: int, end: int) -> list[Token]:
        return [
            t for t, (a, b) in zip(self.tokens, self.spans(), strict=True) if a < end and b > start
        ]


def _overlap(a_top: float, a_bot: float, b_top: float, b_bot: float) -> float:
    return max(0.0, min(a_bot, b_bot) - max(a_top, b_top))


def group_lines(tokens: list[Token], min_overlap: float = 0.5) -> list[Line]:
    """Group tokens into lines by vertical overlap.

    A token joins a line when it overlaps the line's vertical band by at least
    `min_overlap` of its own height (so a 7.5 pt label and a 10 pt value that share a
    baseline end up on one line). Lines are sorted top to bottom, tokens left to right.
    """
    lines: list[Line] = []
    for t in sorted(tokens, key=lambda t: (t.mid_y, t.x0)):
        best, best_ov = None, 0.0
        for line in lines[-6:]:  # only recent lines can overlap
            ov = _overlap(t.top, t.bottom, line.top, line.bottom)
            if ov >= min_overlap * t.height and ov > best_ov:
                best, best_ov = line, ov
        if best is None:
            lines.append(Line([t]))
        else:
            best.tokens.append(t)
    for line in lines:
        line.tokens.sort(key=lambda t: t.x0)
    return sorted(lines, key=lambda line: (line.top, line.tokens[0].x0))
