# Evaluation report: Adaptive Tutor

Team: _Name (NetID)_, _Name (NetID)_

**Submitted files:**
- Tasks: [`tasks.jsonl`](../tasks.jsonl)
- Evaluation script: [`eval/run_eval.py`](run_eval.py), using [`eval/baseline.py`](baseline.py) and [`eval/diagnosis.py`](diagnosis.py)
- Results: [`eval/results/results.md`](results/results.md); every reply, grade and trace is in [`eval/results/runs.jsonl`](results/runs.jsonl)
- Results before the fix in "Fixing the failure": [`eval/results/before_fix/`](results/before_fix/); the side-by-side comparison is [`eval/results/ab_comparison.md`](results/ab_comparison.md)

To reproduce the results, run:

```bash
uv run --no-project --env-file .env -- .venv/bin/python -m eval.run_eval --pdf path/to/week_2.pdf --timeout 20
```

## Setup

| | Question answering (t01–t50) | Diagnosis (d01–d10) |
|---|---|---|
| Agent | `tutor/agent/qa.py`: chooses its searches (at most 3), can read pages, and retries when a citation fails the check | `tutor/agent/loop.py`: a ReAct daily check that picks the next unit to question from the answers so far |
| Non-agentic baseline | One BM25 search with the question as written (top 5 passages), then one model call. It can decline; its citations are not checked | Asks the first 2 questions of every unit studied today regardless of the answers, then makes one model call for the conclusion, checked by the same `validate_finish` |
| Material | Week 2 slides (59 pages) | A fixed, hand-written snapshot of the Week 2 slides (4 units × 3 questions). The simulated learner's answer to every question is fixed, so differences between runs come from the agent alone |
| Grading | `rubric`: an LLM judge must find every rubric point. `unanswerable`: passes only if the tutor declines | `exact`: `primary_gap`, `status` and `next_step` must match the expected conclusion. A conclusion that `validate_finish` rejects fails |
| Edge cases | t46–t48 (edge cases); t49–t50 (unanswerable) | d06 (a careless slip), d10 (questions run out) |

Both systems use the same model (`gpt-6-luna`), retrieval index and grader. The baseline runs once; the agent runs 3 times. The judge's calls are not counted in either system's tokens or latency.

## Results

| Suite | System | Accuracy | Avg turns | Avg latency | p95 latency | Avg tokens |
|---|---|---|---|---|---|---|
| QA (50) | Baseline | 82% | 1.00 | 2.1 s | 3.2 s | 1,303 |
| QA (50) | Agent, 3 runs | **95%** | 2.63 | 4.0 s | 7.0 s | 5,100 |
| Diagnosis (10) | Baseline | 70% | 1.00 | 2.3 s | 4.2 s | 1,430 |
| Diagnosis (10) | Agent, 3 runs | **100%** | 6.13 | 10.6 s | 13.7 s | 11,471 |

| Suite | pass@3 | pass^3 | Tasks whose outcome changed across runs |
|---|---|---|---|
| QA | 96% | 92% | t19 (✗✓✓), t23 (✓✓✗) |
| Diagnosis | 100% | 100% | none |

The results for each individual run are in [`results/results.md`](results/results.md).

**QA accuracy by category:**

| Category | Tasks | Baseline | Agent |
|---|---|---|---|
| direct | 12 | 100% | 100% |
| application | 12 | 75% | 86% |
| paraphrase | 12 | 83% | 100% |
| cross_page | 9 | 56% | 89% |
| edge_case | 3 | 100% | 100% |
| unanswerable | 2 | 100% | 100% |

## Analysis

**Question answering.** The agent's lead comes from the questions a single search cannot handle:

- **paraphrase** (83% → 100%) and **cross_page** (56% → 89%). The baseline searches with the question as worded. When that wording misses the slide, the baseline declines (t16, t21, t29, t34, t40) or answers from only one of the pages it needed.
- **The agent rewords its search and reads more pages.** It averages 2.63 model calls per question, so the gain costs about 4 times the tokens (5,100 vs 1,303) and twice the latency (4.0 s vs 2.1 s; p95 7.0 s vs 3.2 s).
- **The agent's remaining failures are incomplete answers.** It found the right material, but the answer missed one rubric point:
  - t15 and t43 fail for both systems in every run.
  - t19 and t23 each fail in one of the agent's three runs, which is why they changed outcome across runs.
  - The judge's reasons show the answers are correct but leave out one detail, e.g. "the assistant response is appended first". These rubrics may be stricter than the question requires.

