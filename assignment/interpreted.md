# Breaking Down the Requirements

This is a **take-home system design + coding exercise** disguised as a "small prototype." The 30-minute debrief is the real evaluation — the code is just a conversation starter. Let me unpack what they're actually testing.

---

## What They Say vs. What They Mean

**"We don't care about a pixel-perfect diagram"**
→ They care about *how you decompose a fuzzy NLP problem into clean software abstractions.* Don't over-invest in layout math or BPMN spec completeness.

**"Structured for extension"**
→ This is the core ask. They want to see that you understand *separation of concerns*: parsing ≠ modeling ≠ generating. Each layer should be swappable independently. This is a classic pipeline/strategy pattern evaluation.

**"Python preferred"**
→ Use Python. Don't be clever with another language unless you have a strong reason you can articulate.

**"30-minute conversation to walk through your thinking"**
→ They'll probe: *Why did you make this design choice? What would break at scale? What would you do differently?* Your README and code structure need to *anticipate those questions.*

---

## The Three Distinct Problems Embedded in This Task

### 1. Parsing — SOP Document → Structured Intermediate Representation
Extract meaning from a `.docx`. The hard part is **detecting control flow** — recognizing "If yes" / "If no" as a gateway, not just another task. This is a shallow NLP problem.

Key assumption they're handing you: *"reasonably structured (sections, numbered steps, basic if/then)"* — meaning regex + heuristics is acceptable; you don't need an LLM here (though that's worth noting as a future improvement).

### 2. Modeling — Intermediate Representation → Process Graph
This is the conceptual heart. You need an **internal model** (not BPMN-specific) that represents:
- Sequential tasks
- Exclusive gateways with named branches
- Start/end events

Think of it as a simple directed graph of typed nodes. If you skip this layer and go straight from parsed text to XML, the code becomes unmaintainable — and they'll call it out.

### 3. Generation — Process Graph → BPMN 2.0 XML
Serialize the graph into valid BPMN 2.0 XML. The tricky parts are:
- Proper XML namespaces (`xmlns:bpmn`, `xmlns:xsi`)
- IDs for every element + every sequence flow
- Basic layout coordinates (x/y) — even if approximate — so bpmn.io can render it without exploding

---

## The Architecture They're Implicitly Asking For

```
.docx file
    ↓
[DocxReader]          — extract raw text / paragraphs
    ↓
[SOPParser]           — detect steps, conditions, branches → ProcessModel
    ↓
[ProcessModel]        — language-agnostic graph: nodes (Task, Gateway, Event) + edges
    ↓
[BPMNGenerator]       — serialize ProcessModel → BPMN 2.0 XML
    ↓
output.bpmn
```

Each box should be its own class/module. The interfaces between them are what they'll interrogate.

---

## What the README Needs to Cover

They gave you an explicit checklist — don't skip any of it:

| Section | What to actually write |
|---|---|
| **Approach** | Describe the pipeline + why you chose a 3-layer design. Name the tradeoffs. |
| **Key assumptions** | SOP uses numbered steps; if/then appears as "If [condition]," on its own line or inline; one condition per gateway; no loops/parallel flows in scope. |
| **What you'd improve** | LLM-based parsing for messy docs; proper Dagre/graphviz layout; parallel gateways; BPMN validation via `bpmnlint`. |
| **Architecture diagram** | A Mermaid diagram in the README is clean and renders natively on GitHub. |

---

## The Gaps / Judgment Calls You Need to Make (and document)

These are the things they'll ask about in the debrief:

**1. How do you handle the gateway "merge"?**
When two branches (Yes/No) rejoin, you need a merging gateway before the next task. Many simple implementations miss this. Even if you handle it naively, *acknowledge it.*

**2. What's your intermediate model?**
Dataclasses or Pydantic models are clean. A dict is lazy. A full NetworkX graph is over-engineered. Dataclasses + a simple list of edges is the sweet spot.

**3. Layout coordinates**
bpmn.io needs `x`/`y` on `<bpmndi:BPMNShape>` elements or it'll pile everything at 0,0. A simple left-to-right linear layout (increment x by 150 per node) is fine — just do *something* intentional.

**4. LLM vs. heuristics for parsing**
For the prototype, heuristics are correct. But in your README, flag that a real system would likely use an LLM to extract steps + conditions from unstructured prose. This shows you understand the problem space beyond the exercise.

---

## Scope I'd Recommend

**In scope (do these):**
- `python-docx` to read `.docx`
- Regex/heuristic parser for numbered steps + if/then detection
- Pydantic process model (Task, ExclusiveGateway, StartEvent, EndEvent, SequenceFlow)
- BPMN XML generator using Python's `xml.etree.ElementTree`
- Linear layout algorithm (simple x offset per node)
- One worked example checked in
- Clean README with Mermaid architecture diagram

**Out of scope (explicitly note these):**
- Parallel gateways
- Subprocess/subprocess pools
- Loop detection
- Multi-document SOPs
- GUI or web interface

---

## Summary Verdict

This exercise is testing whether you can **turn ambiguity into structure**. The `.docx` → BPMN conversion is the pretext. The real question is: *Can you design a clean, layered system with clear interfaces, document your assumptions honestly, and speak to what you'd improve?*