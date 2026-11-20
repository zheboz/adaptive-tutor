"""The study units for the open outline.

They depend only on the outline, so they are planned in the background as soon as the outline is
ready, while the learner reads it and checks topics. Starting the quiz then waits only for what is
left. A failed stage is reported when the units are needed, and retried there.
"""

from concurrent.futures import Future, ThreadPoolExecutor
import contextvars
from collections.abc import Sequence

import streamlit as st

import tutor.planning as planning
from tutor.llm import LLMError
from tutor.materials.outline import Outline
from tutor.planning.units import UnitPlan


# `units_started` keeps a failed background run from starting again on every rerun.
UNIT_KEYS = ("unit_plan", "study_units", "units_future", "units_started")
# One pool for the whole server: the app script itself runs again on every interaction.
_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="unit-planning")

_Planned = tuple[UnitPlan | None, tuple[planning.StudyUnit, ...] | None, Exception | None]


def _plan(result: Outline) -> _Planned:
    """Both planning stages, keeping the first if the second fails. Runs in a worker thread."""
    try:
        plan = planning.plan_units(result)
    except (LLMError, planning.PlanningError) as error:
        return None, None, error
    try:
        return plan, planning.build_study_units(result, plan), None
    except (LLMError, planning.PlanningError) as error:
        return plan, None, error


def start_planning(result: Outline) -> None:
    """Plan the units in the background, once per outline. Call inside `llm.using(...)`."""
    if any(key in st.session_state for key in UNIT_KEYS):
        return
    # The worker uses this session's key and model.
    context = contextvars.copy_context()
    st.session_state.units_started = True
    st.session_state.units_future = _POOL.submit(context.run, _plan, result)


def _collect(future: Future) -> Exception | None:
    with st.spinner("Planning the learning units…"):
        plan, units, error = future.result()
    if plan is not None:
        st.session_state.unit_plan = plan
    if units is not None:
        st.session_state.study_units = units
    return error


def ensure_units(result: Outline) -> Sequence[planning.StudyUnit] | None:
    """The units, planned once per outline; None after showing why they could not be planned."""
    # Retire schedules from sessions opened before model-planned units were introduced.
    if "study_units" in st.session_state and "unit_plan" not in st.session_state:
        for key in ("study_units", "study_plan", "planned_days"):
            st.session_state.pop(key, None)
    future = st.session_state.pop("units_future", None)
    try:
        if future is not None:
            error = _collect(future)
            if error is not None:
                raise error
        if "unit_plan" not in st.session_state:
            with st.spinner("Planning the learning units…"):
                st.session_state.unit_plan = planning.plan_units(result)
        if "study_units" not in st.session_state:
            with st.spinner("Preparing study tasks for the planned units…"):
                st.session_state.study_units = planning.build_study_units(result, st.session_state.unit_plan)
    except (LLMError, planning.PlanningError) as error:
        st.error(str(error))
        return None
    return st.session_state.study_units
