# Setup and portability

## Required capabilities

- A local Codex desktop chat with a scheduling tool that returns to the same chat.
  The originating environment used `automation_update(kind="heartbeat")`. Inspect
  the actual tool schema rather than copying a serialized tool call.
- Supported computer use that can read and operate the intended Claude Code UI.
  The originating workflow used `cua_repl`, an accessibility tree, and an existing
  Claude Code conversation in the Claude desktop app. Other Codex installations
  may not include that tool or support native desktop apps.
- Authenticated Claude Code and Codex sessions, the local project, and Python
  3.10+ on macOS/Linux. The controller uses only the Python standard library.
- The host and app remain running and Claude is accessible at scheduled wakeups.

The skill is consumed by **Codex**; Claude receives ordinary prompts and writes
deliverables in the agreed project. No API key, model subscription, MCP server,
daemon, or permission bypass is introduced. Existing usage and plan limits apply.

## Install

Clone/download the repository and place its folder in a skill discovery directory.
For example, from the repository root:

```bash
mkdir -p "$HOME/.agents/skills"
ln -s "$PWD" "$HOME/.agents/skills/claude-codex-loop"
```

Do not replace an existing destination. Some clients use `~/.codex/skills`; use
the directory your client discovers. Reload the chat if required. Installing the
skill does not schedule or authorize a run.

## Bootstrap

Invoke with a concrete request such as:

> Use $claude-codex-loop to supervise the calculation in /work/curve-project and
> the existing Claude Code conversation “Curve calculation,” session SESSION_ID.
> Review every hour and automatically send the next prompt. Stop when the stated
> finite-case certificate is reproduced with exact checks and all blocking review
> objections are resolved. Limit the run to 20 prompts, 48 hours, and 3 consecutive
> reviews without verified progress. Work locally within that project.

Obtain the exact target/session from supported observed UI or supplied metadata.
Do not guess from a similar title. If no stable identifier is exposed, record the
observable unique identity and explain the limitation; block if the intended
conversation cannot be distinguished. A guessed session string is not identity proof.

1. Copy `assets/config.example.json` to a private config and fill in the actual
   values. Each success criterion needs a stable ID and testable description.
   Specify input/code/result/certificate files with `watch` globs, adding binary
   formats when material. Use smaller manifests for large data.
2. Initialize a **new** supervisor directory outside Claude's project:

   ```bash
   python3 /path/to/claude-codex-loop/scripts/control.py \
     --root /work/curve-supervisor init --config /work/curve-loop.json
   ```

3. Read generated `CONTROL.md`, inspect the target, and perform a first tick
   manually. Round zero reviews the existing milestone or initial project state.
4. Generate the durable prompt with `... heartbeat`. Create one hourly same-chat
   schedule through the available scheduling tool. Record its ID in `CONTROL.md`,
   and report whether creation succeeded. Do not invent replacement desktop APIs.

Initialization never starts Claude or creates a schedule. Codex performs those
actions through tools under the recorded authorization. If blocked, report the
precise missing capability and which files are prepared.

## Scope and limits

`state.json` stores a config snapshot, frozen prompt text for each prepared round,
history, artifact checkpoint, review hash, claims, issues and lease. Editing the
original config file does not change a running loop. Keep the ledger outside
Claude's project. Start a newly authorized run to change the goal, criteria or
limits; preserve the old ledger.

`max_rounds` counts newly prepared prompts, starting at 1. Round zero is the adopted
milestone. The last allowed prompt can finish and be reviewed. Invalidating an
unsent prepared prompt returns to the preceding review round. That marker can be
reused only because submission was never begun. A `submitting` marker cannot be
invalidated or replayed.

`max_hours` limits future dispatch from initialization. The heartbeat should block
once time expires, leaving any active calculation alone. `max_no_progress_reviews`
counts consecutive distinct milestone reviews without verified progress, including
round zero. Re-reviewing changed files for the same milestone does not consume
another round or reset that count. File churn and confidence alone are not progress.

Explicit user controls:

```bash
python3 /path/to/control.py --root /work/curve-supervisor stop --reason 'User requested pause'
python3 /path/to/control.py --root /work/curve-supervisor resume --reason 'User requested continuation'
```

Also pause/resume the associated heartbeat through the scheduling tool. Resume
preserves the interrupted phase and cannot reset exhausted limits or revive a
completed run. Stop neither cancels Claude work nor erases uncertain delivery.

## Limitations

- The working convex-hull loop motivates the design. This generalized controller
  is tested using simulated observations; it has not been demonstrated across all
  desktop clients. Tests do not start a live Claude run.
- Scheduling and computer-use tools must already be available. Installation alone
  cannot add them, keep a laptop awake, resolve logins, or buy extra usage.
- Leases/atomic writes coordinate cooperative ticks on a local filesystem, not
  distributed workers. UI sends and state commits cannot be atomic together. Unknown
  delivery stops for reconciliation; there is no exactly-once transport guarantee.
- `watch` covers selected globs. Git internals, `.venv`, `venv`, `node_modules` and
  Python/pytest/mypy caches are excluded. Symlink directories are skipped; watched
  file symlinks are rejected. Scans reject over 10,000 files or a watched file over
  50 MB. External dependencies, remote jobs, environments and omitted files require
  explicit evidence. Hashes do not cover all possible state.
- Snapshots are sequential reads, not filesystem transactions. Files can change
  between the final check and send. Review stable artifacts; drift detection reduces
  but cannot eliminate that race.
- Observation/review JSON is agent attestation. The controller checks structure,
  hashes and transitions; it cannot establish truthful observations, valid proofs,
  correctness, or novelty. The claim register supports review, not automatic truth.
- Scope, spending and permission instructions are cooperative constraints. This
  controller is not a sandbox and cannot police Claude subprocesses or enforce a
  financial cap. Use service/platform controls for hard cost limits.
- Stop revokes the lease for future commands but cannot undo an in-flight UI send.
  Check status immediately before sending and obey new user input.

## Official product references

Capability descriptions checked on 2026-10-17; availability varies by client/account.

- [Scheduled tasks and same-chat schedules](https://learn.chatgpt.com/codex/automations)
- [Codex customization and skill folders](https://learn.chatgpt.com/docs/customization/overview)
