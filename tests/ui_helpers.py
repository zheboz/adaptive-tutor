"""Driving the app in tests: the setup steps, then the study workspace."""

from concurrent.futures import Future, wait
from html import unescape
import os
from pathlib import Path
import re
import time
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from tests.test_pdf_preview import APP, button, make_pdf
from tutor.llm import LLMError


KEY = "sk-test"


class UITestCase(unittest.TestCase):
    """The app has a key from its environment, never the developer's real one; its models load without a
    request, and no request ever reaches OpenAI."""

    def setUp(self):
        self.env = self.enterContext(patch.dict(os.environ, {"OPENAI_API_KEY": KEY}, clear=True))
        self.enterContext(patch("tutor.ui.settings.ENV_FILE", Path("/nonexistent/.env")))
        self.list_models = self.enterContext(patch("tutor.ui.settings.list_models", return_value=[]))
        self.enterContext(patch("tutor.llm._request", side_effect=LLMError("No network in tests.")))
        self._apps: list[AppTest] = []

    def new_app(self, **kwargs) -> AppTest:
        app = AppTest.from_file(APP, default_timeout=10, **kwargs).run()
        self._apps.append(app)
        return app

    def tearDown(self):
        """Let the work these apps started in the background (outline, units, cards) finish while this
        test's mocks are still in place, so none of it runs into the next test's mocks."""
        for app in self._apps:
            wait_for_jobs(app)
        super().tearDown()


def wait_for_jobs(app, seconds: float = 10):
    """Wait for the background jobs the app's session holds: outline, units, cards, check head starts."""
    wait(_jobs(app.session_state.values()), timeout=seconds)


def _jobs(values) -> list[Future]:
    """The background jobs among session values, also inside dicts, lists and tuples."""
    found = []
    for value in values:
        if isinstance(value, Future):
            found.append(value)
        elif isinstance(value, dict):
            found += _jobs(value.values())
        elif isinstance(value, (list, tuple)):
            found += _jobs(value)
    return found


def add_material(app, *pages) -> bytes:
    """In the first step: the PDF."""
    document = make_pdf(*pages)
    app.file_uploader[0].set_value(("lesson.pdf", document, "application/pdf")).run()
    return document


def begin(app, *pages) -> bytes:
    """Add the material and open the Topics step, where the outline is made."""
    document = add_material(app, *pages)
    app.button(key="material_next").click().run()
    wait_for_outline(app)
    return document


def wait_for_outline(app, seconds: float = 5):
    """While the outline is made in the background, Topics shows its progress and refreshes itself;
    run the page again until the job is done, as that refresh would."""
    end = time.monotonic() + seconds
    while "outline_job" in app.session_state and time.monotonic() < end:
        time.sleep(0.05)
        app.run()


def go_to_step(app, step: int):
    app.button(key=f"step_{step}").click().run()


def start_quick_check(app):
    app.button(key="start_initial_quiz").click().run()


def answer_quiz(app, item_id: str, option: str):
    """Answer the current question and move past its feedback."""
    app.radio(key=f"quiz_choice_{item_id}").set_value(option).run()
    app.button(key="quiz_submit").click().run()
    app.button(key="quiz_next").click().run()


def studying(app) -> bool:
    return app.session_state["planned_days"] is not None if "planned_days" in app.session_state else False


def create_plan(app, days: int):
    """Finish setup with this many days, skipping the quick check unless it is done; or, while
    studying, change the plan's days on the Plan page."""
    if studying(app):
        show_page(app, "Plan")
        app.number_input(key="study_target_days").set_value(days)
        button(app, "Update plan").click().run()
        return
    if "quiz" in app.session_state and app.session_state["quiz"]["results"] is not None:
        go_to_step(app, 4)
    else:
        if app.session_state["setup_step"] != 2:
            go_to_step(app, 2)
        app.button(key="skip_initial_quiz").click().run()
    if "start_studying" not in [b.key for b in app.button]:
        return  # the units could not be planned; the step shows why
    app.number_input(key="study_target_days").set_value(days).run()
    app.button(key="start_studying").click().run()


def show_page(app, name: str):
    app.segmented_control(key="workspace_page").set_value(name).run()


def show_panel(app, name: str):
    """Beside the PDF on Today: Study or Ask the tutor."""
    show_page(app, "Today")
    app.segmented_control(key="today_tab").set_value(name).run()


def open_day(app, day: int):
    show_panel(app, "Study")
    app.segmented_control(key="day_picker").set_value(day).run()


def metrics(app):
    return {metric.label: metric.value for metric in app.main.metric}


def visible_text(app):
    return "\n".join(
        item.value
        for group in (app.subheader, app.text, app.caption, app.html, app.markdown, app.info)
        for item in group
    )


def labels(app) -> list[str]:
    return [b.label for b in app.button]


def plan_days(app) -> list[dict]:
    """The days the plan shows, from the timeline's HTML: number, state and what each one studies."""
    page = "\n".join(item.value for item in app.html if 'class="plan-days"' in item.value)
    days = []
    for state, number, body in re.findall(r'<li class="plan-day ([a-z]*)" data-day="(\d+)">(.*?)</li>', page):
        units = re.findall(r'<span class="plan-kind [a-z]+">(\w+)</span><span class="plan-unit-title">(.*?)</span>',
                           body)
        study = " · ".join(f"{kind}: {unescape(title)}" for kind, title in units) or "Optional review"
        days.append({"Day": int(number), "State": state, "Study": study})
    return days
