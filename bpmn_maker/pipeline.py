import sys

from .reader.base import IDocumentReader
from .parser.base import ISOPParser
from .generator.base import IBPMNBuilder, ILayoutEngine


class SOPToBPMNPipeline:
    """
    Wires the four layers together.
    Every dependency is injected — swap any layer without touching this class.
    """

    def __init__(
        self,
        reader: IDocumentReader,
        parser: ISOPParser,
        layout: ILayoutEngine,
        builder: IBPMNBuilder,
    ):
        self.reader = reader
        self.parser = parser
        self.layout = layout
        self.builder = builder

    def run(self, input_path: str, output_path: str) -> None:
        raw_doc = self.reader.read(input_path)
        model = self.parser.parse(raw_doc)
        layout = self.layout.compute(model)
        xml = self.builder.build(model, layout)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(xml)


# ── Default wiring (production defaults) ─────────────────────────────────────


def build_default_pipeline() -> SOPToBPMNPipeline:
    from .reader.docx_reader import DocxReader
    from .parser.nlp_parser import NLPParser
    from .generator.layout_engine import LinearLayoutEngine
    from .generator.bpmn_builder import BPMNBuilder

    return SOPToBPMNPipeline(
        reader=DocxReader(),
        parser=NLPParser(),
        layout=LinearLayoutEngine(),
        builder=BPMNBuilder(),
    )


def cli() -> None:
    if len(sys.argv) != 3:
        print("Usage: bpmn-maker <input.docx> <output.bpmn>")
        sys.exit(1)
    build_default_pipeline().run(sys.argv[1], sys.argv[2])
