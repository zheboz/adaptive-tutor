"""Driving the app in tests: the setup steps, then the study workspace."""

import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from tests.test_pdf_preview import APP, button, make_pdf
from tutor.llm import LLMError


KEY = "sk-test"


class UITestCase(unittest.TestCase):
    """The learner's models load without a request, and no request ever reaches OpenAI."""

    def setUp(self):
        self.list_models = self.enterContext(patch("tutor.ui.settings.list_models", return_value=[]))
        self.enterContext(patch("tutor.llm._request", side_effect=LLMError("No network in tests.")))

    def new_app(self, **kwargs) -> AppTest:
        return AppTest.from_file(APP, default_timeout=10, **kwargs).run()


def add_material(app, *pages, key: str | None = KEY) -> bytes:
    """In the first step: the key, then the PDF."""
    if key is not None and app.text_input(key="api_key_input").value != key:
        app.text_input(key="api_key_input").set_value(key).run()
    document = make_pdf(*pages)
    app.file_uploader[0].set_value(("lesson.pdf", document, "application/pdf")).run()
    return document


def begin(app, *pages, key: str | None = KEY) -> bytes:
    """Add the material and open the Topics step, where the outline is made."""
    document = add_material(app, *pages, key=key)
    app.button(key="material_next").click().run()
    return document


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
