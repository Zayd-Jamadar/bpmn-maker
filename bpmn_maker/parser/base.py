from typing import Protocol

from ..reader.base import RawDocument
from ..models.process_model import ProcessModel


class ISOPParser(Protocol):
    def parse(self, doc: RawDocument) -> ProcessModel: ...
