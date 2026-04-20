# TASK-XXX__REVIEW_REPORT

## Metadata
- Task: TASK-XXX
- Date: YYYY-MM-DD
- Reviewer: REVIEWER_AGENT
- Task assignee (Code): <name/model>
- Files audited: <list from §13 Change Log of TASK-XXX.md>
- Review result: PASS | PASS_WITH_NOTES | FAIL

## Summary
<!-- 1-3 sentences. What was reviewed, headline result. -->

## Findings

### P0 (blocking — security / production-safety critical)
<!-- 1. [file:line] <finding title>. Evidence: `<grep match or code snippet>`. Fix requirement: <action>. -->

### P1 (blocking — reliability / correctness)
<!-- same structure -->

### P2 (non-blocking — quality / maintainability; follow-up task)
<!-- same structure -->

## Checklist Coverage
| Check | Result |
|-------|--------|
| 2.1 Hardcoded secrets | PASS / FAIL (N findings) |
| 2.2 CORS | PASS / FAIL |
| 2.3 Bare except | PASS / FAIL |
| 2.4 Sync-in-async | PASS / FAIL |
| 2.5 Dead code / docstring honesty | PASS / FAIL |
| 2.6 Secrets in logs | PASS / FAIL |
| 2.7 Injection surface | PASS / FAIL |
| 2.8 Input validation | PASS / FAIL |
| 2.9 Unbounded collections | PASS / FAIL |
| 2.10 Test quality | PASS / FAIL |

## Evidence of Review
<!-- grep commands run (with output):
```
$ rg 'password\s*=\s*["\']' <files>
<output>
```
Files inspected manually: <list>
-->

## Recommendation
<!-- If PASS: task may proceed to PM for DONE verification.
If FAIL: list P0/P1 items that must be fixed before re-review. -->
