from typing import Protocol
from ..models.process_model import ProcessModel


class LayoutResult(dict):
    """Maps node_id → (x, y) tuple."""


class ILayoutEngine(Protocol):
    def compute(self, model: ProcessModel) -> LayoutResult: ...


class IBPMNBuilder(Protocol):
    def build(self, model: ProcessModel, layout: LayoutResult) -> str: ...

    # Returns a valid BPMN 2.0 XML string.
