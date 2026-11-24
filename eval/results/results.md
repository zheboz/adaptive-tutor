# Evaluation results

Model `gpt-6-luna` · agent runs: 3 · baseline runs: 3

## PDF question answering: Ask the tutor

190 tasks

| System | Accuracy | Avg turns | Avg latency | p95 latency | Avg tokens |
|---|---|---|---|---|---|
| Baseline (one-shot RAG), run 1 | 81% | 1.00 | 2.1 s | 3.4 s | 1,427 |
| Baseline (one-shot RAG), run 2 | 81% | 1.00 | 2.2 s | 3.5 s | 1,427 |
| Baseline (one-shot RAG), run 3 | 82% | 1.00 | 2.2 s | 4.2 s | 1,422 |
| Baseline (one-shot RAG), all 3 runs | 81% | 1.00 | 2.2 s | 3.5 s | 1,425 |
| Agent, run 1 | 84% | 1.28 | 2.5 s | 5.6 s | 3,275 |
| Agent, run 2 | 85% | 1.24 | 2.5 s | 5.4 s | 3,128 |
| Agent, run 3 | 86% | 1.32 | 2.7 s | 6.0 s | 3,366 |
| Agent, all 3 runs | 85% | 1.28 | 2.6 s | 5.7 s | 3,257 |

| System | pass@k | pass^k | Tasks whose outcome changed across runs |
|---|---|---|---|
| Baseline | 87% | 75% | t22 (✓✓✗), t23 (✓✗✗), t24 (✓✗✗), t45 (✓✗✗), t57 (✓✗✓), t61 (✗✓✓), t74 (✓✗✓), t77 (✗✗✓), t78 (✗✓✗), t94 (✗✓✓), t99 (✓✗✗), t109 (✗✓✓), t113 (✗✗✓), t115 (✓✗✓), t117 (✓✗✗), t129 (✗✓✓), t131 (✗✗✓), t142 (✓✗✗), t144 (✗✗✓), t148 (✗✓✓), t164 (✗✓✓), t170 (✓✓✗), t177 (✗✓✓), t187 (✗✓✗) |
| Agent | 90% | 79% | t19 (✓✗✓), t44 (✗✗✓), t45 (✓✗✗), t57 (✓✗✓), t65 (✗✓✓), t78 (✓✗✗), t109 (✗✓✓), t112 (✓✗✓), t113 (✗✓✓), t114 (✗✓✓), t115 (✓✓✗), t117 (✗✓✗), t123 (✗✓✓), t140 (✗✓✗), t142 (✗✓✓), t145 (✗✓✗), t148 (✗✗✓), t150 (✓✗✗), t180 (✓✗✓), t190 (✗✗✓) |

k = 3 for the agent and 3 for the baseline.

| Category | Tasks | Baseline (all runs) | Agent (all runs) |
|---|---|---|---|
| direct | 44 | 95% | 94% |
| application | 44 | 82% | 92% |
| paraphrase | 44 | 80% | 83% |
| cross_page | 33 | 54% | 62% |
| edge_case | 15 | 91% | 89% |
| unanswerable | 10 | 100% | 93% |

| Document | Tasks | Baseline (all runs) | Agent (all runs) |
|---|---|---|---|
| week_2.pdf | 50 | 77% | 91% |
| week_3.pdf | 35 | 90% | 93% |
| Week 4 Agentic RAG & Context.pdf | 35 | 83% | 88% |
| Week 5 Agent Memory.pdf | 35 | 78% | 73% |
| Week 6 Evaluation & Observability.pdf | 35 | 78% | 77% |

Failed runs:

