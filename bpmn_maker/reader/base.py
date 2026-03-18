from typing import Protocol
from dataclasses import dataclass


@dataclass
class RawDocument:
    """Language-agnostic output of any document reader."""

    paragraphs: list[str]  # ordered list of paragraph strings
    metadata: dict[str, str]  # title, author, etc. — best-effort


class IDocumentReader(Protocol):
    def read(self, path: str) -> RawDocument: ...