**Diagnosis.** The agent reached the expected conclusion on all 10 tasks in all 3 runs, asking 4.1 questions per check against the baseline's 3.9. Two things limit the baseline:

- **Fixed questions.** In d05 (right, wrong, wrong), two fixed questions give one right and one wrong, which cannot confirm a gap. The agent asks the third question.
- **No second chance.** Most of the baseline's failures are conclusions that `validate_finish` rejected, such as `confirmed` without enough wrong answers, or sentences instead of question IDs in `evidence`. The agent receives the same rejection as a tool result and corrects its conclusion; the one-shot baseline cannot. Because it depends on one unchecked model call, the baseline's accuracy varied from run to run of the whole evaluation: **80%, 50% and 70%** across our three full evaluations, with the code unchanged. The agent scored 100% each time. The agent costs about 8 times the tokens and 4.6 times the latency (10.6 s). In use, a learner spends far longer than that thinking about each answer.

## Failure trace (t03, before the fix)

Before the fix, task t03 (what share of chats Klarna's assistant handled, and the staffing equivalent; answer: two-thirds, equal to 700 agents) failed in two of the agent's three runs, and the step that went wrong was the citation check, not retrieval. The agent's first search found the right page, p14. That slide sets three case studies side by side in columns, and the PDF text extractor reads it line by line across the columns, so p14's text reads "Its assistant handled two-thirds of Its support chatbot described a refund A coding agent wiped a user's live support chats in its first month…". The model understood the slide and quoted the sentence a human reads, "Its assistant handled two-thirds of support chats in its first month, work the company equated to 700 agents.", but `_check_answer` required each quote to appear verbatim in the extracted text and rejected it. The agent then re-read p14 and quoted the same sentence, tried a fragment that was too short, and tried p12, which is also laid out in columns; every citation was rejected, and after 6 model calls it returned `failed` although its answer was right. The baseline, which does not check citations, answered correctly. The strict check guarantees that the agent never shows an unverified quote, but on slides laid out in columns it also stops the agent from showing a correct answer: the same cause produced 9 of the agent's 150 runs that ended `failed` (t03, t09, t12, t37, t41 and t42) and made those tasks change outcome across runs.

## Fixing the failure: an A/B test

**The fix.** `qa.py` now accepts a quote when its words appear on the cited page in order, with a bounded number of other words in between. This is the word-order check `tutor/materials/cards.py` already uses for knowledge-point cards. A sentence that is not on the page is still rejected, and the page must still be one the agent retrieved. We also made the request timeout configurable (`--timeout 20` for the evaluation; the web app keeps 60 s for slow models).

**The test.** A (the code before the fix) and B (after) ran on the same 60 tasks **at the same time**, so both met the same API conditions.

| QA agent | A: before | B: after |
|---|---|---|
| Accuracy | 90% | **95%** |
| pass^3 | 82% | **92%** |
| pass@3 | 98% | 96% |
| Runs that gave up (`failed`) | 9 | **0** |
| Avg turns | 3.33 | **2.63** |
| Avg latency | 5.9 s | **4.0 s** |
| p95 latency | 12.9 s | **7.0 s** |
| Avg tokens | 7,034 | **5,100** |

All six affected tasks (t03, t09, t12, t37, t41, t42) passed in all three runs after the fix. Fewer rejected quotes meant fewer retries, so one fix improved accuracy, consistency, latency and cost together.

- **pass@3 fell by one task:** t15 passed once in A by chance and never in B. In every run its failures are the rubric point described above, which is not a citation failure.
- **The other suites behaved as expected.** The QA baseline (82%) and the diagnosis agent (100%) were unchanged, because neither uses the citation check.
- **The timeout change was not exercised.** In our first full evaluation, 23 OpenAI calls stalled for 40–107 s without an error and inflated the agents' latency. That is why we made the timeout configurable. During this A/B run no call took longer than 14 s, so this test does not show whether the shorter timeout helps; the latency gain above comes from the fewer turns.
