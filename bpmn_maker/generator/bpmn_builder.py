import xml.etree.ElementTree as ET
from ..models.process_model import ProcessModel, NodeType
from .base import IBPMNBuilder, LayoutResult

_NS = "http://www.omg.org/spec/BPMN/20100524/MODEL"
_BPMNDI = "http://www.omg.org/spec/BPMN/20100524/DI"
_DC = "http://www.omg.org/spec/DD/20100524/DC"
_DI = "http://www.omg.org/spec/DD/20100524/DI"
_XSI = "http://www.w3.org/2001/XMLSchema-instance"

_TAG_MAP = {
    NodeType.START_EVENT: "startEvent",
    NodeType.END_EVENT: "endEvent",
    NodeType.TASK: "task",
    NodeType.EXCLUSIVE_GATEWAY: "exclusiveGateway",
}

_W, _H = 140, 70  # default node width/height
_GW_W = 50  # gateway diamond width (BPMN convention)
_EVENT_SIZE = 36
_EVENT_Y_OFFSET = (_H // 2) - (_EVENT_SIZE // 2)


class BPMNBuilder:
    """
    Converts a ProcessModel + LayoutResult into a BPMN 2.0 XML string.
    Uses xml.etree.ElementTree — no external XML libraries required.
    """

    def build(self, model: ProcessModel, layout: LayoutResult) -> str:
        ET.register_namespace("", _NS)
        ET.register_namespace("bpmndi", _BPMNDI)
        ET.register_namespace("dc", _DC)
        ET.register_namespace("di", _DI)
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
        incoming_by_node: dict[str, list[str]] = {}
        outgoing_by_node: dict[str, list[str]] = {}
        for flow in model.flows:
            outgoing_by_node.setdefault(flow.source_ref, []).append(flow.id)
            incoming_by_node.setdefault(flow.target_ref, []).append(flow.id)
        node_by_id = {node.id: node for node in model.nodes}

        for node in model.nodes:
            tag = _TAG_MAP[node.type]
            el = ET.SubElement(
                proc, f"{{{_NS}}}{tag}", {"id": node.id, "name": node.name}
            )
            if node.type == NodeType.EXCLUSIVE_GATEWAY:
                gateway_direction = getattr(node, "gateway_direction", None)
                if gateway_direction is None:
                    incoming = len(incoming_by_node.get(node.id, []))
                    outgoing = len(outgoing_by_node.get(node.id, []))
                    gateway_direction = (
                        "Converging" if incoming > 1 and outgoing <= 1 else "Diverging"
                    )
                el.set("gatewayDirection", gateway_direction)
            if node.type != NodeType.START_EVENT:
                for flow_id in incoming_by_node.get(node.id, []):
                    incoming = ET.SubElement(el, f"{{{_NS}}}incoming")
                    incoming.text = flow_id
            if node.type != NodeType.END_EVENT:
                for flow_id in outgoing_by_node.get(node.id, []):
                    outgoing = ET.SubElement(el, f"{{{_NS}}}outgoing")
                    outgoing.text = flow_id

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
        diagram = ET.SubElement(
            root, f"{{{_BPMNDI}}}BPMNDiagram", {"id": "Diagram_1"}
        )
        plane = ET.SubElement(
            diagram,
            f"{{{_BPMNDI}}}BPMNPlane",
            {
                "id": "Plane_1",
                "bpmnElement": "Process_1",
            },
        )

        for node in model.nodes:
            x, y = layout.get(node.id, (60, 200))
            if node.type in {NodeType.START_EVENT, NodeType.END_EVENT}:
                w = _EVENT_SIZE
                h = _EVENT_SIZE
                y += _EVENT_Y_OFFSET
            elif node.type == NodeType.EXCLUSIVE_GATEWAY:
                w = _GW_W
                h = _GW_W
            else:
                w = _W
                h = _H
            shape = ET.SubElement(
                plane,
                f"{{{_BPMNDI}}}BPMNShape",
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
                f"{{{_BPMNDI}}}BPMNEdge",
                {
                    "id": f"Edge_{flow.id}",
                    "bpmnElement": flow.id,
                },
            )
            sx, sy = layout.get(flow.source_ref, (0, 0))
            tx, ty = layout.get(flow.target_ref, (0, 0))
            source_node = node_by_id[flow.source_ref]
            target_node = node_by_id[flow.target_ref]
            source_is_event = source_node.type in {
                NodeType.START_EVENT,
                NodeType.END_EVENT,
            }
            target_is_event = target_node.type in {
                NodeType.START_EVENT,
                NodeType.END_EVENT,
            }
            source_w = (
                _GW_W
                if source_node.type == NodeType.EXCLUSIVE_GATEWAY
                else (_EVENT_SIZE if source_is_event else _W)
            )
            source_h = (
                _GW_W
                if source_node.type == NodeType.EXCLUSIVE_GATEWAY
                else (_EVENT_SIZE if source_is_event else _H)
            )
            target_h = (
                _GW_W
                if target_node.type == NodeType.EXCLUSIVE_GATEWAY
                else (_EVENT_SIZE if target_is_event else _H)
            )
            source_y = sy + (_EVENT_Y_OFFSET if source_is_event else 0)
            target_y = ty + (_EVENT_Y_OFFSET if target_is_event else 0)
            ET.SubElement(
                edge,
                f"{{{_DI}}}waypoint",
                {"x": str(sx + source_w), "y": str(source_y + source_h // 2)},
            )
            ET.SubElement(
                edge,
                f"{{{_DI}}}waypoint",
                {"x": str(tx), "y": str(target_y + target_h // 2)},
            )

        ET.indent(root, space="  ")
        return ET.tostring(root, encoding="unicode", xml_declaration=True)