- t15 · baseline run 1: The answer correctly says it returns the first text block without running a tool, but it omits the rubric’s required step that the loop appends the assistant response first.
- t16 · baseline run 1: kind=declined: The passages describe the loop and its normal return when the model stops requesting tools, but they don’t specify what it returns after all MAX_STEPS iterations request tools.
- t21 · baseline run 1: kind=declined: The passages cover the Seattle weather agent’s dependent tool calls, not a three-city comparison with grouped lookups.
- t29 · baseline run 1: kind=declined: The passages cover sending the whole transcript each turn, tool selection, and retrying failures, but they do not say what to do with older messages when the conversation exceeds the model’s window.
- t34 · baseline run 1: kind=declined: The passages cover tool design, selection, and error recovery, but they do not discuss consolidating similar search tools.
- t40 · baseline run 1: kind=declined: The passages cover retrying HTTP 503 errors with backoff, but do not explain which layer handles an invalid `units='F'` request or what should happen next for it.
- t42 · baseline run 1: The answer correctly says the description comes from the function’s docstring and mentions the tool’s name and schema. But it omits that the model also reads the system prompt, conversation, and prior tool results.
- t43 · baseline run 1: The answer correctly explains that the weather call depends on the coordinates. It says the parallel calls are run together and their results returned, but it does not state that the results are returned in one user message with each matched by tool_use_id.
- t44 · baseline run 1: It correctly gives three attempts and two sleeps, and identifies the model as the layer that takes over. However, it does not say that retries are first handled in code or that the final ToolError is reported to the model's recovery layer.
- t61 · baseline run 1: It correctly identifies the Replanner and says it revises the plan when a step fails, but it does not state that it runs only if needed.
- t75 · baseline run 1: The answer contradicts both rubric points: it says the ReAct trace has rain in Portland and that neither city works, whereas the trace's Portland observation is 18 degrees and clear. It also omits the chain-of-thought example's 17-degree rainy forecast.
- t77 · baseline run 1: The answer identifies that the up-front plan cannot know about the two Portlands until step 2 runs, and describes replanning to choose Portland, Oregon. However, it does not say to record the assumption in plan.md, as the rubric requires.
- t78 · baseline run 1: The answer covers the think tool’s purpose and its use in 3 of 9 turns, and names interleaved thinking as the recommendation. It omits the rubric’s detail that the same task took 6 turns with interleaved thinking.
- t91 · baseline run 1: kind=declined: The passages list the Week 4 lab’s submission requirements, but they do not say when it is due.
- t94 · baseline run 1: The once-per-document steps are covered, and the answer describes retrieval, prompt augmentation, and generation with citations. However, it does not specify that retrieval searches for the top-k nearest chunks.
- t101 · baseline run 1: The answer covers staleness and dating memories, replayed harmful instructions, and user control over private data. But it omits the advice to prefer fresh sources, and does not specify that poisoned instructions may be hidden in a web page and replayed every session.
- t109 · baseline run 1: The answer correctly describes delegating to a sub-agent with its own context, returning a short sourced answer, and the increased total token cost. However, it omits the expected scale of the returned answer (about 60 tokens here, typically 1–2K), so it does not satisfy every rubric point.
- t113 · baseline run 1: The answer gives the correct stale-context amount and the reduction from 24,000 to 6,040 tokens, but it does not state that clearing keeps only the newest tool result in full.
- t114 · baseline run 1: The no-results behavior is described correctly, but the answer does not include Seattle as one of the city enum choices, which the rubric requires.
- t129 · baseline run 1: The answer correctly identifies the memory store as persistent across sessions and says the model reads only the context window. However, it omits the weights box and its role (what was learned until retraining), required by the first rubric point.
- t131 · baseline run 1: The answer covers the three time scopes, storage formats, and decision-making options, but it omits that the learned policy is RL-trained, as required by the rubric.
- t136 · baseline run 1: The answer correctly says the system prompt, goal, and hard rules are pinned verbatim and explains that this protects them from summarization drift. However, it omits notes.md, which the rubric explicitly requires.
- t140 · baseline run 1: The answer correctly says to save only user-stated preferences, confirm tool-derived information, and treat tool text as data rather than instruction. But it does not say to tag sources, as required by the rubric.
- t144 · baseline run 1: The answer covers the memory fields, keyword search, and LLM decision-making via tools with plain-English system-prompt rules, but it does not specify the required filename, memories.json.
- t145 · baseline run 1: kind=declined: The passage lists the memories read and written in session 3, but it does not show how the agent’s answer used them.
- t147 · baseline run 1: The attack chain is described correctly, and the answer includes confirming outside facts before saving. However, it omits the rubric’s additional defense habits: tagging sources and logging every write.
- t148 · baseline run 1: The answer covers short-term memory’s limits, per-call cost, session end, and maintenance, and it covers long-term storage and retrieval. But it does not state that short-term memory rots or degrades as the context accumulates, which is an explicit rubric point.
- t149 · baseline run 1: The answer gives the 75% threshold and mentions using a small model, but it does not explicitly say compaction costs an extra model call or that it cuts at a turn boundary.
- t163 · baseline run 1: The latency and max-turns thresholds are correct, but the answer omits that the tool error rate threshold applies per tool, per version.
- t164 · baseline run 1: The answer covers silent fluent errors, nonrepresentative test questions, and changes breaking other cases. But it does not state that results can differ between runs; mentioning repeated runs as a measurement practice does not explicitly convey that variability.
- t167 · baseline run 1: The answer gives a different grading scheme (outcome, trajectory, step) and does not mention coding graders, an LLM judge with a rubric, or humans labeling about 50 cases to calibrate the judge.
- t169 · baseline run 1: The answer correctly covers saturation and contamination, but it does not include the specific scaffolding caveat that the same model’s SWE-bench score can swing about 25 points with a different harness.
- t177 · baseline run 1: The answer correctly favors Y, says the 2-point gap is within noise, and notes X uses four times the tokens. However, it omits the rubric’s stated one-standard-error estimate of about 2.6 points.
- t180 · baseline run 1: The answer correctly explains the policy violation, database/goal-state mismatch, and pass^k values. However, it does not state that a satisfaction-based judge would pass the task despite the underlying failure, as the rubric requires.
- t182 · baseline run 1: The answer includes the 14.2-second run and the three search_venues calls taking 8.9 seconds with timeouts, but it omits that 63% of the time was one tool retrying on timeouts rather than the model.
- t184 · baseline run 1: The answer correctly names all four grader types and the four standard rubric parts, but it omits that passing requires yes on all four parts plus the task's own items.
- t187 · baseline run 1: The answer correctly distinguishes pass@k from consistency and says pass^k measures success on all k reruns. However, it does not explicitly state that pass@k goes up with k or that pass^k goes down.
- t15 · baseline run 2: The answer correctly says it returns the first text block without running tools, but omits that the loop first appends the assistant response.
- t16 · baseline run 2: kind=declined: The passages cover the tool loop and returning a response when the model is done, but not what `run_agent` returns after all `MAX_STEPS` iterations are used.
- t21 · baseline run 2: kind=declined: The passages cover a Seattle weather lookup and a Seattle–Tokyo comparison, but not how grouping three-city lookups affects model calls or rounds.
- t23 · baseline run 2: It correctly says `is_error` is `True` and that the full traceback goes to the logs, but it does not specify that this happens via `log.exception`, as required by the rubric.
- t24 · baseline run 2: It correctly says the 404 is not retryable and identifies `r.raise_for_status()`, but it does not explicitly state that this call raises an HTTP error.
- t29 · baseline run 2: kind=declined: The passages cover sending the whole transcript each turn, tool selection, and retrying failures, but they do not explain what to do with older messages when the conversation exceeds the model’s window.
- t34 · baseline run 2: kind=declined: The passages cover tool anatomy, selection, and error recovery, but they do not discuss consolidating similar search tools.
- t40 · baseline run 2: kind=declined: The passages cover retrying HTTP 503 responses with backoff and handing off after the last try, but they do not explain how a request with units='F' is handled or what should happen next in that case.
- t42 · baseline run 2: The answer correctly says the tool description comes from the registered function’s docstring and mentions the tool name and schema. However, it omits that the model also reads the system prompt, conversation, and prior tool results; its claim that the model sees only the name, description, and schema contradicts that rubric point.
- t43 · baseline run 2: The answer correctly explains that Seattle weather depends on the coordinates and cannot start at the same time. But it does not state that independent tool results are returned together in one user message, with each result matched by tool_use_id.
- t44 · baseline run 2: It correctly gives three attempts and two sleeps, and identifies the model as the final recovery layer. However, it does not say that retries are first handled in code or that a final ToolError is reported to that layer.
- t45 · baseline run 2: The corrected coordinates are stated correctly, but the answer identifies the maximum of 90 instead of the schema’s latitude minimum of −90 as the constraint that rules out −122.33.
- t57 · baseline run 2: The answer gives the date and all three measures, but omits that Step 1 was due before class.
- t74 · baseline run 2: The answer covers the low-effort behavior and the high-effort choice, parallel forecasts, wind, and hike suggestion. But it says Oregon was treated as an assumption without saying that the assumption was recorded, which is required by the rubric.
- t75 · baseline run 2: The answer does not identify the differing illustrative weather: it omits that the chain-of-thought example has Portland at 17 degrees with rain and the ReAct observations have Portland at 18 degrees and clear. It instead says the passages do not show a ReAct trace recommending Portland for a picnic, contradicting the rubric’s ReAct point.
- t77 · baseline run 2: The answer correctly identifies that the up-front plan is written before the evidence, so step 2 cannot know about the two Portlands. It also says the plan clarifies Portland as Oregon, but it omits the required detail that the replanner notes this assumption in plan.md.
- t91 · baseline run 2: kind=declined: The passages list the Week 4 lab submissions—the notebook, filled-in table, and three sentences about when agentic retrieval was worth its cost—but do not give the due date.
- t99 · baseline run 2: The answer covers the agent strategy, but it does not explicitly state that the same passage is used worse in the middle than at the start or end.
- t101 · baseline run 2: The answer covers stale facts and user control over private stored information. However, it does not specify that a poisoned instruction may be hidden in a web page and replayed every session.
- t113 · baseline run 2: The answer gives the stale-token count and the reduction from 24,000 to 6,040 tokens, but it does not say that only the newest result is kept in full.
- t114 · baseline run 2: The answer correctly describes the no-results note and distinguishes the two Portlands, but it omits Seattle from the city enum required by the rubric.
- t115 · baseline run 2: The first mapping is correct: “Grade and correct” scores retrieved chunks and can fall back to web search. But “Decide to retrieve” in Self-RAG decides whether to retrieve; checking whether a passage supports the answer is a separate evaluation. The answer conflates these moves.
- t117 · baseline run 2: The answer correctly says context rot is a gradual slope rather than a cliff and that each extra token makes relevant information harder to find. It does not explicitly address that this happens even on simple tasks.
- t131 · baseline run 2: The answer covers all three design questions, but it only says “learned policy” and does not specify the rubric’s RL-trained policy.
- t136 · baseline run 2: The answer includes the system prompt, goal, and hard rules verbatim, and explains that pinning them prevents loss or drift during trimming or summarization. But it omits notes.md, which the rubric explicitly requires.
- t140 · baseline run 2: The answer says to save only user-stated information, confirm tool-derived information, and treat the listing as data rather than an instruction. It does not mention tagging sources, so it misses a rubric point.
- t142 · baseline run 2: The answer captures both ideas, but it does not specify that classic RAG returns its top 5 chunks, as required by the rubric.
- t144 · baseline run 2: The answer covers the memory fields and the LLM's save/search tools and plain-English system-prompt rules, but it does not specify the filename memories.json or that memories are searched by keyword.
- t145 · baseline run 2: kind=declined: The passage identifies which memories were read and written in session 3, but it does not show the agent’s answer or how it used those memories.
- t147 · baseline run 2: The answer accurately describes the attack chain and says to confirm outside facts before saving, but it omits the required habits of tagging sources and logging every write.
- t149 · baseline run 2: It correctly gives the 75% threshold and mentions using a small model, but it does not state that compaction costs an extra model call or that it cuts at a turn boundary.
- t163 · baseline run 2: The p95 latency and max-turns thresholds are correct, but the tool error threshold omits that it is measured per tool, per version.
- t167 · baseline run 2: The answer gives an outcome → trajectory → step hierarchy, but omits the recommended sequence of code graders, an LLM judge for the remaining cases, and human labeling of about 50 cases to calibrate the judge.
- t169 · baseline run 2: The answer covers saturation, contamination, and the effect of different harnesses, but it omits the rubric’s specific caveat that the same model’s SWE-bench score can swing about 25 points.
- t180 · baseline run 2: The answer correctly explains the policy violation and database-goal mismatch, and gives pass^k values of 0.420 at pass^1 and 0.200 at pass^4. But it does not explicitly state that a satisfaction judge would pass the happy-user outcome, as the rubric requires.
- t182 · baseline run 2: The answer correctly states that the 14.2-second trace included 8.9 seconds for three venue searches with timeouts. It does not say that 63% of the time was one tool retrying on timeouts rather than the model.
- t184 · baseline run 2: The answer names all four grader types but does not explain their required behavior: exact checks for an expected answer, tool matches the first call’s name and arguments, rubric uses an LLM judge per criterion, and unanswerable declines without inventing anything. It correctly gives the four standard open-answer rubric parts and the pass condition.
- t15 · baseline run 3: The answer correctly says it returns resp.content[0].text without executing a tool, but it omits that the loop first appends the assistant response.
- t16 · baseline run 3: The answer says run_agent returns None, but the rubric requires the step-limit message: “Stopped: step limit reached.”
- t21 · baseline run 3: kind=declined: The passages cover weather lookups for Seattle and Tokyo, but not a three-city comparison or grouping those lookups into rounds.
- t22 · baseline run 3: The answer identifies the `description` field, but it is incomplete and does not state that the `TOOLS` list derives the description from `fn.__doc__`.
- t23 · baseline run 3: It correctly says `is_error` is `True` and that the traceback goes to logs, but it does not specify that it is logged via `log.exception`, as required by the rubric.
- t24 · baseline run 3: It correctly says 404 is not retryable and that `r.raise_for_status()` is called, but it does not state the rubric’s required outcome: that the call raises an HTTP error.
- t29 · baseline run 3: kind=declined: The passages cover the agent loop, tool selection, and retry behavior, but not what to do with older messages when the conversation record exceeds the model’s window.
- t34 · baseline run 3: kind=declined: The passages cover tool contracts, tool selection, and handling errors and retries, but they do not describe consolidating similar search tools.
- t40 · baseline run 3: kind=declined: The passages cover tool contracts and retrying transient HTTP errors, but not how a request with units='F' is handled or what should happen next for that request.
- t42 · baseline run 3: It correctly says the description comes from the registered function’s docstring and mentions each tool’s name and schema. However, it omits that the model reads the system prompt, conversation, and prior tool results, and its claim that it sees “only” the tool name, description, and schema contradicts that rubric point.
- t43 · baseline run 3: It correctly explains that the Seattle weather call depends on the coordinates, so it cannot start at the same time. But it does not state that independent-call results are returned together in one user message, with each result matched to its tool_use_id.
- t44 · baseline run 3: The answer correctly gives three attempts and two sleeps, and identifies the model as the final recovery layer. It does not state that the retries are handled in code and that the final ToolError is reported to that layer.
- t45 · baseline run 3: The corrected coordinates are stated correctly, but the answer incorrectly identifies the latitude maximum as the constraint. The rubric requires the latitude minimum of −90, which −122.33 falls below.
- t75 · baseline run 3: The answer correctly describes the chain-of-thought example as having rainy Portland, but it contradicts the ReAct point: the trace says Portland is 18°C and clear, so it works. The answer instead says ReAct missed the rain condition.
- t78 · baseline run 3: The answer correctly explains that the think tool adds no new information, gives the count of 3 out of 9 turns, and names interleaved thinking as the recommendation. It omits that the same task was completed in 6 turns, so it does not satisfy every rubric point.
- t91 · baseline run 3: kind=declined: The passages list the lab submissions—a notebook, a filled-in table, and three sentences about when agentic retrieval was worth its cost—but do not give the Week 4 lab’s due date.
- t99 · baseline run 3: The answer covers the middle-position disadvantage but does not explicitly say that the same passage is used better at the start or end. It does satisfy the agent guidance to keep the goal near the end, retrieve few chunks, and put the best chunk first.
- t101 · baseline run 3: The answer mentions that memories can become stale, be poisoned, and contain private information, but it omits the rubric’s key safeguards and specifics: dating facts and preferring fresh sources; hidden web-page instructions being saved and replayed each session; and letting users see, correct, and delete stored information.
- t114 · baseline run 3: The answer correctly describes the no-results note and distinguishes the two Portlands, but it omits Seattle from the city enum. The rubric requires Seattle, Portland, OR, and Portland, ME.
- t117 · baseline run 3: The answer correctly says context rot is gradual rather than a hard cliff and that each extra token makes relevant information harder to find, but it omits that this applies even on simple tasks.
- t136 · baseline run 3: The answer correctly identifies the system prompt, goal, and hard rules and explains protection against summarization drift, but it omits notes.md, which the rubric explicitly requires.
- t140 · baseline run 3: The answer correctly says to save only user-stated information, confirm tool-derived information, and treat the event listing as data rather than an instruction. However, it does not say to tag sources, as required by the rubric.
- t142 · baseline run 3: The answer covers the empty-search evidence and says classic RAG may return irrelevant results and fill gaps from training, but it does not state that classic RAG always returns its top 5 chunks.
- t145 · baseline run 3: kind=declined: The passage lists the memories read and written in session 3, but does not include the agent’s response or explain how it used them.
- t147 · baseline run 3: The answer gives the core attack sequence but omits that the inbox is monitored. It also mentions confirming outside facts before saving, but omits tagging sources and logging every write.
- t149 · baseline run 3: The answer correctly places compaction at about 75% of the context budget and says to use a small model, but it omits that compaction costs an extra model call and should cut at a turn boundary.
- t163 · baseline run 3: The answer gives all three numeric thresholds, but it omits that the tool error rate threshold is evaluated per tool, per version.
- t167 · baseline run 3: The answer describes outcome, trajectory, and step grading, but the rubric requires code-based checks where possible, an LLM judge with a rubric for the rest, and roughly 50 human-labeled cases to calibrate the judge. It does not mention those points.
- t169 · baseline run 3: The answer correctly describes saturation and contamination, and mentions scaffolding effects, but it omits the rubric’s specific caveat that the same model’s SWE-bench score can swing about 25 points with a different harness.
- t170 · baseline run 3: The answer correctly describes a span as one step with name, start time, duration, inputs, and outputs, and a trace as the tree of spans for one request. But it omits the rubric-required tokens and errors as span details.
- t180 · baseline run 3: The answer covers the policy violation, incorrect database state, and user happiness, but it does not say that a satisfaction judge would pass the task. It correctly gives the pass^k figures.
- t182 · baseline run 3: The answer correctly states that the trace took 14.2 seconds and that three `search_venues` calls took 8.9 seconds with timeouts. It omits that 63% of the time was one tool retrying on timeouts rather than the model.
- t184 · baseline run 3: The answer lists the four grader types and the four standard rubric parts, but omits the required descriptions of the grader types and the rule that passing requires yes on all four rubric parts plus the task’s own items.
- t187 · baseline run 3: The answer correctly says pass@k concerns at least one success and defines pass^k as success on all k reruns, but it does not state the rubric’s required point that pass^k goes down as k increases.
- t15 · agent run 1: The answer correctly says it returns the final text without running tools or starting another iteration, but it does not say that the loop first appends the assistant response.
- t42 · agent run 1: The answer correctly says the description comes from the decorated function’s docstring, but it omits that the model also reads the system prompt, conversation, and prior tool results when choosing whether to call a tool.
- t43 · agent run 1: The answer correctly explains that the Seattle weather call depends on the coordinates call. However, it does not say that independent-call results should be returned in one user message with each result matched by tool_use_id.
- t44 · agent run 1: It correctly states three attempts and two sleeps, and that the model takes over after the final failure. But it does not specify that retries are handled in code or that the final ToolError is reported to the model’s recovery layer.
- t65 · agent run 1: The answer covers that trained thinking is learned, can be longer and self-checking, and that the model chooses how much to think. But it does not say that trained thinking is often summarized, as required by the rubric.
- t77 · agent run 1: The answer correctly identifies that step 2 cannot know about the two Portlands before it runs and says the plan is updated to use Portland, Oregon. But it omits the required detail that the assumption is noted in plan.md.
- t91 · agent run 1: The answer says the due date is not stated rather than Wednesday, October 28, end of day, and lists a notebook, a filled-in table, and three explanatory sentences instead of the changed code, the test for part (a), and the token table for part (b).
- t101 · agent run 1: The answer covers stale information and recommends dating memories, but it does not say to prefer fresh sources. It satisfies the poisoned-memory and user-control points.
- t109 · agent run 1: The answer correctly says to delegate the search to a sub-agent with its own context, which returns a concise answer and sources, and it notes that total token use goes up and can be worth it for big searches. However, it omits the rubric’s specific estimate of about 60 tokens for the short answer in this example.
- t113 · agent run 1: The answer gives the 18K stale figure and correctly says clearing reduces results from 24,000 to 6,040 tokens, keeping the newest in full. But it omits that the 18K stale old tool results are out of 31K tokens, so it does not satisfy the first rubric point completely.
- t114 · agent run 1: It correctly says the two Portlands are explicit choices and gives the no-results note, but it does not state that Seattle is also included in the city enum.
- t117 · agent run 1: The answer correctly says context rot is gradual rather than a sudden cliff, but it does not state that each extra token makes finding the relevant information harder even on simple tasks.
- t123 · agent run 1: The answer gives the stated accuracy gain and correctly reports the latency and token reductions, but it does not specify that the +26% LOCOMO accuracy result is LLM-judged, as required by the rubric.
- t129 · agent run 1: The answer correctly identifies the memory store and context window, and says the model only directly reads the context window. But it omits the weights box and what it represents, so it does not satisfy the full first rubric point.
- t131 · agent run 1: The answer covers all three design questions and their examples, but it omits that the learned policy is RL-trained, as specified in the rubric.
- t136 · agent run 1: The answer correctly says the system prompt, goal, and hard rules are pinned verbatim, and explains protection against summarization drift. However, it omits notes.md, which the rubric explicitly requires.
- t140 · agent run 1: The answer correctly says to save only user-stated preferences and confirm information inferred from tool output. It also treats the listing as data rather than an instruction, but it does not say to tag sources, as the rubric requires.
- t142 · agent run 1: The answer explains that classic RAG can return irrelevant results and fill gaps from training, but it does not state the rubric’s specific point that classic RAG always returns its top five chunks, relevant or not. The agentic RAG point is satisfied.
- t144 · agent run 1: The answer covers keyword search and the LLM deciding through memory tools, with save rules in the system prompt. But it does not specify the filename `memories.json` or the per-memory fields `id`, `text`, `kind`, `source`, and `date`, so it misses the first rubric point.
- t145 · agent run 1: The answer covers the memories read and written and says it recommended LongRoPE without re-explaining RoPE and cited a page. But it does not say that the answer explained the paper intuitively, as the rubric requires.
- t147 · agent run 1: The answer accurately describes the false fact being written and later repeated, and gives the confirmation habit, but it omits that the inbox is monitored and does not mention tagging sources. The rubric requires both details.
- t148 · agent run 1: The answer covers short-term memory’s contents, limits, decay, per-call cost, and session-end loss, but omits keeping it trim through clearing, compaction, and notes. It describes long-term memory’s write and read paths, but does not say they are governed by policies.
- t149 · agent run 1: The answer gives the 75% threshold and mentions using a small model, but it does not state that compaction costs an extra model call or that it occurs at a turn boundary.
- t163 · agent run 1: The answer gives all three numeric thresholds, but it omits that the tool error rate threshold is measured per tool, per version.
- t164 · agent run 1: The answer covers silent fluent wrong answers and that a few test questions may miss users’ less common cases, but it does not mention that changes can ripple to other cases.
- t167 · agent run 1: The answer describes outcome, trajectory, and step graders, but does not give the recommended order of code graders, an LLM judge for the rest, and human labels on about 50 cases to calibrate the judge.
- t169 · agent run 1: The answer covers saturation and contamination, and it notes that harnesses can substantially affect scores. However, it omits the specific caveat that the same model's SWE-bench score can swing about 25 points with a different harness.
- t182 · agent run 1: The answer gives the 14.2-second run and 8.9 seconds across three timed-out `search_venues` calls, but it omits that this was one tool retrying on timeouts and accounted for 63% of the time rather than the model.
- t184 · agent run 1: It names all four grader types and accurately gives the four open-answer rubric parts and pass condition, but it does not specify what the grader types mean: exact checks for the expected answer, tool checks the first call's name and arguments, rubric uses an LLM judge per criterion, and unanswerable requires declining without inventing anything.
- t187 · agent run 1: The answer correctly explains that pass@k concerns at least one success and that pass^k requires success on all k reruns. However, it never states that pass^k goes down as k increases, as the rubric requires.
- t190 · agent run 1: kind=answer
- t15 · agent run 2: The answer correctly says the function returns the final text without running a tool, but it omits the required step of appending the assistant response first.
- t19 · agent run 2: The answer correctly says an unknown tool raises ToolError before argument validation, but it does not say that the error gives the registered choices.
- t42 · agent run 2: The answer correctly says the description comes from the registered function’s docstring, but it omits that the model also reads the system prompt, conversation, and prior tool results when deciding whether to call a tool.
- t43 · agent run 2: The answer correctly explains that the weather call depends on the coordinates, but it does not state that independent tool calls’ results are returned together in one user message, each matched by tool_use_id.
- t44 · agent run 2: The answer correctly gives three attempts and two backoff sleeps. It says the model takes over after retries are exhausted, but does not state that retries are first handled in code or that the final ToolError is reported to the model's recovery layer.
- t45 · agent run 2: The corrected coordinates are right, and the answer mentions the −90 minimum. But it identifies the latitude maximum of 90 as the constraint that rules out −122.33; the relevant constraint is the minimum, since −122.33 is below −90.
- t57 · agent run 2: The answer gives Tuesday, October 27, and the three measures, but omits that it was due before class.
- t77 · agent run 2: The answer correctly identifies that the plan is written before evidence and step 2 cannot know about the two Portlands until it runs. It describes replanning after a surprising observation and choosing Portland, Oregon, but omits the required detail that the assumption is noted in plan.md.
- t78 · agent run 2: The answer correctly explains that the think tool obtains no new information and reports 3 of 9 turns as think calls. It also names interleaved thinking as the native alternative, but omits the rubric’s detail that the same task took 6 turns with interleaved thinking.
- t91 · agent run 2: kind=declined: The Week 4 material lists the three submission items, but it does not give this lab’s due date; it only says to submit the notebook, the filled-in table, and three sentences explaining when agentic retrieval was worth its cost, on Canvas.
- t101 · agent run 2: The answer identifies staleness, replayed harmful instructions, and the need for correction or deletion, but it omits key rubric details: dating stale facts and preferring fresh sources, the hidden-web-page source and replay every session, and users’ ability to see stored information.
- t112 · agent run 2: The answer gives the 56%-to-0% hallucination figure and the 23% bad-search-results figure, but it does not identify the evaluation as ReAct on HotpotQA or specify that the 56% was for chain of thought, as the rubric requires.
- t129 · agent run 2: The answer correctly identifies the memory store as cross-session storage and says the model reads only the context window, but it omits the weights box and what it represents, so it does not satisfy every rubric point.
- t131 · agent run 2: The answer correctly covers the time scope and storage-form questions, and names fixed rules, the LLM, and a learned policy as decision-makers. However, it omits the rubric’s specific qualifier that the learned policy is RL-trained.
- t136 · agent run 2: The answer correctly says the system prompt, goal, and hard rules are pinned verbatim and explains protection against summarization drift. However, it omits notes.md, which the rubric explicitly requires.
- t144 · agent run 2: The answer includes the JSON file and the specified fields, and says the LLM uses memory tools with plain-English write rules in the system prompt. But it does not state that memories are searched by keyword.
- t147 · agent run 2: The chain is otherwise accurate, and the answer gives the requested defense habits, but it says only that the email reaches the agent’s inbox—not that it reaches a monitored inbox, as the rubric requires.
- t148 · agent run 2: The answer covers short-term memory as limited session context that rots, is paid for on each call, and ends with the session, but it omits the rubric’s required ways to keep it trim: clearing, compaction, and notes. It satisfies the long-term memory point.
- t149 · agent run 2: It gives the roughly 75% threshold and mentions using a small model, but it does not state that compaction costs one extra model call or that it cuts at a turn boundary.
- t150 · agent run 2: The four path items are identified, and all supporting boxes are listed, but the path omits the required details: the web app is Streamlit on the cloud, the agent loop is LLM + tools, and the answer includes sources.
- t163 · agent run 2: The answer gives all three numeric thresholds, but it omits that tool error rate is measured per tool, per version.
- t164 · agent run 2: The answer covers silent fluent wrong answers, variation across runs, and the long tail of real user questions. But it does not say that changes can ripple to other cases, so it misses a rubric point.
- t167 · agent run 2: The answer describes outcome, trajectory, and step-level grading, but it does not give the recommended grader order: code where possible, then an LLM judge with a rubric for the rest, calibrated by humans labeling about 50 cases.
- t169 · agent run 2: The answer covers saturation and contamination. It mentions harness-dependent score changes, but omits the rubric’s specific example: the same model’s SWE-bench score can swing about 25 points with a different harness.
- t180 · agent run 2: The answer correctly explains the policy violation, database-state failure, and pass^k figures, but it does not explicitly say that a satisfaction judge would pass the happy-user outcome, as the rubric requires.
- t182 · agent run 2: The answer states that the run took 14.2 seconds and the three search_venues calls took 8.9 seconds and timed out. It does not state that 63% of the time was spent on one tool retrying on timeouts rather than the model.
- t184 · agent run 2: It names all four grader types, but does not give the required descriptions of what each grader checks. The four standard open-answer criteria and the all-four-plus-task-specific-items pass rule are otherwise covered.
- t187 · agent run 2: The answer correctly says pass@k increases and pass^k measures success on all tries, but it does not state that pass^k goes down as k increases.
- t190 · agent run 2: kind=answer
- t15 · agent run 3: The answer correctly says it returns the final text without processing tools or starting another iteration, but it does not mention that the loop first appends the assistant response.
- t42 · agent run 3: The answer correctly says the description comes from the registered function’s docstring. But it omits that the model also reads the system prompt, conversation, and prior tool results; its claim that the model sees “only” the tool details contradicts that rubric point.
- t43 · agent run 3: The answer correctly explains that the weather call depends on the coordinates call. But it does not state that independent results are returned in one user message with each result matched by tool_use_id; saying they are tied to their cities is not sufficient.
- t45 · agent run 3: The corrected coordinates are right, but the answer incorrectly identifies the latitude maximum as the constraint. The schema’s latitude minimum of −90 rules out −122.33 because it is below that minimum.
- t77 · agent run 3: The answer correctly explains that step 2 cannot know about the two Portlands in advance and that replanning can specify Portland, Oregon after the surprising observation. However, it does not mention noting the assumption in plan.md, which the rubric requires.
- t78 · agent run 3: The answer correctly describes the think tool and its use in 3 of 9 turns, but it omits that interleaved thinking completed the same task in 6 turns.
- t91 · agent run 3: The answer denies that the Week 4 lab’s due date is stated and gives a different submission list. The rubric requires Wednesday, October 28, end of day, and the changed code, the test for part (a), and the token table for part (b).
- t101 · agent run 3: The answer covers stale facts and poisoned instructions, and says users can review and delete stored information. However, it does not say users must be able to correct what is stored, so it misses the private-memory rubric point.
- t115 · agent run 3: It correctly names “Grade and correct” for the first move and “Decide to retrieve” for the second, but it does not identify the latter as being from Self-RAG (Asai et al.).
- t117 · agent run 3: The answer correctly says context rot is gradual and that additional tokens make relevant information harder to find, but it does not mention that this happens even on simple tasks.
- t129 · agent run 3: The answer correctly identifies the memory store and context window, but omits the weights and their role in the three-box picture, so it does not satisfy the first rubric point.
- t131 · agent run 3: The answer identifies the three general questions, but omits the rubric’s specific options: memory time scopes, storage formats, and decision-making approaches.
- t136 · agent run 3: The answer includes the system prompt, goal, and hard rules verbatim, and explains that pinning them protects against summarization drift. However, it omits notes.md, which the rubric explicitly requires.
- t140 · agent run 3: The answer correctly says to save only user-stated preferences, confirm tool-derived information, and treat the event listing as data rather than an instruction. It does not mention tagging sources, as required by the rubric.
- t144 · agent run 3: The answer correctly says the LLM decides what to save through memory tools and that the write rules are in plain English in the system prompt. But it omits the required filename (memories.json) and per-memory fields (id, text, kind, source, and date).
- t145 · agent run 3: The answer correctly identifies the memories read and written, and says it recommended LongRoPE without re-explaining RoPE and cited a page. But it does not establish that the explanation was intuitive, as the rubric requires.
- t147 · agent run 3: The answer correctly describes the attack chain and mentions confirming outside facts before saving and logging writes, but it omits the rubric’s requirement to tag sources.
- t149 · agent run 3: It states the roughly 75% budget threshold and that a small model summarizes older turns, but it does not say compaction costs an extra model call or that it cuts at a turn boundary.
- t150 · agent run 3: The supporting boxes are all correct, but the flowchart path is given only in abbreviated form and omits the required details: the user question, Streamlit on the cloud, LLM + tools, and an answer with sources.
- t163 · agent run 3: The thresholds are correct, but the answer omits that the tool error rate is measured per tool, per version.
- t164 · agent run 3: The answer covers fluent, specific wrong answers that produce no error, and notes that runs and prompt changes can affect other cases. However, it does not state that a few demo questions may not reflect users’ questions or that failures often appear in the long tail.
- t167 · agent run 3: The answer correctly gives code checks first and an LLM judge with a rubric for the rest, but it only says humans should label a sample; it does not specify about 50 cases as the rubric requires.
- t169 · agent run 3: The answer correctly covers saturation and contamination, and it notes that scaffolding affects scores. However, it omits the specific caveat that the same model’s SWE-bench score can swing about 25 points with a different harness.
- t182 · agent run 3: The answer states the 14.2-second run and that search_venues ran three times, taking 8.9 seconds with timeouts. But it does not say that 63% of the time was spent on one tool retrying, rather than on the model.
- t184 · agent run 3: It names all four grader types and gives the four standard rubric parts, but it does not explain what each grader type does: exact checks for an expected answer, tool checks the first call’s name and arguments, rubric uses an LLM judge per criterion, and unanswerable requires declining without inventing anything.
- t187 · agent run 3: The answer correctly says pass@k increases with k and defines pass^k as success on all k reruns, but it does not state that pass^k goes down as k increases.

