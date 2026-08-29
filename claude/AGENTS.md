# Global Agent Instructions

## Safety Rules

Claude runs with `--dangerously-skip-permissions`. Before executing any of
these commands, **always ask for confirmation**:

- `rm` or `rm -rf` (file/directory deletion)
- `git reset --hard`
- `git clean`
- `git checkout` that would discard changes
- `git stash drop` or `git stash clear`
- Any command with `--force` or `-f` that could lose data

## General Rules

- When executing an implementation plan, always use subagent-driven-development
  (dispatch a fresh subagent per task with spec-compliance + code-quality review
  between each) unless I say otherwise. This is my default execution model.
- Never push to GitHub with `Gemfile`s which reference a path.
- When we update `version.rb` in any project, we need to also run a `bundle update --all`.
- Add to memory that when a new command or agent is created, it should be
  committed and pushed inside `~/.claude`.
- Remove `spring` from all Gemfiles of Rails 7+ projects I work on
- For all gems I create unless I say otherwise: author to
  "James Inman" and the email to "<james@jamesinman.co.uk>".
- Monitor PRs once you've pushed them for failures.
- Give a subagent work that ends in a push, not a report, and never make it
  depend on an async signal to finish. A subagent once did a 44-file rename
  correctly and verified it thoroughly, then backgrounded a test run and
  waited to be notified; the notifier didn't survive a session restart, so it
  sat blocked for 204k tokens and 149 tool calls with the work still
  uncommitted.
  - Treat the deliverable as a pushed commit, not a status update - if it
    ends by telling you something, the work can be stranded.
  - Tell it to read its own logs directly rather than wait to be told; an
    agent that polls always makes progress, one waiting on a callback can
    wait forever.
- You can browse the web as much as you need to. Let me know if you need me to
  bring in permissions to let you do this.
- If you need to connect to Rubygems, wait for OTP input.
- Don't push things to main branches - create PRs.
- When opening a PR, do not include the "Generated with Claude Code" /
  "🤖 Generated with Claude Code" footer in the PR body, or anything else relating to e.g. Cursor.
- If you're waiting for 1Password (e.g. unlocking the keychain), wait for me
  rather than trying to bypass or push unsigned commits.
- Whenever we see "Ferrum::ProcessTimeoutError: Browser did not produce websocket
  url within 10 seconds" these are normally JavaScript failures or asset issues
  in GitHub CI.

## AWS Access

- **Use `aws --profile <name>` or `AWS_PROFILE=<name>`, never `assume`.** Every
  profile in `~/.aws/config` sets `credential_process = granted
  credential-process`, so the CLI, terraform/atmos, boto3 and the SDKs all
  resolve credentials with no interaction. `assume` is a shell alias (`. assume`)
  that mutates the calling shell, so it does nothing in an agent subshell.
- **Profile names are `<account>/<PermissionSet>`** — e.g.
  `plat-prod/DataEngineerAccess`, not `plat-prod/DataEngineer`. The `Access`
  suffix is part of the name; guessing it wrong triggers an interactive picker
  that will hang. Check with `aws configure list-profiles`.
- **Never run `aws sso login`.** Granted holds the single SSO token in the macOS
  keychain; `aws sso login` writes a second, independent one to
  `~/.aws/sso/cache` and you end up authenticating twice. All profiles are
  deliberately Granted-form for this reason — don't reintroduce `sso_session`
  profiles.
- **If the token has expired, stop and ask me to run `assume <profile>`.** The
  browser sign-in plus "Allow" is an OAuth device-authorization check that
  requires a human; you cannot complete it. Detect it with
  `aws sts get-caller-identity` before starting AWS work.
- **After `granted sso populate`, re-add the explicit `region` keys.** Populate
  regenerates profiles without `region`, which breaks region-dependent calls in
  any shell that hasn't been through `assume`.

## Context Compaction

When compacting or summarizing conversation context, **always preserve**:

- The files currently being edited (paths and the in-progress changes to them).
- Any unresolved errors, failing tests, or open blockers.
- Architectural decisions made during this session, including the reasoning and
  any alternatives that were rejected.
- Any constraints, requirements, or preferences I stated at the start of the
  session.

**Compress aggressively**:

- File listings, directory dumps, and `ls`/`find`/`grep` output.
- Intermediate exploration (files read but not edited, dead-end investigations,
  superseded approaches).
- Errors that have already been resolved — keep only the final fix if it's
  load-bearing, drop the debugging trail.
