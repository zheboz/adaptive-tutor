# Adaptive Tutor

Adaptive Tutor turns a PDF into a study outline, a daily plan, and checks whose questions link to their source pages. Upload lecture notes, generate an outline, and choose how many days to spend on the material. After each study day, a check asks questions from that day's pages.

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

The outline, planning, quiz, check and tutor features use the OpenAI SDK and read `OPENAI_API_KEY` from the server process environment. With the key already exported, start the app from the project root:

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

### Initial quiz, then the plan

1. After the outline appears, check **I don't understand this** under the topics you find unclear.
2. Select **Start initial quiz** in the sidebar. The study units are prepared, and the quiz takes the outline's place beside the PDF:
   - With topics checked, there is one question for each checked topic, in the order you checked them. Each question is built from that topic's own pages.
   - With nothing checked, up to three questions come from topics spread across the whole material.
3. Answer every question and select **Submit answers**. Only then do you see whether each answer was right, the correct answer, an explanation, and the passage of your material that supports it, with a link that opens that page.
4. The plan controls appear after the results. Set the number of days and select **Create study plan**. Topics you checked, and topics you answered wrong, get more of the time: in a short plan their units share a day with fewer other units; in a long plan they get extra reading days first and a review day.

**Learning status** shows each unit's status and the evidence behind it. To ask about something specific you don't understand, use **Ask the tutor**.

### Asking the tutor

**Ask the tutor** appears once the outline is ready. Type a question about the material and the tutor answers from your PDF only (agentic RAG):

- It decides what to search for, tries other wording or reads a page when the first search misses, and uses at most three searches per question. Code fragments such as `x = x + 1` are matched word for word.
- Every answer quotes the pages it relies on. The app checks that each quote appears on the cited page and that the tutor retrieved that page for this question; select a page link to open it beside the chat.
- When the material doesn't cover the question, the tutor says so and names the missing topic instead of answering from general knowledge.
- It knows today's study units and the topics you marked as weak, and remembers the last few questions for follow-ups. The caption under the chat shows the model calls and tokens used so far.

### Checking your understanding each day

Study a day's readings and task, then select **Check my understanding** at the bottom of the day. Only then are questions prepared, from that day's pages alone; a review day gets fresh questions. When the day's pages have nothing the tutor can ask about, it says so for each unit and leaves the plan unchanged.

Otherwise the tutor asks up to three questions, choosing each from your earlier answers and showing why. After every answer you see whether it was right, the correct answer, an explanation, and the supporting passage with a link to its page; at the end every answer is listed again. It reports a confirmed gap only after at least two wrong answers on a unit that outnumber the correct ones. It then continues, adds a review of today's unit after its remaining study days, or, when your earlier answers show the cause is an earlier unit, adds a review of that unit. A review already planned later is not added twice.

The plan shows your goal, how many days the plan now has, and how many you have checked. When reviews make the plan longer than your goal, it says by how much. **Plan changes** lists each change and the answers behind it.

To try a diagnosis in the terminal instead, run:

```bash
uv run --no-project --env-file .env -- .venv/bin/python -m tutor.agent.cli path/to/lesson.pdf --trace
```

`--trace` lists every model call and tool step with its time and tokens.

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
