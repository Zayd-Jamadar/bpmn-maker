from enum import StrEnum
from pydantic import BaseModel, Field, model_validator


class NodeType(StrEnum):
    START_EVENT = "startEvent"
    END_EVENT = "endEvent"
    TASK = "task"
    EXCLUSIVE_GATEWAY = "exclusiveGateway"


# ── Node types ────────────────────────────────────────────────────────────────


class BPMNNode(BaseModel):
    """Base for every element in the process graph."""

    id: str
    name: str
    type: NodeType  # discriminator — drives XML tag selection in generator


class StartEvent(BPMNNode):
    type: NodeType = NodeType.START_EVENT


class EndEvent(BPMNNode):
    type: NodeType = NodeType.END_EVENT


class Task(BPMNNode):
    type: NodeType = NodeType.TASK


class ExclusiveGateway(BPMNNode):
    type: NodeType = NodeType.EXCLUSIVE_GATEWAY
    yes_ref: str | None = None  # ID of the Task on the "yes" branch
    no_ref: str | None = None  # ID of the Task on the "no" branch
    gateway_direction: str | None = None


# ── Edges ─────────────────────────────────────────────────────────────────────


class SequenceFlow(BaseModel):
    id: str
    source_ref: str
    target_ref: str
    name: str = ""  # "Yes" / "No" / "" for unlabelled flows


# ── Graph container ───────────────────────────────────────────────────────────


class ProcessModel(BaseModel):
    nodes: list[BPMNNode]
    flows: list[SequenceFlow]

    @model_validator(mode="after")
    def validate_refs(self) -> "ProcessModel":
        """Every SequenceFlow must reference IDs that actually exist."""
        node_ids = {n.id for n in self.nodes}
        for flow in self.flows:
            if flow.source_ref not in node_ids:
                raise ValueError(
                    f"Flow {flow.id}: source_ref '{flow.source_ref}' not in nodes"
                )
            if flow.target_ref not in node_ids:
                raise ValueError(
                    f"Flow {flow.id}: target_ref '{flow.target_ref}' not in nodes"
                )
        return self

    @model_validator(mode="after")
    def validate_single_start_end(self) -> "ProcessModel":
        starts = [n for n in self.nodes if n.type == NodeType.START_EVENT]
        ends = [n for n in self.nodes if n.type == NodeType.END_EVENT]
        if len(starts) != 1:
            raise ValueError(
                f"ProcessModel must have exactly 1 StartEvent, got {len(starts)}"
            )
        if len(ends) < 1:
            raise ValueError("ProcessModel must have at least 1 EndEvent")
        return self