## Diagnosis: the daily-check agent

10 tasks

| System | Accuracy | Avg turns | Avg latency | p95 latency | Avg tokens | Avg questions |
|---|---|---|---|---|---|---|
| Baseline (2 fixed questions per unit + one model call), run 1 | 60% | 1.00 | 2.7 s | 4.6 s | 1,468 | 3.9 |
| Baseline (2 fixed questions per unit + one model call), run 2 | 90% | 1.00 | 2.9 s | 4.9 s | 1,485 | 3.9 |
| Baseline (2 fixed questions per unit + one model call), run 3 | 70% | 1.00 | 2.7 s | 4.5 s | 1,448 | 3.9 |
| Baseline (2 fixed questions per unit + one model call), all 3 runs | 73% | 1.00 | 2.8 s | 4.6 s | 1,467 | 3.9 |
| Agent, run 1 | 100% | 5.20 | 9.5 s | 13.2 s | 10,324 | 4.1 |
| Agent, run 2 | 100% | 5.20 | 9.4 s | 11.9 s | 10,264 | 4.1 |
| Agent, run 3 | 90% | 5.30 | 9.9 s | 13.4 s | 10,537 | 4.1 |
| Agent, all 3 runs | 97% | 5.23 | 9.6 s | 13.2 s | 10,375 | 4.1 |

