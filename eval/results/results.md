# Evaluation results

Model `gpt-6-luna` · agent runs: 3

## PDF question answering: Ask the tutor

50 tasks

| System | Accuracy | Avg turns | Avg latency | p95 latency | Avg tokens |
|---|---|---|---|---|---|
| Baseline (one-shot RAG) | 82% | 1.00 | 2.1 s | 3.2 s | 1,303 |
| Agent, run 1 | 94% | 2.56 | 4.2 s | 7.3 s | 4,910 |
| Agent, run 2 | 96% | 2.74 | 4.1 s | 7.4 s | 5,427 |
| Agent, run 3 | 94% | 2.58 | 3.8 s | 6.5 s | 4,964 |
| Agent, all 3 runs | 95% | 2.63 | 4.0 s | 7.0 s | 5,100 |

| pass@3 | pass^3 | Tasks whose outcome changed across runs |
|---|---|---|
| 96% | 92% | t19 (✗✓✓), t23 (✓✓✗) |

| Category | Tasks | Baseline | Agent (all runs) |
|---|---|---|---|
| direct | 12 | 100% | 100% |
| application | 12 | 75% | 86% |
| paraphrase | 12 | 83% | 100% |
| cross_page | 9 | 56% | 89% |
| edge_case | 3 | 100% | 100% |
| unanswerable | 2 | 100% | 100% |

Failed runs:

- t15 · baseline run 1: The answer correctly says the loop returns the final text without running a tool, but it omits the required step of appending the assistant response before returning.
- t16 · baseline run 1: kind=declined: The passages cover the tool loop and the MAX_STEPS guard, but not what the function returns when the loop runs out of steps.
- t21 · baseline run 1: kind=declined: The passages cover a Seattle weather lookup and dependent tool calls, but not a three-city comparison with grouped lookups.
- t29 · baseline run 1: kind=declined: The passages cover sending the whole transcript each turn, tool selection, and retrying transient failures, but not what to do with older messages when the conversation exceeds the model’s window.
- t34 · baseline run 1: kind=declined: The passages cover tool design, selection, and error recovery, but do not say what consolidation to use for similar searches across different collections.
- t40 · baseline run 1: kind=declined: The passages cover tool contracts and retrying certain HTTP errors, but they don’t explain how the `units='F'` request is handled or what should happen next for either example.
- t42 · baseline run 1: The answer correctly says the description comes from the function’s docstring, but it omits that the model also reads the system prompt, conversation, and prior tool results when choosing whether to call a tool.
- t43 · baseline run 1: The answer correctly explains that the Seattle weather call depends on the coordinates. But it does not state that independent tool results are returned together in one user message, with each result matched to its tool_use_id.
- t44 · baseline run 1: The attempt and sleep counts are correct, and the answer identifies the model as taking over. However, it does not state that retries are first handled in code or that the final ToolError is reported to the model’s recovery layer.
- t15 · agent run 1: The answer correctly says the loop returns the final text without running a tool, but it omits the rubric requirement that the assistant response is appended first.
- t19 · agent run 1: The answer correctly says argument validation is not reached, but it does not state that the ToolError gives the registered choices.
- t43 · agent run 1: The answer correctly explains that the weather call depends on the coordinates. But it does not say that independent-call results should be returned in one user message with each result matched by its tool_use_id.
- t15 · agent run 2: The answer correctly says the loop returns the final text without executing a tool, but it omits that the assistant response is appended first.
- t43 · agent run 2: The answer correctly explains that the Seattle weather call depends on the coordinates call. But it does not say that independent tool results are returned in one user message, with each result matched to its tool_use_id.
- t15 · agent run 3: The answer correctly says the loop returns the final text without running a tool, but it does not mention that the loop first appends the assistant response.
- t23 · agent run 3: The answer correctly says the returned error flag is true and that the traceback is logged, but it does not specify that the traceback goes to the application logs via `log.exception`, as required by the rubric.
- t43 · agent run 3: The answer correctly explains that the weather call depends on the coordinates. But it does not state that independent-call results are returned in one user message, with each result matched to its tool_use_id; saying to send back every result does not cover those requirements.

## Diagnosis: the daily-check agent

10 tasks

| System | Accuracy | Avg turns | Avg latency | p95 latency | Avg tokens | Avg questions |
|---|---|---|---|---|---|---|
| Baseline (2 fixed questions per unit + one model call) | 70% | 1.00 | 2.3 s | 4.2 s | 1,430 | 3.9 |
| Agent, run 1 | 100% | 6.10 | 10.3 s | 12.7 s | 11,367 | 4.1 |
| Agent, run 2 | 100% | 6.10 | 10.6 s | 13.7 s | 11,376 | 4.1 |
| Agent, run 3 | 100% | 6.20 | 11.0 s | 16.1 s | 11,669 | 4.1 |
| Agent, all 3 runs | 100% | 6.13 | 10.6 s | 13.7 s | 11,471 | 4.1 |

| pass@3 | pass^3 | Tasks whose outcome changed across runs |
|---|---|---|
| 100% | 100% | none |

| Category | Tasks | Baseline | Agent (all runs) |
|---|---|---|---|
| diagnosis | 10 | 70% | 100% |

Failed runs:

- d05 · baseline run 1: no accepted conclusion; fallback {'primary_gap': 'unit-3', 'status': 'uncertain', 'next_step': 'review_today'}
- d06 · baseline run 1: no accepted conclusion; fallback {'primary_gap': 'unit-3', 'status': 'uncertain', 'next_step': 'review_today'}
- d10 · baseline run 1: no accepted conclusion; fallback {'primary_gap': 'none', 'status': 'uncertain', 'next_step': 'continue'}
