# Adaptive Tutor

Adaptive Tutor turns a PDF into a study outline, a daily plan, and practice questions linked to their source pages. Upload lecture notes, generate an outline, and choose how many days to spend on the material. Each study day includes the option to practice what was assigned.

The planned tutoring workflow will use the learner’s goals, deadline, and answers to schedule study sessions. The first course will cover variable updates, loop counts, and loop tracing in Python.

## Planned features

- **Choose what to study.** Learners will be able to select topics from an outline built across multiple PDFs and images.
- **Personalize the daily study plan.** The tutor will use the selected topics, an initial assessment, and prerequisite relationships to schedule readings and exercises.
- **Diagnose gaps with follow-up questions.** When a wrong answer has several plausible causes, the tutor will choose a question that helps distinguish them. A topic will stay marked “needs more evidence” until the learner’s answers support a judgment.
- **See why a plan changed.** Learners will be able to compare two versions of a plan and see which answer prompted a change to a day's activities.

## Example of a planned learning session

A learner uploads a handout on loops and a screenshot of their class notes. They want to finish the material in two weeks. During the initial assessment, they miscalculate the final value of a loop counter. To check whether the difficulty starts with assignment, the tutor asks, “What is the value of `x` after `x = 2` followed by `x = x + 1`?”

If the learner answers `3`, the tutor asks how many times the loop runs. If they answer `2`, it points to an assignment example in the handout and asks them to try again with different numbers. If their answers continue to suggest difficulty with assignment, the tutor can schedule variable updates before loop tracing the next day.

## Getting started

Use Python 3.13 to create a project-local environment. Run these commands from the project root on macOS or Linux.

```bash
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

The outline, planning, and practice features use the OpenAI SDK and read `OPENAI_API_KEY` from the server process environment. With the key already exported, start the app from the project root:

```bash
python -m streamlit run app.py
```

If your key is in a local `.env` file, you can use `uv` to supply it to the same app at launch:

```bash
uv run --no-project --env-file .env -- .venv/bin/python -m streamlit run app.py
```

The default model is `gpt-4.1-mini`. To choose another model that supports structured outputs, set `OPENAI_MODEL` in the server environment.

### Generating an outline

1. Upload a PDF in the sidebar. Use the up/down arrows or the page selector beneath the PDF to navigate the original document. **Extracted text** below the reading area follows the selected page. The preview works offline.
2. Click **Generate outline**. Short documents use one model request. Longer documents are processed in batches; topics with matching titles are combined in page order. Blank, image-only, or unreadable pages are skipped.
3. The outline appears to the right of the PDF. Select a page reference under a topic to check its summary against the original page. Switching pages reuses the outline. Removing or replacing the PDF clears it.

### Scheduling the outline

1. In the sidebar, enter the **Target duration (days)** and select **Create study plan**. The plan appears beside the PDF, and the outline moves below both, above the extracted text. Each panel scrolls independently. The first submission runs a two-step Plan-and-Solve workflow with OpenAI. The planning request uses the full outline to group or split topics into ordered learning units. The second request follows that plan to write a learning objective and a study task for each unit. The app checks topic coverage and takes the page references from the outline.
2. Choose a **Study day** to see its learning content and open the cited pages. A short plan groups complete units together. A longer plan can put the reading on one or more days and the unit's study task on the next. Any days left after all readings and tasks are marked for optional review.
3. To adjust the pace, change the duration and submit again. Python redistributes the same units locally. The plan stays available while browsing the PDF in the current session and clears when the PDF changes.

### Practicing a day's material

1. Choose a study day and click **Generate daily practice** in the plan panel. Each assigned learning item gets 1–5 single-answer multiple-choice or true/false questions. Optional review days point back to the earlier assignments.
2. The app indexes readable PDF passages locally and ranks them with BM25. It retrieves passages from the assigned pages and looks elsewhere in the same document for related exercises, including chapter-end questions. OpenAI uses these excerpts to reuse, adapt, or write questions. Each question links to its source pages and shows its origin.
3. Select an option and click **Check answer** to see feedback and the source of the answer. The app distinguishes a verified PDF answer key, an answer taken directly from the assigned reading, and a model reference answer. If model drafts fail validation, the app can use a clearly keyed exercise or build a fill-in-the-blank check from a numeric value in a relevant sentence on the assigned pages. When neither is available, the day shows that the reading had too little evidence for practice. Pages that teach nothing to assess, such as a title slide, an agenda, course logistics or references, get no practice: the app skips them when it finds no teaching point or exercise, and the model can also decline them. Either way the plan shows the reason. Questions and submitted answers follow the same unit and cited pages when you change days or adjust the schedule. They are kept in the current PDF session.

### Marking weak topics

After the outline appears, check **I find this weak or unclear** under any topic. In the sidebar you can also describe what you don't understand in a sentence. Both are used when you select **Create study plan**:

- Weak topics get more of the time. In a short plan their units share a day with fewer other units; in a long plan they get extra reading days first and a review day, before other units get extra reading days.
- The tutor matches your sentence to units in the material, and tells you when it describes something the material doesn't cover.

**Learning status** shows each unit's status and the evidence behind it. A unit marked weak is only suspected until answers check it; practice answers decide whether it is understood or a likely gap.

### Diagnosing a difficulty (command line)

The diagnosis agent is not in the web app yet. To try it on a PDF, run it in the terminal with the same environment as the app:

```bash
uv run --no-project --env-file .env -- .venv/bin/python -m tutor.agent.cli path/to/lesson.pdf --trace
```

The tutor builds the study units, asks which units are unclear, then asks up to five questions from your material. It chooses each question from your earlier answers and shows why. It reports a confirmed gap only after at least two wrong answers on that unit; otherwise its conclusion stays uncertain. `--trace` lists every model call and tool step with its time and tokens.

## Planned architecture

| Component | Responsibility |
| --- | --- |
| Streamlit interface | Let learners upload materials, confirm the outline, submit answers, and compare plans. |
| Document parsing and retrieval (RAG) | Index passages by file and location, then retrieve the source text for questions and feedback. |
| LangGraph workflow | Use answer evidence to choose the next step in assessment, follow-up, practice, or replanning. |
| Python scheduler and SQLite storage | Assign readings and activities to days in learning order. Save sessions, answers, and plan versions. |

## Development roadmap

- [x] Define the first learning scenario and add the project description and Git ignore rules.
- [x] View the original PDF page by page and inspect its extracted text.
- [x] Generate a PDF study outline with source page references.
- [x] Schedule the full outline across a learner-selected number of days and browse each day's readings.
- [x] Retrieve PDF passages and exercises for each day's learning items, generate practice, and check answers.
- [ ] Support images and let learners select topics for their plan.
- [ ] Connect the initial assessment, a fixed study plan, and practice exercises so learners can resume a session.
- [ ] Add adaptive follow-up questions, review feedback against the evidence, and update plans based on learner responses.
- [ ] Add support for Word documents and publish the web demo and usage guide.

Importing Markdown materials from GitHub repositories is a possible extension after the core workflow is complete.
