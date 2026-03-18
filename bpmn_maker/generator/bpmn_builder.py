import xml.etree.ElementTree as ET
from ..models.process_model import ProcessModel, NodeType
from .base import IBPMNBuilder, LayoutResult

_NS = "http://www.omg.org/spec/BPMN/20100524/MODEL"
_DI = "http://www.omg.org/spec/BPMN/20100524/DI"
_DC = "http://www.omg.org/spec/DD/20100524/DC"
_XSI = "http://www.w3.org/2001/XMLSchema-instance"

_TAG_MAP = {
    NodeType.START_EVENT: "startEvent",
    NodeType.END_EVENT: "endEvent",
    NodeType.TASK: "task",
    NodeType.EXCLUSIVE_GATEWAY: "exclusiveGateway",
}

_W, _H = 120, 60  # default node width/height
_GW_W = 50  # gateway diamond width (BPMN convention)


class BPMNBuilder:
    """
    Converts a ProcessModel + LayoutResult into a BPMN 2.0 XML string.
    Uses xml.etree.ElementTree — no external XML libraries required.
    """

    def build(self, model: ProcessModel, layout: LayoutResult) -> str:
        ET.register_namespace("", _NS)
        ET.register_namespace("bpmndi", _DI)
        ET.register_namespace("dc", _DC)
        ET.register_namespace("xsi", _XSI)

        root = ET.Element(
            f"{{{_NS}}}definitions",
            {
                "targetNamespace": "http://sop-bpmn/process",
            },
        )

        proc = ET.SubElement(
            root,
            f"{{{_NS}}}process",
            {
                "id": "Process_1",
                "isExecutable": "false",
            },
        )

        # ── BPMN semantic elements ────────────────────────────────────────
        for node in model.nodes:
            tag = _TAG_MAP[node.type]
            el = ET.SubElement(
                proc, f"{{{_NS}}}{tag}", {"id": node.id, "name": node.name}
            )
            # outgoing / incoming are populated from flows below
            if node.type == NodeType.EXCLUSIVE_GATEWAY:
                el.set("gatewayDirection", "Diverging")

        for flow in model.flows:
            ET.SubElement(
                proc,
                f"{{{_NS}}}sequenceFlow",
                {
                    "id": flow.id,
                    "name": flow.name,
                    "sourceRef": flow.source_ref,
                    "targetRef": flow.target_ref,
                },
            )

        # ── BPMN DI (diagram interchange) ────────────────────────────────
        diagram = ET.SubElement(root, f"{{{_DI}}}BPMNDiagram", {"id": "Diagram_1"})
        plane = ET.SubElement(
            diagram,
            f"{{{_DI}}}BPMNPlane",
            {
                "id": "Plane_1",
                "bpmnElement": "Process_1",
            },
        )

        for node in model.nodes:
            x, y = layout.get(node.id, (60, 200))
            w = _GW_W if node.type == NodeType.EXCLUSIVE_GATEWAY else _W
            h = _GW_W if node.type == NodeType.EXCLUSIVE_GATEWAY else _H
            shape = ET.SubElement(
                plane,
                f"{{{_DI}}}BPMNShape",
                {
                    "id": f"Shape_{node.id}",
                    "bpmnElement": node.id,
                },
            )
            ET.SubElement(
                shape,
                f"{{{_DC}}}Bounds",
                {
                    "x": str(x),
                    "y": str(y),
                    "width": str(w),
                    "height": str(h),
                },
            )

        for flow in model.flows:
            edge = ET.SubElement(
                plane,
                f"{{{_DI}}}BPMNEdge",
                {
                    "id": f"Edge_{flow.id}",
                    "bpmnElement": flow.id,
                },
            )
            sx, sy = layout.get(flow.source_ref, (0, 0))
            tx, ty = layout.get(flow.target_ref, (0, 0))
            ET.SubElement(
                edge, f"{{{_DI}}}waypoint", {"x": str(sx + _W), "y": str(sy + _H // 2)}
            )
            ET.SubElement(
                edge, f"{{{_DI}}}waypoint", {"x": str(tx), "y": str(ty + _H // 2)}
            )

        ET.indent(root, space="  ")
        return ET.tostring(root, encoding="unicode", xml_declaration=True)
