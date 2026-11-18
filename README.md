# Adaptive Tutor

Adaptive Tutor helps learners turn their own lecture notes into a study outline. Upload a PDF to see its original pages, including figures, tables, and scans. Select **Generate outline** to send the readable page text to OpenAI. Each topic includes a summary and page buttons that open the supporting material in the preview.

The planned tutoring workflow will use the learner’s goals, deadline, and answers to schedule study sessions. The first course will cover variable updates, loop counts, and loop tracing in Python.

## Planned features

- **Choose what to study.** Learners will be able to select topics from an outline built across multiple PDFs and images.
- **Build a daily study plan.** The tutor will use the selected topics, an initial assessment, and prerequisite relationships to schedule readings and exercises. If the work exceeds the time available, it will flag the conflict so the learner can adjust the scope or deadline.
- **Diagnose gaps with follow-up questions.** When a wrong answer has several plausible causes, the tutor will choose a question that helps distinguish them. A topic will stay marked “needs more evidence” until the learner’s answers support a judgment.
- **See why a plan changed.** Learners will be able to compare two versions of a plan, see which answer prompted a change, and check how much time the revised activity will take.

## Example of a planned learning session

A learner uploads a handout on loops and a screenshot of their class notes. They have 30 minutes a day for two weeks. During the initial assessment, they miscalculate the final value of a loop counter. To check whether the difficulty starts with assignment, the tutor asks, “What is the value of `x` after `x = 2` followed by `x = x + 1`?”

If the learner answers `3`, the tutor asks how many times the loop runs. If they answer `2`, it points to an assignment example in the handout and asks them to try again with different numbers. If their answers continue to suggest difficulty with assignment, the tutor can split the next day’s 30-minute session into 10 minutes of variable updates and 20 minutes of loop tracing.

## Getting started

Use Python 3.13 to create a project-local environment. Run these commands from the project root on macOS or Linux.

```bash
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

The outline generator uses the OpenAI SDK and reads `OPENAI_API_KEY` from the server process environment. With the key already exported, start the app from the project root:

```bash
python -m streamlit run app.py
```

If your key is in a local `.env` file, you can use `uv` to supply it to the same app at launch:

```bash
uv run --no-project --env-file .env -- .venv/bin/python -m streamlit run app.py
```

The default outline model is `gpt-4.1-mini`. To choose another model that supports structured outputs, set `OPENAI_MODEL` in the server environment.

### Generating an outline

1. Upload a PDF and use the page selector to read the original document. Expand **Extracted text** to see which text is available for the outline. The preview works offline.
2. Click **Generate outline**. Short documents use one model request. Longer documents are processed in batches; topics with matching titles are combined in page order. Blank, image-only, or unreadable pages are skipped.
3. Select a page reference under a topic to check its summary against the original PDF page. Switching pages reuses the outline. Removing or replacing the PDF clears it.

## Planned architecture

| Component | Responsibility |
| --- | --- |
| Streamlit interface | Let learners upload materials, confirm the outline, submit answers, and compare plans. |
| Document parsing and retrieval (RAG) | Index passages by file and location, then retrieve the source text for questions and feedback. |
| LangGraph workflow | Use answer evidence to choose the next step in assessment, follow-up, practice, or replanning. |
| Python scheduler and SQLite storage | Check daily time limits and prerequisite order. Save sessions, answers, and plan versions. |

## Development roadmap

- [x] Define the first learning scenario and add the project description and Git ignore rules.
- [x] View the original PDF page by page and inspect its extracted text.
- [x] Generate a PDF study outline with source page references.
- [ ] Support images and let learners select topics for their plan.
- [ ] Connect the initial assessment, a fixed study plan, and practice exercises so learners can resume a session.
- [ ] Add adaptive follow-up questions, review feedback against the evidence, and update plans based on learner responses.
- [ ] Add support for Word documents and publish the web demo and usage guide.

Importing Markdown materials from GitHub repositories is a possible extension after the core workflow is complete.
