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

The outline, planning, quiz, check and tutor features call OpenAI with the key each learner enters at the top of the page; the app has no key of its own. Start the app from the project root:

```bash
.venv/bin/python -m streamlit run app.py
```

Then open the app, enter your OpenAI API key under **OpenAI settings**, and choose a model (the default is `gpt-4.1-mini`).

### Your OpenAI key and model

The bar at the top of the page holds **OpenAI API key**, **Model** and **PDF to study**; there is no sidebar. Enter your OpenAI API key: it is hidden as you type, and the eye button in the field shows or hides it. The key is used only in your browser session: it is not saved, not shown to anyone else, and not written to the server's environment, so other people using the same app never use it.

**Model** starts with the default, `gpt-6-luna`, then recommended models from the newest (`gpt-6.2-sol`, `gpt-5.6-luna` and others) down to `gpt-4o-mini`; each was checked with tool calls and structured outputs. Once your key is entered, the list keeps the recommended models your account has and adds its other chat models after them; when your account has no `gpt-6-luna`, the default becomes `gpt-4.1-mini`. **Other…** accepts any model ID. Pro models work but take about 50 seconds a call. The tutor needs a model that supports tool calls and structured outputs; if one fails, switch back to the default. Your key and model apply to everything in your session: the outline, the plan, the quiz, the daily checks and Ask the tutor.

The app never uses a key from the server's environment: without your key, nothing is sent to OpenAI.

### Page layout

A step bar at the top shows where you are (Upload › Outline › Mark & quiz › Plan › Study) and what to do next. The top bar holds only the key, the model and the upload; every other action is in the panel beside the PDF, where you are already looking. The PDF stays on the left in a panel with its page controls at the bottom; the page fits the panel's width and scrolls inside it when taller. On the right, a panel of the same height, so the two line up, holds a row of views at the top; the selected view scrolls below it. Both panels fill the window's height below the step bar (at least 460 pixels):

