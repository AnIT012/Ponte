"""フェーズ4：proposed 行を検出して承認待ちにする仕組み。

仕様: `# proposed by ai` の付いた行は、人が承認するまでビルドできない。
承認の書き方は仕様に無い（QUESTIONS.md Q13）。今は「マーカーを消す」＝承認。
`python -m lang proposals <spec>` で承認待ちを一覧し、承認待ちがあれば終了コード1。
"""
from __future__ import annotations

from dataclasses import dataclass

from .parser import Spec


@dataclass
class Proposal:
    line: int
    text: str
    by: str

    def __str__(self) -> str:
        return f"L{self.line}: {self.text}   （{self.by}）"


def list_proposals(spec: Spec) -> list[Proposal]:
    out = []
    for n in spec.walk():
        if n.proposed:
            out.append(Proposal(n.line, n.raw, n.comment))
    return out
