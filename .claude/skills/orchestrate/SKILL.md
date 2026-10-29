---
name: orchestrate
description: Run the project's issue lifecycle. Picks the next open GitHub issue and drives it through the pm, software-engineer and qa-engineer subagents until QA passes, then opens a PR. Use when asked to work the backlog or process the next issue.
---

# Orchestrator

The main session is the orchestrator. It launches the PM, the engineer and QA
as subagents (`pm`, `software-engineer`, `qa-engineer`). It does not groom,
implement or test itself. Source of truth: `_docs/process.md`.

## Lifecycle

1. Pick the next open issue from the backlog (`gh issue list`)
2. Launch `pm` to groom it
3. Launch `software-engineer` to implement it
4. Launch `qa-engineer` to verify it
5. On FAIL, back to step 3 with the QA comment as input
6. On PASS, create a PR for the issue
7. Repeat until the backlog is empty

## Rules

- Do not skip step 2
- Tasks are GitHub issues, one at a time
- Read the acceptance criteria before starting and before closing
- The engineer does not close the issue
- QA does not fix the code, only outputs PASS or FAIL
- Create the Pull Request only after QA outputs PASS
- Never merge directly into the main branch
- Never commit to main; all work happens on an issue-based branch
- Commit regularly

## Roles

- PM - grooms a task before anyone implements it, follows `_docs/team/pm.md`
- Engineer - implements one groomed task, follows `_docs/team/software-engineer.md`
- QA - checks the result against the acceptance criteria, follows `_docs/team/qa-engineer.md`

## Passing context

Each subagent starts cold. Give it the issue number and, for a re-run of the
engineer, tell it to read the latest `## QA: FAIL` comment on that issue.
Read the verdict from the QA comment on the issue, not from memory.
