# Whip-it — working-discipline contract

These rules are binding in every session of this project. Each one
exists because it has been violated before. Re-read this file after
every compaction and whenever the user invokes `/whip-it`, then run
the self-check at the bottom and correct course.

## 1. TDD-first — RED before any production code

TDD is a three-stage loop, and the order is the point:

1. **RED** — write the test for the next small behaviour FIRST, before
   any production code. Run it. Watch it fail, and fail for the right
   reason — an assertion failure on the missing behaviour, not an
   import error or a typo. Paste the failing output into your reply:
   that output is the evidence the RED stage happened.
2. **GREEN** — write the minimum production code that makes that one
   test pass. Run the test again; paste the passing output.
3. **REFACTOR** — clean up only while tests are green, re-running them
   after each change.

Writing production code first and back-filling a test afterwards is
not TDD. A test that has never been seen to fail proves nothing — it
may pass vacuously, assert the wrong thing, or mirror the
implementation instead of the behaviour. If you catch yourself with
production code and no failing test: stop, set the code aside
(`git stash` or comment it out), write the test, run it RED, then
bring the code back.

Never delete, skip, or weaken a failing test to reach green. Report
the failure and why it happens instead.

## 2. File search — native Unix tools, not built-in Grep/Glob

On this workstation the built-in Grep / Glob / List tools return false
"file not found" results. An empty result from them is NOT evidence
that a file or symbol is absent.

- Use the shell tool with native Unix commands instead:
  `grep -rn "pattern" <dir>`, `find <dir> -name "*.py"`, `ls <dir>`.
- Never conclude "X does not exist" without quoting the Unix command
  you ran and its output.

## 3. Recorded agreements outrank general convention

The user has made project-specific working agreements for this
internal environment — for example how local git branches are named,
created, and switched. They are recorded in `MEMORY.md` and in
`personalities/<active>/memory/understanding/`. They are binding:

- Never substitute a general best practice for a recorded agreement.
- Before any git branch or workflow action, check the recorded
  agreement first.
- If you cannot find an agreement you believe exists, ask the user —
  do not guess and do not improvise a replacement.

## 4. After every compaction — re-anchor before continuing

Compaction erases working context, including the agreements above.
Immediately after any compaction (and whenever you notice you lack
context you should have), and BEFORE continuing the task:

1. Re-read `AGENTS.md`.
2. Re-read `MEMORY.md` (project map + default-personality callout).
3. Re-read `personalities/<active>/ROLE.md`.
4. Re-read `personalities/<active>/memory/understanding/_index.md`,
   then the L2 files relevant to the task in flight.

## 5. No shortcuts

- **Full scope.** Run the scope you were asked to run — the whole test
  suite, the whole file list, every target. Narrowing scope is allowed
  only if you state the narrowing explicitly and the user agrees.
- **Whole files.** Read files in full. Partial reads are only for
  files too large to read at once — and then say which lines you read.
- **Per-item reporting.** Asked to analyse N items, report all N, one
  by one. No sampling, no "the rest are similar".
- **Real output.** Every claim — "tests pass", "not found", "build
  works" — must quote the actual command output. A claim without
  output is unverified.

## 6. Honesty over fluency

- A tool error is a result. Report the exact error text; never paper
  over it or invent plausible content for a file you failed to read.
- This deployment is air-gapped. Never claim to have checked online
  documentation; use the in-repo references
  (`.opencode/reference/opencode/`, the bundled SMAK skill).
- If you are blocked, say so and say why. Stopping silently — or
  declaring success early — is worse than asking.

## Self-check on /whip-it

When the user invokes `/whip-it`, answer each question in one short
block, honestly:

1. Did I write any production code this session without a RED test
   run first?
2. Did I conclude anything was "not found" from a built-in Grep/Glob
   result alone?
3. Am I following the recorded git-branch agreement, or a convention
   I assumed?
4. Have I re-read `AGENTS.md`, `MEMORY.md`, and the active ROLE.md
   since the last compaction?
5. Did I narrow any scope, skim any file, or claim any result without
   quoting output?

Report every violation found, fix course, then continue the task that
was in flight.
