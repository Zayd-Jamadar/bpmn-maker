import re
from dataclasses import dataclass

from .base import ISOPParser
from ..reader.base import RawDocument
from ..models.process_model import (
    ProcessModel,
    StartEvent,
    EndEvent,
    Task,
    ExclusiveGateway,
    SequenceFlow,
)

# ── Heuristic patterns ────────────────────────────────────────────────────────
_STEP_RE = re.compile(r"^(?P<number>\d+)\.\s+(?P<text>.+)")
_SECTION_RE = re.compile(r"^(?P<number>\d+)\.\s+(?P<title>.+)$")
_IF_YES_RE = re.compile(r"^if\s+yes(?:[,:]|$)\s*(.*)", re.I)
_IF_NO_RE = re.compile(r"^if\s+no(?:[,:]|$)\s*(.*)", re.I)
_IF_BRANCH_RE = re.compile(r"^if\s+(.+?)(?:,\s*|\s+then\s+)(.+)$", re.I)
_CHECK_RE = re.compile(
    r"^(check if|verify whether|confirm whether|determine whether)\b", re.I
)
_STEP_REF_RE = re.compile(r"\bstep\s+(\d+)\b", re.I)
_PROCEDURE_SECTION_TITLES = {"procedure steps", "procedure", "steps", "process steps"}
_NON_STEP_PREFIXES = ("note:", "owner:", "version:", "department:", "effective date:")
_TERMINAL_BRANCH_RE = re.compile(
    r"\b(pending until|terminate|stop)\b", re.I
)
_ACTION_VERB_RE = re.compile(
    r"^(receive|accept|collect|gather|capture|count|log|enter|input|record|document|print|"
    r"compare|match|reconcile|submit|forward|route|lock|unlock|return|review|check|verify|"
    r"confirm|determine|assess|validate|screen|run|search|lookup|cross-check|complete|send|"
    r"deliver|issue|generate|obtain|sign|scan|file|retain|archive|store|save|navigate|open|"
    r"update|attach|upload|download|notify|inform|escalate|prepare|inspect|approve|reject|"
    r"mark|release|close|activate|deactivate|create|initiate|process|post|retrieve)\b",
    re.I,
)
_ROLE_ACTION_RE = re.compile(
    r"^(?:the|a|an)\s+.+?\s+(?:must|shall|should|will)\s+" + _ACTION_VERB_RE.pattern[1:],
    re.I,
)


