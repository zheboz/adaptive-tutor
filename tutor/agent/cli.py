"""Run one diagnosis in the terminal: python -m tutor.agent.cli lesson.pdf

This uses the same outline, units, question pipeline and agent loop as the web app.
"""

import argparse
from pathlib import Path
import sys

from tutor.llm import LLMError, Trace, tracing
from tutor.materials import outline
from tutor.materials.ingest import PdfInputError, read_pdf_pages
from tutor.planning import build_study_units, plan_units

from .bank import QuestionBank
from .intake import read_self_report
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
    args = parser.parse_args(argv)

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
    raw = input("\nUnits you don't understand (numbers separated by commas, or Enter for none): ")
    checked = [units[int(n) - 1].unit_id for n in raw.replace(",", " ").split()
               if n.isdigit() and 1 <= int(n) <= len(units)]
    note = input("Describe what you don't understand (optional): ")

    state = LearnerState(units)
    session = start_session(units, state, QuestionBank(units, pages))
    try:
        with tracing(session.trace):
            intake = read_self_report(units, checked, note)
        state.apply_report(intake.checked_ids, intake.note, intake.noted_ids, intake.missing_topic)
        if intake.missing_topic:
            print(f"\nYour material doesn't seem to cover: {intake.missing_topic}")

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
