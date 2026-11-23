# Adaptive Tutor

Adaptive Tutor turns a PDF into a study outline, a daily plan, and checks whose questions link to their source pages. Upload lecture notes, mark the topics you find unclear, answer a short quick check, and choose how many days to spend on the material. After each study day, a check asks questions from that day's pages.

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

The outline, planning, quick check, daily check and tutor features call OpenAI with the app's own key. Put it in a `.env` file at the project root (it is ignored by git), or set it in the environment, which takes precedence:

```bash
echo 'OPENAI_API_KEY=sk-...' > .env
```

Then start the app from the project root:

```bash
.venv/bin/python -m streamlit run app.py
```

Then open the URL it prints (usually http://localhost:8501) and follow the four setup steps.

### How the app is organized

The app has two parts: **setup**, four steps taken once for each PDF, then the **study workspace**, used day by day.

**Setup** fills the page's width and shows one step at a time. The step bar at the top shows where you are (✓ marks a step you have finished) and opens any step you have already reached, so you can go back and change an earlier choice. Each step ends with the button for the next one.

1. **Material**: the model, and the PDF to study.
2. **Topics**: the outline of your PDF. Check the topics you don't understand yet.
3. **Quick check**: a few questions from your pages, one at a time. You can skip it.
4. **Plan**: choose the number of days and see the plan before you start.

The **study workspace** opens when you select **Start studying**. The bar at the top switches between three pages:

- **Today**: a row of days (✓ a checked day, ↻ a review day) above the PDF. Beside the PDF, **Study** shows the open day's knowledge points, readings and task, and **Ask the tutor** shows the chat. Page links there turn the PDF to that page. Below the PDF, **Page** and **Text** switch between the page itself and the text the tutor reads from it.
- **Plan**: your goal, the number of days the plan now has and how many you have checked, every day down a timeline (checked days in green, the next day in yellow, reviews in orange), **Plan changes**, and **Change the plan**.
- **Progress**: each unit's status with the evidence behind it, and your quick check answers.

Outside the Today page's PDF, page links open the page in a window, so you never lose your place. **Settings** at the top right holds the model after the first step, and **Start over with another PDF**, which clears the outline, the plan and your progress but keeps the model.

### The OpenAI key and model

The app reads its key from `OPENAI_API_KEY`: the environment first, then the `.env` file at the project root (on Streamlit Community Cloud, add it as a root-level secret, which Streamlit passes to the environment). Learners never enter or see the key. Every learner using the app spends from this key, so do not share a public deployment's URL widely. Without a key, the first step says how to set one and nothing is sent to OpenAI.

Learners choose the model in the first step; afterwards it is under **Settings**.

**Model** starts with the default, `gpt-6-luna`, then recommended models from the newest (`gpt-6.2-sol`, `gpt-5.6-luna` and others) down to `gpt-4o-mini`; each was checked with tool calls and structured outputs. Once the key's models are loaded, the list keeps the recommended models the account has and adds its other chat models after them; when the account has no `gpt-6-luna`, the default becomes `gpt-4.1-mini`. **Other…** accepts any model ID. Pro models work but take about 50 seconds a call. The tutor needs a model that supports tool calls and structured outputs; if one fails, switch back to the default. The chosen model applies to everything in your session.

### Step 1: Material

Choose a model and upload a PDF. The step shows how many pages the PDF has and how many have readable text; a damaged or password-protected PDF is reported here. **Next: review the topics** is available once the PDF is in (and the app has a key). The PDF is kept when you come back to this step; choose another PDF to replace it, which starts over.

### Step 2: Topics

The outline is made as soon as this step opens; there is no button to press. If the request fails, the reason and **Try again** appear instead of repeating it on every interaction. Short documents use one model request. Longer documents are processed in batches; topics with matching titles are combined in page order. Blank, image-only, or unreadable pages are skipped.

Each topic shows its summary, its pages and **I don't understand this**. Check the topics you find unclear: the quick check asks about them first, and the plan gives them more time. Select a page link to compare a summary with the original page.

While you read the outline, the study units are planned in the background with a two-step Plan-and-Solve workflow: the first request groups or splits the topics into ordered learning units, and the second writes a learning objective and a study task for each one. The app checks topic coverage and takes the page references from the outline.

Then select **Start the quick check**, or **Skip to the plan**. **Ask the tutor about this material**, below the outline, answers questions before any plan exists.

### Step 3: Quick check

- With topics checked, there is one question for each checked topic, in the order you checked them. Each question is built from that topic's own pages.
- With nothing checked, up to three questions come from topics spread across the whole material.

Questions come one at a time. Select an answer and **Check answer** to see right away whether it was right, the correct answer, an explanation, and the passage of your material that supports it, with a link to its page. **Next question** moves on; after the last one, **See my results** lists your score and every answer. Your answers count only once the last one is in. If you leave the check halfway, it waits where you left it.

If you skip it, nothing is graded, and the topics you checked still get more time; you can still take the check from the Topics step.

### Step 4: Plan

Enter how many days you want to spend. The table below shows the plan for that number of days at once, so you can try a few numbers before deciding. Topics you checked, and topics you answered wrong, get more of the time: in a short plan their units share a day with fewer other units; in a long plan they get extra reading days first and a review day at the end of the plan. A short plan groups complete units together; a longer plan can put the reading on one or more days and the unit's study task on the next. Any days left after all readings and tasks are marked for optional review. Select **Start studying** to open the workspace at day 1.

To change the plan later, open **Change the plan** on the Plan page: check or uncheck topics, set the number of days, and select **Update plan**. The same units are redistributed locally, without a model call; checks and plan changes start again.

### Asking the tutor

**Ask the tutor** is under the outline in the Topics step and beside the PDF on the Today page; the conversation is the same in both. Type a question about the material and the tutor answers from your PDF only (agentic RAG):

- The app searches the PDF with your question before the tutor’s first reply. If those passages are insufficient, the tutor can try up to three searches of its own or read a full page. Code fragments such as `x = x + 1` are matched word for word.
- Every answer quotes the pages it relies on. The app checks that each quote appears on the cited page and that the tutor retrieved that page for this question; select a page link to open it.
- When the material doesn't cover the question, the tutor says so and names the missing topic instead of answering from general knowledge.
- It knows today's study units and the topics you marked as weak, and remembers the last few questions for follow-ups. The caption under the chat shows the model calls and tokens used so far.

### Knowledge points for each day

Each unit of the open day lists the 3–6 most important knowledge points its pages teach, in page order. Each point has a one-sentence explanation, a few details taken only from the pages, a page link that opens the page in the PDF, and, under **From page N**, the sentence of the page it comes from. The app checks that the words of that sentence are on the cited page in the same order (symbols, punctuation and the interleaving of slide columns are ignored), and drops a point whose quote is not; when none survive, the model is told why and tries once more. A title or agenda page says it has no points to list.

A day's points are made when you open the day and kept for the session; the next day's are made in the background meanwhile, and a review day reuses its unit's points. If a request fails, **Try again** appears instead of repeating it on every interaction. The unit's objective, its study task and links to all of its pages stay below the points.

### Checking your understanding each day

Study a day's knowledge points, readings and task, then select **Check my understanding** at the bottom of the day. The check takes the whole page and hides the PDF until it ends, so you answer from what you learned; the pages behind each answer open in a window. The questions come from that day's pages alone, and are prepared in the background as soon as you open the day, so the check starts without waiting; a review day gets fresh questions. When the day's pages have nothing the tutor can ask about, it says so for each unit; when you continue, the day is marked as checked and the plan is unchanged. When questions were made but none passed verification, **Try again** prepares them again.

Otherwise the tutor asks up to eight questions, at most three per unit, choosing each from your answers so far and showing why. Your answers in the check settle each unit studied that day:

- 2 right and none wrong: **understood**, and it gets no more questions;
- 2 wrong that outnumber the right ones: **needs review**, and it gets no more questions;
- 1 right and 1 wrong: a third question decides (2 of 3 right is **mixed answers**, 1 of 3 is **needs review**).

The tutor decides which unit to ask about next, spends the questions where the evidence is least clear, and stops early when every unit is settled. After every answer you see whether it was right, the correct answer, an explanation, and the supporting passage with a link to its page; at the end each unit's result and every answer are listed again.

A review day is added at the end of the plan for each unit studied that day that needs review. When your earlier answers show that the cause is an earlier unit, that unit gets a review too. Without such a unit, the check says so and the plan stays as it is. A review already planned is not added twice.

The Plan page shows your goal, how many days the plan now has, and how many you have checked. When reviews make the plan longer than your goal, it says by how much. **Plan changes** lists each change and the answers behind it.

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
