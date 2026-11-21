
### qa baseline

| Metric | A (before) | B (after) |
|---|---|---|
| accuracy | 82% | 82% |
| turns | 1.00 | 1.00 |
| avg latency | 2.2 s | 2.1 s |
| p95 latency | 3.8 s | 3.2 s |
| tokens | 1,319 | 1,303 |
| gave up (failed) | 0 | 0 |
| calls > 30 s | 0 | 0 |
| slowest call | 7 s | 5 s |

### qa agent

| Metric | A (before) | B (after) |
|---|---|---|
| accuracy | 90% | 95% |
| pass@3 | 98% | 96% |
| pass^3 | 82% | 92% |
| turns | 3.33 | 2.63 |
| avg latency | 5.9 s | 4.0 s |
| p95 latency | 12.9 s | 7.0 s |
| tokens | 7,034 | 5,100 |
| gave up (failed) | 9 | 0 |
| calls > 30 s | 0 | 0 |
| slowest call | 14 s | 5 s |

### diagnosis baseline

| Metric | A (before) | B (after) |
|---|---|---|
| accuracy | 50% | 70% |
| turns | 1.00 | 1.00 |
| avg latency | 2.9 s | 2.3 s |
| p95 latency | 6.2 s | 4.2 s |
| tokens | 1,506 | 1,430 |
| gave up (failed) | 0 | 0 |
| calls > 30 s | 0 | 0 |
| slowest call | 6 s | 4 s |

### diagnosis agent

| Metric | A (before) | B (after) |
|---|---|---|
| accuracy | 100% | 100% |
| pass@3 | 100% | 100% |
| pass^3 | 100% | 100% |
| turns | 6.17 | 6.13 |
| avg latency | 10.3 s | 10.6 s |
| p95 latency | 13.4 s | 13.7 s |
| tokens | 11,542 | 11,471 |
| gave up (failed) | 0 | 0 |
| calls > 30 s | 0 | 0 |
| slowest call | 5 s | 5 s |
