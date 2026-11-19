"""Run one diagnosis in the terminal: python -m tutor.agent.cli lesson.pdf

This uses the same outline, units, question pipeline and agent loop as the web app. The web app
takes the key from each learner; this developer tool reads OPENAI_API_KEY from its own environment.
"""

import argparse
import os
from pathlib import Path
import sys

from tutor.llm import DEFAULT_MODEL, LLMError, Trace, tracing, using
from tutor.materials import outline
from tutor.materials.ingest import PdfInputError, read_pdf_pages
from tutor.planning import build_study_units, plan_units

from .bank import QuestionBank
from .loop import Ask, advance, start_session
from .state import LearnerState


def _choose(prompt: str, count: int) -> int:
    while True:
        raw = input(prompt).strip()
        if raw.isdigit() and 1 <= int(raw) <= count:
            return int(raw) - 1
        print(f"Enter a number from 1 to {count}.")


def _print_trace(label: str, trace: Trace) -> None:
    print(f"\n[{label}] model calls: {trace.model_calls} · tokens: {trace.total_tokens} · "
          f"model time: {trace.model_seconds:.1f} s")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Diagnose a learner's main difficulty in a PDF's material.")
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--trace", action="store_true", help="Print every model and tool step at the end.")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"OpenAI model ID (default {DEFAULT_MODEL}).")
    args = parser.parse_args(argv)
    if not os.environ.get("OPENAI_API_KEY"):
        print("Set OPENAI_API_KEY to run the command-line diagnosis.", file=sys.stderr)
        return 1
    with using(os.environ["OPENAI_API_KEY"], args.model):
        return _run(args)


def _run(args: argparse.Namespace) -> int:

    try:
        pages = read_pdf_pages(args.pdf.read_bytes())
    except (OSError, PdfInputError) as error:
        print(error, file=sys.stderr)
        return 1

    setup = Trace()
    try:
        with tracing(setup):
            print("Generating the outline and study units…")
            topics = outline.generate_outline(pages)
            units = build_study_units(topics, plan_units(topics))
    except (LLMError, outline.OutlineError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1
    _print_trace("setup", setup)

    print("\nStudy units:")
    for number, unit in enumerate(units, 1):
        print(f"  {number}. {unit.title} — {unit.objective}")
    raw = input("\nUnits you find weak (numbers separated by commas, or Enter for none): ")
    weak = [units[int(n) - 1].unit_id for n in raw.replace(",", " ").split()
            if n.isdigit() and 1 <= int(n) <= len(units)]

    state = LearnerState(units)
    state.apply_report(weak)
    session = start_session(units, state, QuestionBank(units, pages))
    try:
        step = advance(session)
        while isinstance(step, Ask):
            question = step.question.question
            print(f"\nQuestion {step.number} · {state.units[step.question.unit_id].unit.title}")
            print(f"(Why: {step.reason})")
            print(question.prompt)
            for number, option in enumerate(question.options, 1):
                print(f"  {number}. {option}")
            step = advance(session, _choose("Your answer: ", len(question.options)))
    except LLMError as error:
        print(error, file=sys.stderr)
        return 1

    diagnosis = step.diagnosis
    gap = state.units[diagnosis.primary_gap].unit.title if diagnosis.primary_gap else "none"
    print(f"\nDiagnosis: {gap} ({diagnosis.status}{', stopped at the call limit' if diagnosis.forced else ''})")
    print(f"Evidence: {', '.join(diagnosis.evidence) or 'none'} · next step: {diagnosis.next_step}")
    print(diagnosis.summary)
    print("\nUnit status:")
    for evidence in state.units.values():
        print(f"  {evidence.unit.title}: {evidence.status}")
    _print_trace("diagnosis", session.trace)
    if args.trace:
        for span in session.trace.spans:
            tokens = f" · {span.input_tokens}+{span.output_tokens} tok" if span.input_tokens else ""
            error = f" · ERROR {span.error}" if span.error else ""
            print(f"  {span.name:<24} {span.seconds:5.2f} s{tokens} {span.detail}{error}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
