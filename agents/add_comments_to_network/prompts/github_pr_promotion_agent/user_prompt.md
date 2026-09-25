Read AGENTS.md in your working directory first.

Check whether it contains any entry with status proposed-awaiting-response.

If it does, take the OLDEST such entry and follow up on it exactly as Step 4 of your system prompt describes: open the recorded issue URL with your browser tools, read the page, and classify the maintainer's response (positive / declined / no reply yet under 10 days / no reply 10+ days). Act on whichever case applies.

If there is no pending proposal, look for exactly ONE new candidate: a small, actively-maintained, individually-run AI agent project (roughly 15-600 GitHub stars, recently active, not archived, not on your blocklist) where Adam Network would solve a real, specific gap in that project — not just "any AI project could use this." Use search_agent_repositories and inspect_agent_repository to find and verify it against your Good-Fit Checklist.

If you find a genuine fit, open a short, plain GitHub Issue asking whether a small, optional integration PR would be welcome. Do NOT open a Pull Request in this run — that only happens in Step 5, after a maintainer has already said yes in a previous run.

Only build and submit an actual Pull Request when Step 5's condition is met.

Finish by updating AGENTS.md with exactly one new line reflecting what you did this run, using one of the exact status values from your system prompt: proposed-awaiting-response, declined-do-not-recontact, no-response-closing, or pr-submitted. If you rejected every candidate this run (no repo passed the Good-Fit Checklist), do not add a line at all.