class NLPParser(ISOPParser):
    """
    Converts a RawDocument into a ProcessModel using section-aware heuristics.

    Assumptions:
    - Prefer extracting steps from a "Procedure Steps" section when present.
    - Otherwise, fall back to numbered steps ("1. Step text").
    - Gateway branches are expressed as "If <condition>, ..." lines.
    - A preceding check/verify-style step, or any step followed by branch lines,
      is treated as the gateway question.
    - No parallel flows or loops in scope — those are detected and flagged but not modelled.
    """

    def parse(self, doc: RawDocument) -> ProcessModel:
        nodes: list = []
        flows: list[SequenceFlow] = []
        id_seq = _IDSeq()
        steps = self._classify_steps(self._extract_steps(doc.paragraphs))

        start = StartEvent(id=id_seq.next("start"), name="Process started")
        nodes.append(start)

        end = EndEvent(id=id_seq.next("end"), name="Process complete")
        hold_end: EndEvent | None = None
        nodes_by_index: dict[int, StartEvent | EndEvent | Task | ExclusiveGateway] = {}

        for step in steps:
            if step.kind == "gateway":
                node = ExclusiveGateway(id=id_seq.next("gw"), name=step.name)
            else:
                node = Task(id=id_seq.next("task"), name=step.name)
            nodes.append(node)
            nodes_by_index[step.index] = node

        merge_targets_by_step: dict[int, str] = {}
        merge_flows: list[tuple[str, int]] = []
        for step in steps:
            if step.kind != "gateway":
                continue
            branch_steps = self._find_branch_steps(steps, step.index)
            if len(branch_steps) < 2:
                continue

            branches_by_target: dict[int, list[int]] = {}
            for branch_step in branch_steps:
                merge_plan = self._find_branch_merge_plan(branch_step, steps)
                if merge_plan is None:
                    continue
                exit_index, target_index = merge_plan
                branches_by_target.setdefault(target_index, []).append(exit_index)

            for target_index, exit_indices in branches_by_target.items():
                if len(exit_indices) < 2:
                    continue
                merge_gateway = ExclusiveGateway(
                    id=id_seq.next("gw"),
                    name="",
                    gateway_direction="Converging",
                )
                target_node = nodes_by_index[target_index]
                nodes.insert(nodes.index(target_node), merge_gateway)
                for exit_index in exit_indices:
                    merge_targets_by_step[exit_index] = merge_gateway.id
                merge_flows.append((merge_gateway.id, target_index))

        if steps:
            flows.append(
                SequenceFlow(
                    id=id_seq.next("flow"),
                    source_ref=start.id,
                    target_ref=nodes_by_index[0].id,
                )
            )
        else:
            nodes.append(end)
            flows.append(
                SequenceFlow(
                    id=id_seq.next("flow"),
                    source_ref=start.id,
                    target_ref=end.id,
                )
            )
            return ProcessModel(nodes=nodes, flows=flows)

        for step in steps:
            node = nodes_by_index[step.index]

            if step.kind == "gateway":
                branch_steps = self._find_branch_steps(steps, step.index)
                first_branch, second_branch = self._layout_branch_slots(branch_steps)
                if first_branch:
                    node.yes_ref = nodes_by_index[first_branch.index].id
                if second_branch:
                    node.no_ref = nodes_by_index[second_branch.index].id

                for branch_step in branch_steps:
                    branch_node = nodes_by_index[branch_step.index]
                    flows.append(
                        SequenceFlow(
                            id=id_seq.next("flow"),
                            source_ref=node.id,
                            target_ref=branch_node.id,
                            name=branch_step.branch_label,
                        )
                    )
                continue

            if merge_target := merge_targets_by_step.get(step.index):
                flows.append(
                    SequenceFlow(
                        id=id_seq.next("flow"),
                        source_ref=node.id,
                        target_ref=merge_target,
                    )
                )
                continue

            if step.kind == "branch":
                target_index = self._resolve_branch_target(step, steps)
                if target_index is not None:
                    flows.append(
                        SequenceFlow(
                            id=id_seq.next("flow"),
                            source_ref=node.id,
                            target_ref=nodes_by_index[target_index].id,
                        )
                    )
                    continue
                if step.terminal_hold:
                    if hold_end is None:
                        hold_end = EndEvent(
                            id=id_seq.next("end"), name="Application on hold"
                        )
                        nodes.append(hold_end)
                    flows.append(
                        SequenceFlow(
                            id=id_seq.next("flow"),
                            source_ref=node.id,
                            target_ref=hold_end.id,
                        )
                    )
                continue

            next_index = self._find_next_mainline_step(steps, step.index)
            if next_index is not None:
                flows.append(
                    SequenceFlow(
                        id=id_seq.next("flow"),
                        source_ref=node.id,
                        target_ref=nodes_by_index[next_index].id,
                    )
                )
            else:
                flows.append(
                    SequenceFlow(
                        id=id_seq.next("flow"),
                        source_ref=node.id,
                        target_ref=end.id,
                    )
                )

        for merge_gateway_id, target_index in merge_flows:
            flows.append(
                SequenceFlow(
                    id=id_seq.next("flow"),
                    source_ref=merge_gateway_id,
                    target_ref=nodes_by_index[target_index].id,
                )
            )

        nodes.append(end)

        return ProcessModel(nodes=nodes, flows=flows)

    def _extract_steps(self, paragraphs: list[str]) -> list["_SourceStep"]:
        procedure_steps = self._extract_procedure_section_steps(paragraphs)
        if procedure_steps:
            return procedure_steps
        return self._extract_numbered_steps(paragraphs)

    def _classify_steps(self, steps: list["_SourceStep"]) -> list["_Step"]:
        classified: list[_Step] = []
        texts = [step.text for step in steps]
        for index, source_step in enumerate(steps):
            text = source_step.text
            if branch := self._parse_branch_step(text):
                classified.append(
                    _Step(
                        index=index,
                        kind="branch",
                        name=branch.action,
                        source_number=source_step.number,
                        branch_label=branch.label,
                        branch_polarity=branch.polarity,
                        jump_target=self._extract_step_reference(text),
                        terminal_hold=self._is_terminal_branch(text),
                    )
                )
                continue
            if self._is_gateway_question(text, texts, index):
                classified.append(
                    _Step(
                        index=index,
                        kind="gateway",
                        name=text,
                        source_number=source_step.number,
                    )
                )
                continue
            classified.append(
                _Step(
                    index=index,
                    kind="task",
                    name=text,
                    source_number=source_step.number,
                )
            )
        inferred_ref_number = 1
        for step in classified:
            if step.source_number is not None:
                step.procedure_ref_number = step.source_number
            elif step.kind != "gateway":
                step.procedure_ref_number = inferred_ref_number
                inferred_ref_number += 1

        return classified

    def _extract_procedure_section_steps(self, paragraphs: list[str]) -> list["_SourceStep"]:
        in_procedure_section = False
        steps: list[_SourceStep] = []

        for raw_line in paragraphs:
            line = raw_line.strip()
            if not line:
                continue

            section_match = _SECTION_RE.match(line)
            if section_match:
                section_title = self._normalize_section_title(
                    section_match.group("title")
                )
                if section_title in _PROCEDURE_SECTION_TITLES:
                    in_procedure_section = True
                    continue
                if in_procedure_section:
                    break
                continue

            if not in_procedure_section:
                continue
            if self._is_non_step_line(line):
                continue
            step_match = _STEP_RE.match(line)
            text = step_match.group("text").strip() if step_match else line
            number = int(step_match.group("number")) if step_match else None
            if self._looks_like_action_step(text):
                steps.append(_SourceStep(text=text, number=number))

        return steps

    def _extract_numbered_steps(self, paragraphs: list[str]) -> list["_SourceStep"]:
        steps: list[_SourceStep] = []
        for raw_line in paragraphs:
            line = raw_line.strip()
            if not line:
                continue
            step_match = _STEP_RE.match(line)
            if not step_match:
                continue
            text = step_match.group("text").strip()
            if self._normalize_section_title(text) in _PROCEDURE_SECTION_TITLES:
                continue
            steps.append(
                _SourceStep(text=text, number=int(step_match.group("number")))
            )
        return steps

    def _normalize_section_title(self, title: str) -> str:
        return re.sub(r"\s+", " ", title.strip().lower()).rstrip(":")

    def _is_non_step_line(self, line: str) -> bool:
        normalized = line.strip().lower()
        return normalized.startswith(_NON_STEP_PREFIXES)

    def _looks_like_action_step(self, line: str) -> bool:
        return (
            bool(_ACTION_VERB_RE.match(line))
            or bool(_ROLE_ACTION_RE.match(line))
            or bool(_IF_BRANCH_RE.match(line))
            or bool(_IF_YES_RE.match(line))
            or bool(_IF_NO_RE.match(line))
        )

    def _is_gateway_question(self, text: str, steps: list[str], index: int) -> bool:
        if _CHECK_RE.search(text):
            return True
        next_step = steps[index + 1] if index + 1 < len(steps) else ""
        return self._parse_branch_step(next_step) is not None

    def _extract_step_reference(self, text: str) -> int | None:
        if match := _STEP_REF_RE.search(text):
            return int(match.group(1)) - 1
        return None

    def _is_terminal_branch(self, text: str) -> bool:
        return bool(_TERMINAL_BRANCH_RE.search(text))

    def _find_branch_steps(self, steps: list["_Step"], gateway_index: int) -> list["_Step"]:
        branch_steps: list[_Step] = []
        for step in steps[gateway_index + 1 :]:
            if step.kind == "branch":
                branch_steps.append(step)
                continue
            if branch_steps:
                break
        return branch_steps

    def _find_next_mainline_step(
        self, steps: list["_Step"], step_index: int
    ) -> int | None:
        for step in steps[step_index + 1 :]:
            if step.kind != "branch":
                return step.index
        return None

    def _resolve_branch_target(self, step: "_Step", steps: list["_Step"]) -> int | None:
        if step.jump_target is not None:
            target_index = self._resolve_step_reference(step.jump_target, steps)
            if target_index is not None:
                jump_step = steps[target_index]
                if jump_step.kind == "branch":
                    return self._find_next_mainline_step(steps, jump_step.index)
                return target_index
        if step.terminal_hold:
            return None
        return self._find_next_mainline_step(steps, step.index)

    def _find_branch_merge_plan(
        self, branch_step: "_Step", steps: list["_Step"]
    ) -> tuple[int, int] | None:
        immediate_target = self._resolve_branch_target(branch_step, steps)
        if immediate_target is None:
            return None
        path = [branch_step.index]
        current_index = immediate_target
        seen = {branch_step.index}

        while True:
            if current_index in seen:
                return path[-1], current_index
            seen.add(current_index)
            path.append(current_index)

            current_step = steps[current_index]
            if current_step.kind in {"gateway", "branch"}:
                return path[-2], current_index

            next_index = self._find_next_mainline_step(steps, current_index)
            if next_index is None:
                return path[-2], current_index

            next_step = steps[next_index]
            if next_step.kind in {"gateway", "branch"}:
                return path[-1], next_index

            current_index = next_index

    def _resolve_step_reference(self, step_number: int, steps: list["_Step"]) -> int | None:
        numbered_match = next(
            (step.index for step in steps if step.source_number == step_number + 1),
            None,
        )
        if numbered_match is not None:
            return numbered_match
        procedure_match = next(
            (step.index for step in steps if step.procedure_ref_number == step_number + 1),
            None,
        )
        if procedure_match is not None:
            return procedure_match
        if 0 <= step_number < len(steps):
            return step_number
        return None

    def _parse_branch_step(self, text: str) -> "_ParsedBranch | None":
        if m := _IF_YES_RE.match(text):
            return _ParsedBranch(
                action=m.group(1).strip() or text,
                label="Yes",
                polarity="yes",
            )
        if m := _IF_NO_RE.match(text):
            return _ParsedBranch(
                action=m.group(1).strip() or text,
                label="No",
                polarity="no",
            )
        if m := _IF_BRANCH_RE.match(text):
            condition = m.group(1).strip()
            action = m.group(2).strip() or text
            return _ParsedBranch(
                action=action,
                label=self._condition_to_label(condition),
                polarity=self._condition_polarity(condition),
            )
        return None

    def _condition_to_label(self, condition: str) -> str:
        normalized = re.sub(r"\s+", " ", condition).strip()
        if self._condition_polarity(normalized) == "no":
            return "No"
        if normalized.lower() in {"yes", "true"}:
            return "Yes"
        return normalized[:1].upper() + normalized[1:]

    def _condition_polarity(self, condition: str) -> str | None:
        normalized = condition.strip().lower()
        if normalized == "yes":
            return "yes"
        if normalized == "no":
            return "no"
        if normalized.startswith("no "):
            return "no"
        return None

    def _layout_branch_slots(
        self, branch_steps: list["_Step"]
    ) -> tuple["_Step | None", "_Step | None"]:
        yes_branch = next(
            (step for step in branch_steps if step.branch_polarity == "yes"),
            None,
        )
        no_branch = next(
            (step for step in branch_steps if step.branch_polarity == "no"),
            None,
        )
        remaining = [
            step
            for step in branch_steps
            if step is not yes_branch and step is not no_branch
        ]
        upper = yes_branch or (remaining.pop(0) if remaining else None) or no_branch
        lower = no_branch or (remaining.pop(0) if remaining else None)
        if lower is None and (upper is yes_branch or upper is no_branch) and remaining:
            lower = remaining.pop(0)
        return upper, lower


@dataclass
class _ParsedBranch:
    action: str
    label: str
    polarity: str | None


@dataclass
class _SourceStep:
    text: str
    number: int | None = None


class _IDSeq:
    def __init__(self):
        self._counts: dict[str, int] = {}

    def next(self, prefix: str) -> str:
        self._counts[prefix] = self._counts.get(prefix, 0) + 1
        return f"{prefix}_{self._counts[prefix]}"


@dataclass
class _Step:
    index: int
    kind: str
    name: str
    source_number: int | None = None
    procedure_ref_number: int | None = None
    branch_label: str = ""
    branch_polarity: str | None = None
    jump_target: int | None = None
    terminal_hold: bool = False
