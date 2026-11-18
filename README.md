# Adaptive Tutor

Adaptive Tutor is a planned AI study assistant for people learning from their own lecture notes and handouts. Learners choose which topics to study, set a deadline, and enter the time they have each day. The tutor uses their answers to decide when to move on, ask a follow-up question, or revisit a prerequisite.

The project is in the **design stage**. The first demo will cover three introductory Python concepts: updating a variable, counting loop iterations, and tracing a variable through a loop.

## Planned features

- **Choose topics from an outline.** The tutor will group topics across uploaded PDFs and images. Learners will be able to open the original page or screenshot for each topic and check passages that were hard to read.
- **Build a daily study plan.** The tutor will use the selected topics, an initial assessment, and prerequisite relationships to schedule readings and exercises. If the work exceeds the time available, it will flag the conflict so the learner can adjust the scope or deadline.
- **Diagnose gaps with follow-up questions.** When a wrong answer has several plausible causes, the tutor will choose a question that helps distinguish them. A topic will stay marked “needs more evidence” until the learner’s answers support a judgment.
- **See why a plan changed.** Learners will be able to compare two versions of a plan, see which answer prompted a change, and check how much time the revised activity will take.

## Example learning session

A learner uploads a handout on loops and a screenshot of their class notes. They have 30 minutes a day for two weeks. During the initial assessment, they miscalculate the final value of a loop counter. To check whether the difficulty starts with assignment, the tutor asks, “What is the value of `x` after `x = 2` followed by `x = x + 1`?”

If the learner answers `3`, the tutor asks how many times the loop runs. If they answer `2`, it points to an assignment example in the handout and asks them to try again with different numbers. If their answers continue to suggest difficulty with assignment, the tutor can split the next day’s 30-minute session into 10 minutes of variable updates and 20 minutes of loop tracing.

## Getting started

Use Python 3.13 to create a project-local environment. Run these commands from the project root on macOS or Linux.

```bash
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

The dependencies include Streamlit for the interface, pypdf for text extraction, the OpenAI SDK for outline generation, and LangGraph for the tutor workflow. The web app entry point and launch instructions are planned for the first runnable release.

## Planned architecture

| Component | Responsibility |
| --- | --- |
| Streamlit interface | Let learners upload materials, confirm the outline, submit answers, and compare plans. |
| Document parsing and retrieval (RAG) | Index passages by file and location, then retrieve the source text for questions and feedback. |
| LangGraph workflow | Use answer evidence to choose the next step in assessment, follow-up, practice, or replanning. |
| Python scheduler and SQLite storage | Check daily time limits and prerequisite order. Save sessions, answers, and plan versions. |

## Development roadmap

- [x] Define the first learning scenario and add the project description and Git ignore rules.
- [ ] Support PDF and image uploads and generate a selectable outline with source references.
- [ ] Connect the initial assessment, a fixed study plan, and practice exercises so learners can resume a session.
- [ ] Add adaptive follow-up questions, review feedback against the evidence, and update plans based on learner responses.
- [ ] Add support for Word documents and publish the web demo and usage guide.

Importing Markdown materials from GitHub repositories is a possible extension after the core workflow is complete.
