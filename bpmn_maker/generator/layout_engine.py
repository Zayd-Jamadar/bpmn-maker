from ..models.process_model import ProcessModel, NodeType
from .base import LayoutResult


_X_STEP = 180  # horizontal spacing between nodes
_Y_MAIN = 200  # y for main path
_Y_UPPER = 80  # y for yes-branch tasks
_Y_LOWER = 320  # y for no-branch tasks


class LinearLayoutEngine:
    """
    Simple left-to-right layout.
    Gateway branches offset vertically; all other nodes sit on the main axis.
    Not pixel-perfect — sufficient for bpmn.io to render without overlaps.
    """

    def compute(self, model: ProcessModel) -> LayoutResult:
        layout = LayoutResult()
        x = 60
        gateway_x: int | None = None

        for node in model.nodes:
            if node.type == NodeType.EXCLUSIVE_GATEWAY:
                layout[node.id] = (x, _Y_MAIN)
                gateway_x = x
            elif hasattr(node, "type") and gateway_x is not None:
                # peek: is this a yes/no branch task?
                gw = next(
                    (
                        n
                        for n in model.nodes
                        if n.type == NodeType.EXCLUSIVE_GATEWAY
                        and (
                            getattr(n, "yes_ref", None) == node.id
                            or getattr(n, "no_ref", None) == node.id
                        )
                    ),
                    None,
                )
                if gw:
                    y = (
                        _Y_UPPER
                        if getattr(gw, "yes_ref", None) == node.id
                        else _Y_LOWER
                    )
                    layout[node.id] = (gateway_x + _X_STEP, y)
                else:
                    layout[node.id] = (x, _Y_MAIN)
                    gateway_x = None
            else:
                layout[node.id] = (x, _Y_MAIN)
            x += _X_STEP

        return layout