- Before the plan: **Outline** (check the topics you don't understand, then start or skip the quiz at the end), **Initial quiz** (the questions, the answers, then the number of days and **Create study plan**) and **Progress**.
- After the plan: **Today** (the open study day's knowledge points and its check), **Plan** (goal, length and checked days, every day in a table, plan changes, **Change the number of days** and the outline) and **Progress** (each unit's status and the initial quiz answers).

**Ask the tutor** is always shown right below both panels, across the full width, from the moment a PDF is uploaded: it needs only the PDF, not the outline or the plan. The text read from the current page is in a collapsed **Extracted text** section at the bottom of the page.

Days are picked from a row of buttons: ✓ marks a checked day and ↻ a review day. Page links in any view open the page in the PDF beside it. The app switches to the quiz when it starts and to Today when a plan is created.

### Generating an outline

1. Upload a PDF in the top bar. Use the up/down arrows or the page selector beneath the PDF to navigate the original document. **Extracted text** at the bottom of the page follows the selected page. The preview works offline.
2. The outline is generated as soon as the PDF and your key are in; there is no button to press. If the request fails, the reason and **Try again** appear beside the PDF; other interactions do not repeat it. Short documents use one model request. Longer documents are processed in batches; topics with matching titles are combined in page order. Blank, image-only, or unreadable pages are skipped.
3. The outline appears to the right of the PDF. Select a page reference under a topic to check its summary against the original page. Switching pages reuses the outline. Removing or replacing the PDF clears it.

### Scheduling the outline

1. Below the initial quiz results, enter the **Target duration (days)** and select **Create study plan**. The plan opens in the **Today** view. The study units come from a two-step Plan-and-Solve workflow with OpenAI, which starts in the background as soon as the outline is ready, while you read it and check topics; starting the quiz waits only for whatever is left. The planning request uses the full outline to group or split topics into ordered learning units. The second request follows that plan to write a learning objective and a study task for each unit. The app checks topic coverage and takes the page references from the outline.
2. Choose a **Study day** to see its learning content and open the cited pages. A short plan groups complete units together. A longer plan can put the reading on one or more days and the unit's study task on the next. Any days left after all readings and tasks are marked for optional review.
3. To adjust the pace, open **Change the number of days** in the **Plan** view and submit again. Python redistributes the same units locally. The plan stays available while browsing the PDF in the current session and clears when the PDF changes.

### Initial quiz, then the plan

1. After the outline appears, check **I don't understand this** under the topics you find unclear in the **Outline** view.
2. Select **Start initial quiz** at the end of the outline. The quiz opens in the **Initial quiz** view:
   - With topics checked, there is one question for each checked topic, in the order you checked them. Each question is built from that topic's own pages.
   - With nothing checked, up to three questions come from topics spread across the whole material.
3. Answer every question and select **Submit answers**. Only then do you see whether each answer was right, the correct answer, an explanation, and the passage of your material that supports it, with a link that opens that page.
4. The plan controls appear right below the results. Set the number of days and select **Create study plan**. Topics you checked, and topics you answered wrong, get more of the time: in a short plan their units share a day with fewer other units; in a long plan they get extra reading days first and a review day at the end of the plan.

To go straight to the plan, select **Skip the quiz** instead. Nothing is graded, and the topics you checked still get more time.

**Learning status** shows each unit's status and the evidence behind it. To ask about something specific you don't understand, use **Ask the tutor**.

### Asking the tutor

**Ask the tutor** is available as soon as a PDF is uploaded. Type a question about the material and the tutor answers from your PDF only (agentic RAG):

- The app searches the PDF with your question before the tutor’s first reply. If those passages are insufficient, the tutor can try up to three searches of its own or read a full page. Code fragments such as `x = x + 1` are matched word for word.
- Every answer quotes the pages it relies on. The app checks that each quote appears on the cited page and that the tutor retrieved that page for this question; select a page link to open it beside the chat.
- When the material doesn't cover the question, the tutor says so and names the missing topic instead of answering from general knowledge.
- It knows today's study units and the topics you marked as weak, and remembers the last few questions for follow-ups. The caption under the chat shows the model calls and tokens used so far.

### Knowledge points for each day

Each unit of the open day lists the 3–6 most important knowledge points its pages teach, in page order. Each point has a one-sentence explanation, a few details taken only from the pages, a page link that opens the page in the PDF, and, under **From page N**, the sentence of the page it comes from. The app checks that the words of that sentence are on the cited page in the same order (symbols, punctuation and the interleaving of slide columns are ignored), and drops a point whose quote is not; when none survive, the model is told why and tries once more. A title or agenda page says it has no points to list.

A day's points are made when you open the day and kept for the session; the next day's are made in the background meanwhile, and a review day reuses its unit's points. If a request fails, **Try again** appears instead of repeating it on every interaction. The unit's objective, its study task and links to all of its pages stay below the points.

### Checking your understanding each day

Study a day's knowledge points, readings and task, then select **Check my understanding** at the bottom of the day. The questions come from that day's pages alone, and are prepared in the background as soon as you open the day, so the check starts without waiting; a review day gets fresh questions. When the day's pages have nothing the tutor can ask about, it says so for each unit; when you continue, the day is marked as checked and the plan is unchanged. When questions were made but none passed verification, **Try again** prepares them again.

Otherwise the tutor asks up to eight questions, at most three per unit, choosing each from your answers so far and showing why. Your answers in the check settle each unit studied that day:

- 2 right and none wrong: **understood**, and it gets no more questions;
- 2 wrong that outnumber the right ones: **needs review**, and it gets no more questions;
- 1 right and 1 wrong: a third question decides (2 of 3 right is **mixed answers**, 1 of 3 is **needs review**).

The tutor decides which unit to ask about next, spends the questions where the evidence is least clear, and stops early when every unit is settled. After every answer you see whether it was right, the correct answer, an explanation, and the supporting passage with a link to its page; at the end each unit's result and every answer are listed again.

A review day is added at the end of the plan for each unit studied that day that needs review. When your earlier answers show that the cause is an earlier unit, that unit gets a review too. Without such a unit, the check says so and the plan stays as it is. A review already planned is not added twice.

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