| System | pass@k | pass^k | Tasks whose outcome changed across runs |
|---|---|---|---|
| Baseline | 90% | 60% | d01 (✗✓✗), d06 (✗✓✗), d09 (✗✓✓) |
| Agent | 100% | 90% | d07 (✓✓✗) |

k = 3 for the agent and 3 for the baseline.

| Category | Tasks | Baseline (all runs) | Agent (all runs) |
|---|---|---|---|
| diagnosis | 10 | 73% | 97% |

Failed runs:

- d01 · baseline run 1: no accepted conclusion; fallback {'primary_gap': 'none', 'status': 'uncertain', 'next_step': 'continue'}
- d05 · baseline run 1: status=uncertain, expected confirmed
- d06 · baseline run 1: no accepted conclusion; fallback {'primary_gap': 'unit-3', 'status': 'uncertain', 'next_step': 'review_today'}
- d09 · baseline run 1: no accepted conclusion; fallback {'primary_gap': 'none', 'status': 'uncertain', 'next_step': 'continue'}
- d05 · baseline run 2: no accepted conclusion; fallback {'primary_gap': 'unit-3', 'status': 'uncertain', 'next_step': 'review_today'}
- d01 · baseline run 3: no accepted conclusion; fallback {'primary_gap': 'none', 'status': 'uncertain', 'next_step': 'continue'}
- d05 · baseline run 3: status=uncertain, expected confirmed
- d06 · baseline run 3: no accepted conclusion; fallback {'primary_gap': 'unit-3', 'status': 'uncertain', 'next_step': 'review_today'}
- d07 · agent run 3: primary_gap=unit-3, expected unit-2; next_step=review_today, expected revisit_earlier
