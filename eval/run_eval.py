from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import traceback
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from bpmn_maker.pipeline import build_default_pipeline


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT_DIR = PROJECT_ROOT / "data" / "raw"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "data" / "processed"
LINT_CONFIG = PROJECT_ROOT / ".bpmnlintrc"
SUMMARY_RE = re.compile(
    r"[✖✔]\s+(?P<problems>\d+)\s+problems?\s+\((?P<errors>\d+)\s+errors?,\s+(?P<warnings>\d+)\s+warnings?\)"
)


class _Ansi:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    CYAN = "\033[36m"


@dataclass
class LintResult:
    status: str
    errors: int = 0
    warnings: int = 0
    problems: int = 0
    summary: str = ""
    output: str = ""


@dataclass
class EvalResult:
    source: str
    output: str
    generation_status: str
    lint_status: str
    lint_errors: int = 0
    lint_warnings: int = 0
    notes: str = ""


def cli() -> None:
    args = _build_parser().parse_args()
    timestamp = args.timestamp or datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    input_dir = args.input_dir.resolve()
    output_dir = args.output_root.resolve() / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)

    pipeline = build_default_pipeline()
    lint_command = None if args.no_lint else _find_bpmnlint()
    results: list[EvalResult] = []

    docx_files = sorted(input_dir.glob("*.docx"))
    if not docx_files:
        raise SystemExit(f"No .docx files found in {input_dir}")

    for source_path in docx_files:
        output_path = output_dir / f"{source_path.stem}.bpmn"
        try:
            pipeline.run(str(source_path), str(output_path))
            lint_result = _run_lint(output_path, lint_command) if lint_command else None
            results.append(
                EvalResult(
                    source=str(source_path.relative_to(PROJECT_ROOT)),
                    output=str(output_path.relative_to(PROJECT_ROOT)),
                    generation_status="ok",
                    lint_status=lint_result.status if lint_result else "skipped",
                    lint_errors=lint_result.errors if lint_result else 0,
                    lint_warnings=lint_result.warnings if lint_result else 0,
                    notes=(lint_result.summary if lint_result else "bpmnlint not available"),
                )
            )
            if lint_result and lint_result.output:
                (output_dir / f"{source_path.stem}.lint.txt").write_text(
                    lint_result.output, encoding="utf-8"
                )
        except Exception as exc:  # pragma: no cover - error path is exercised manually
            results.append(
                EvalResult(
                    source=str(source_path.relative_to(PROJECT_ROOT)),
                    output=str(output_path.relative_to(PROJECT_ROOT)),
                    generation_status="failed",
                    lint_status="not_run",
                    notes=str(exc),
                )
            )
            (output_dir / f"{source_path.stem}.error.txt").write_text(
                traceback.format_exc(), encoding="utf-8"
            )

    summary_path = output_dir / "report.json"
    summary_path.write_text(
        json.dumps(
            {
                "generated_at": timestamp,
                "input_dir": str(input_dir),
                "output_dir": str(output_dir),
                "lint_command": lint_command,
                "results": [asdict(result) for result in results],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    _print_report(
        input_dir=input_dir,
        output_dir=output_dir,
        lint_command=lint_command,
        results=results,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Batch-generate BPMN files for all DOCX SOPs in a directory."
    )
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--timestamp", type=str, default=None)
    parser.add_argument("--no-lint", action="store_true")
    return parser


def _find_bpmnlint() -> list[str] | None:
    local_bin = PROJECT_ROOT / "node_modules" / ".bin" / "bpmnlint"
    if local_bin.exists():
        return [str(local_bin)]

    global_bin = shutil.which("bpmnlint")
    if global_bin:
        return [global_bin]

    return None


def _run_lint(path: Path, command: list[str]) -> LintResult:
    proc = subprocess.run(
        [*command, str(path)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    combined_output = "\n".join(part for part in [proc.stdout.strip(), proc.stderr.strip()] if part)
    match = SUMMARY_RE.search(combined_output)

    if match:
        problems = int(match.group("problems"))
        errors = int(match.group("errors"))
        warnings = int(match.group("warnings"))
        status = "clean" if problems == 0 else "issues"
        summary = f"{problems} problems ({errors} errors, {warnings} warnings)"
        return LintResult(
            status=status,
            problems=problems,
            errors=errors,
            warnings=warnings,
            summary=summary,
            output=combined_output,
        )

    if proc.returncode == 0:
        return LintResult(status="clean", summary="0 problems", output=combined_output)

    return LintResult(
        status="error",
        summary="bpmnlint execution failed",
        output=combined_output or "bpmnlint returned a non-zero exit code without output",
    )


def _print_report(
    *,
    input_dir: Path,
    output_dir: Path,
    lint_command: list[str] | None,
    results: list[EvalResult],
) -> None:
    use_color = os.getenv("NO_COLOR") is None
    generated = sum(result.generation_status == "ok" for result in results)
    failed = len(results) - generated
    linted = sum(result.lint_status != "skipped" for result in results)
    lint_issues = sum(result.lint_status == "issues" for result in results)

    print(_style("BPMN Maker Eval", _Ansi.BOLD, _Ansi.CYAN, enabled=use_color))
    print(_style("=" * 72, _Ansi.DIM, enabled=use_color))
    print(f"Input:      {input_dir}")
    print(f"Output:     {output_dir}")
    print(f"Lint:       {' '.join(lint_command) if lint_command else 'not available'}")
    print()

    rows = [
        ["Case", "Generate", "Lint", "Notes"],
        ["-" * 28, "-" * 10, "-" * 10, "-" * 28],
    ]
    for result in results:
        rows.append(
            [
                Path(result.source).name,
                result.generation_status,
                result.lint_status,
                result.notes or "-",
            ]
        )

    widths = [max(len(str(row[i])) for row in rows) for i in range(4)]
    for index, row in enumerate(rows):
        line = "  ".join(str(cell).ljust(widths[i]) for i, cell in enumerate(row))
        if index < 2:
            print(_style(line, _Ansi.BOLD if index == 0 else _Ansi.DIM, enabled=use_color))
        else:
            print(_colorize_row(line, row, enabled=use_color))

    print()
    print(
        _style(
            f"Generated: {generated}/{len(results)}  Failed: {failed}  Linted: {linted}  Files with lint issues: {lint_issues}",
            _Ansi.BOLD,
            enabled=use_color,
        )
    )
    print(f"Saved summary: {output_dir / 'report.json'}")


def _colorize_row(line: str, row: list[str], *, enabled: bool) -> str:
    if not enabled:
        return line
    if row[1] == "failed":
        return _style(line, _Ansi.RED, enabled=enabled)
    if row[2] == "issues":
        return _style(line, _Ansi.YELLOW, enabled=enabled)
    if row[2] == "clean":
        return _style(line, _Ansi.GREEN, enabled=enabled)
    return line


def _style(text: str, *codes: str, enabled: bool) -> str:
    if not enabled or not codes:
        return text
    return f"{''.join(codes)}{text}{_Ansi.RESET}"


if __name__ == "__main__":
    cli()
