# Evaluation results

Model `gpt-6-luna` · agent runs: 3

## PDF question answering: Ask the tutor

50 tasks

| System | Accuracy | Avg turns | Avg latency | p95 latency | Avg tokens |
|---|---|---|---|---|---|
| Baseline (one-shot RAG) | 82% | 1.00 | 2.2 s | 3.8 s | 1,319 |
| Agent, run 1 | 94% | 3.22 | 5.9 s | 11.7 s | 6,747 |
| Agent, run 2 | 88% | 3.54 | 6.4 s | 14.4 s | 7,583 |
| Agent, run 3 | 88% | 3.24 | 5.4 s | 11.9 s | 6,773 |
| Agent, all 3 runs | 90% | 3.33 | 5.9 s | 12.9 s | 7,034 |

| pass@3 | pass^3 | Tasks whose outcome changed across runs |
|---|---|---|
| 98% | 82% | t03 (✓✗✗), t09 (✓✓✗), t12 (✓✗✗), t15 (✗✓✗), t37 (✓✗✗), t40 (✓✗✓), t41 (✗✓✓), t42 (✓✗✓) |

| Category | Tasks | Baseline | Agent (all runs) |
|---|---|---|---|
| direct | 12 | 100% | 86% |
| application | 12 | 75% | 94% |
| paraphrase | 12 | 83% | 100% |
| cross_page | 9 | 56% | 70% |
| edge_case | 3 | 100% | 100% |
| unanswerable | 2 | 100% | 100% |

Failed runs:

- t15 · baseline run 1: The answer states that the loop returns `resp.content[0].text` without running tools or starting another iteration, but it does not mention that the assistant response is appended first. The rubric requires that step, so the answer does not satisfy every rubric point.
- t16 · baseline run 1: The answer says the function returns `None`, but the rubric requires the step-limit message, `Stopped: step limit reached.`
- t21 · baseline run 1: kind=declined: The passages cover a Seattle–Tokyo weather comparison using parallel calls, but not the three-city grouping example or its call savings and rounds.
- t29 · baseline run 1: kind=declined: The passages cover the agent loop, tool selection, retries, and tool descriptions instead.
- t34 · baseline run 1: kind=declined: The passages cover tool design, selection, and error recovery, but not what to do with two tools that search different collections.
- t40 · baseline run 1: The answer correctly identifies HTTP 503 as retryable and says to retry with backoff, but it does not state that the allowed units are celsius and fahrenheit or that the model can correct the invalid argument and call again. It also does not clearly say to report failure if the retries persist.
- t42 · baseline run 1: The answer correctly says the description comes from the function’s docstring, but it omits that the model also reads the system prompt, conversation, and prior tool results when deciding whether to call a tool.
- t43 · baseline run 1: It correctly says the Seattle weather call depends on the coordinates call. But it does not state that independent-call results are returned together in one user message, with each result matched to its tool_use_id; saying the loop sends back every result is not enough to satisfy that requirement.
- t44 · baseline run 1: It correctly gives three attempts and two sleeps, and says the model takes over after the final try. However, it does not specify that retries are first handled in code or that the final ToolError is reported to the model’s recovery layer.
- t15 · agent run 1: The answer correctly says it returns the final text without running a tool, but it omits that the loop first appends the assistant response.
- t41 · agent run 1: kind=failed: I couldn't find a verified answer in your material. Try asking again with the words your material uses.
- t43 · agent run 1: The answer correctly explains that weather depends on the coordinates, and that the independent calls can run together. However, it does not state that their results are returned in one user message with each result matched to its tool_use_id, as required by the second rubric point.
- t03 · agent run 2: kind=failed: I couldn't find a verified answer in your material. Try asking again with the words your material uses.
- t12 · agent run 2: kind=failed: I couldn't find a verified answer in your material. Try asking again with the words your material uses.
- t37 · agent run 2: kind=failed: I couldn't find a verified answer in your material. Try asking again with the words your material uses.
- t40 · agent run 2: The answer correctly says the model can correct the invalid argument and that code retries HTTP 503 with backoff, but it does not explicitly state that the schema allows only `celsius` and `fahrenheit` or that 503 is in the helper’s retryable status set. Since every rubric point is required, it does not pass.
- t42 · agent run 2: kind=failed: I couldn't find a verified answer in your material. Try asking again with the words your material uses.
- t43 · agent run 2: The answer correctly explains that the weather call depends on the coordinates, and that independent calls can run together. But it does not say that their results are returned in one user message or that each result is matched by tool_use_id, as required by the rubric.
- t03 · agent run 3: kind=failed: I couldn't find a verified answer in your material. Try asking again with the words your material uses.
- t09 · agent run 3: kind=failed: I couldn't find a verified answer in your material. Try asking again with the words your material uses.
- t12 · agent run 3: kind=failed: I couldn't find a verified answer in your material. Try asking again with the words your material uses.
- t15 · agent run 3: The answer correctly says it returns the final text without executing a tool, but it omits that the loop first appends the assistant response.
- t37 · agent run 3: kind=failed: I couldn't find a verified answer in your material. Try asking again with the words your material uses.
- t43 · agent run 3: It correctly explains that Seattle weather depends on the coordinates result and that the parallel example uses independent city-specific calls. However, it does not say that the results are returned in one user message with each matched by tool_use_id, as the rubric requires.

## Diagnosis: the daily-check agent

10 tasks

| System | Accuracy | Avg turns | Avg latency | p95 latency | Avg tokens | Avg questions |
|---|---|---|---|---|---|---|
| Baseline (2 fixed questions per unit + one model call) | 50% | 1.00 | 2.9 s | 6.2 s | 1,506 | 3.9 |
| Agent, run 1 | 100% | 6.10 | 10.2 s | 11.3 s | 11,356 | 4.1 |
| Agent, run 2 | 100% | 6.30 | 10.7 s | 15.1 s | 11,929 | 4.1 |
| Agent, run 3 | 100% | 6.10 | 10.2 s | 12.7 s | 11,342 | 4.1 |
| Agent, all 3 runs | 100% | 6.17 | 10.3 s | 13.4 s | 11,542 | 4.1 |

| pass@3 | pass^3 | Tasks whose outcome changed across runs |
|---|---|---|
| 100% | 100% | none |

| Category | Tasks | Baseline | Agent (all runs) |
|---|---|---|---|
| diagnosis | 10 | 50% | 100% |

Failed runs:

- d03 · baseline run 1: no accepted conclusion; fallback {'primary_gap': 'unit-4', 'status': 'uncertain', 'next_step': 'review_today'}
- d05 · baseline run 1: status=uncertain, expected confirmed
- d06 · baseline run 1: no accepted conclusion; fallback {'primary_gap': 'unit-3', 'status': 'uncertain', 'next_step': 'review_today'}
- d08 · baseline run 1: no accepted conclusion; fallback {'primary_gap': 'unit-2', 'status': 'uncertain', 'next_step': 'revisit_earlier'}
- d09 · baseline run 1: no accepted conclusion; fallback {'primary_gap': 'none', 'status': 'uncertain', 'next_step': 'continue'}
