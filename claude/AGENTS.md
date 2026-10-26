# Global Agent Instructions

## Safety Rules

Before running any of these, **always ask for confirmation**, even when
permission prompts are switched off:

- `rm` or `rm -rf` (file/directory deletion)
- `git reset --hard`
- `git clean`
- `git checkout` that would discard changes
- `git stash drop` or `git stash clear`
- Any command with `--force` or `-f` that could lose data

Claude Code also enforces these as `permissions.ask` rules in
`~/.dotfiles/claude/settings.json`. Cowork, Codex and Cursor do not read that
file, so this list is the fallback there.

## Writing

- Use British English spelling in prose, docs, commit messages and PR bodies.
  Leave code identifiers and API names as they are.
- Author every file, including scratch notes and throwaway scripts, in
  printable ASCII: `-` not em or en dashes, `->` not arrows, plain quotes.
  Never write a literal control byte; write the escape text (`\0`) instead.

## General Rules

- When executing an implementation plan, always use subagent-driven-development
  (dispatch a fresh subagent per task with spec-compliance + code-quality review
  between each) unless I say otherwise. This is my default execution model.
- On complex or multi-step tasks, write a todo list of the steps before
  starting and keep it updated as each one completes. It keeps progress
  visible and stops the task drifting or dropping steps part-way through.
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
- Global agent config lives in `~/.dotfiles/claude/` (this file, Claude Code
  `settings.json`, `keybindings.json`), not in `~/.claude`. Put any new global
  command, agent or setting there and commit it in `~/.dotfiles` on a branch
  with a PR. `~/.claude/CLAUDE.md` and `cursor/user-rules.md` are copies that
  `agents-sync` refreshes on commit; never edit a copy. Skills are installed by
  dotagents into `~/.agents/skills`.
- When we update `version.rb` in any project, we need to also run a `bundle update --all`.
- Remove `spring` from all Gemfiles of Rails 7+ projects I work on
- For all gems I create unless I say otherwise: author to
  "James Inman" and the email to "<james@jamesinman.co.uk>".
- Write Playwright scripts in Ruby with the `playwright-ruby-client` gem, not
  JavaScript, unless I say otherwise.
- You can browse the web as much as you need to. Let me know if you need me to
  bring in permissions to let you do this.
- If you need to connect to Rubygems, wait for OTP input.
- If you're waiting for 1Password (e.g. unlocking the keychain), wait for me
  rather than trying to bypass or push unsigned commits.
- Whenever we see "Ferrum::ProcessTimeoutError: Browser did not produce websocket
  url within 10 seconds" these are normally JavaScript failures or asset issues
  in GitHub CI.

## Git and Pull Requests

- Every new agent session works in its own git worktree. Before the first
  edit, if you are on a repo's primary checkout, create a worktree on a fresh
  branch and do all the work there: in Claude Code use `EnterWorktree`,
  otherwise `git worktree add <path> -b <branch>`, following the repo's own
  convention for where worktrees live if it has one. If the session already
  started inside a worktree or an isolated VM (Conductor, Cursor Cloud), stay
  there.
- Before the first edit, check what is already in flight with
  `gh pr list --search "<area>"` and `git branch -r`. I often open a PR and then
  ask about the same problem later; add to the existing branch rather than
  opening a duplicate.
- Before committing to an existing branch, run `git fetch origin <branch>` and
  `git status -sb`. Cursor Cloud agents on the same branch rebase and
  force-push, so a local checkout can silently diverge.
- Local commits are fine without asking. If the branch already has an open,
  unmerged PR, push the commits after checking the PR's status. Otherwise ask
  before pushing.
- Don't push to main branches - create PRs, and open them as drafts unless I
  say otherwise.
- Keep PR bodies to one or two short lines: what changed and why. Skip
  multi-section templates and test-plan sections on routine PRs.
- Never add a "Generated with Claude Code" footer (with or without the robot
  emoji), or any other agent or Cursor attribution, to commit messages or PR
  bodies.
- Monitor PRs once you've pushed them for failures.
- Never push to GitHub with `Gemfile`s which reference a path.
- Never `git stash` in Conductor worktrees: every worktree shares one stash
  stack, so `stash pop` can apply another workspace's WIP. Use `git restore`,
  `git show <ref>:<path>` or a throwaway worktree instead.

## This Mac

- Loopback connects lie: a TCP connect to `127.0.0.1:<any port>` succeeds
  even when nothing is listening and only fails on the first read. Check
  local port liveness with `lsof -ti tcp:<port> -sTCP:LISTEN`, never with a
  connect probe, and don't "fix" a probe by adding read timeouts.

## AWS Access

- **Use `aws --profile <name>` or `AWS_PROFILE=<name>` for credentials, not
  `assume`.** Every profile in `~/.aws/config` sets
  `credential_process = granted credential-process`, so the CLI,
  terraform/atmos, boto3 and the SDKs all resolve credentials with no
  interaction. `assume` is a shell alias (`. assume`) that mutates the calling
  shell, so it cannot hand credentials to an agent subshell.
- **Profile names are `<account>/<PermissionSet>`**, e.g.
  `plat-prod/DataEngineerAccess`, not `plat-prod/DataEngineer`. The `Access`
  suffix is part of the name; guessing it wrong triggers an interactive picker
  that will hang. Check with `aws configure list-profiles`.
- **Never run `aws sso login`.** Granted holds the single SSO token in the macOS
  keychain; `aws sso login` writes a second, independent one to
  `~/.aws/sso/cache` and you end up authenticating twice. All profiles are
  deliberately Granted-form for this reason, so don't reintroduce `sso_session`
  profiles.
- **Detect an expired token before starting AWS work** with
  `aws sts get-caller-identity`.
- **If the token has expired, start the sign-in straight away; don't ask
  first.** On the first expired-token error (`NoCredentials`,
  `InvalidGrantException`, "please login using 'granted sso login'"), run
  `GRANTED_ALIAS_CONFIGURED=true AWS_REGION=eu-west-1 assume plat-prod/AdministratorAccess 2>&1 </dev/null`
  in the background. It opens the browser on this Mac by itself, so all I do
  is approve. Post the link it prints as a fallback, then re-probe with
  `aws sts get-caller-identity` and carry on once it passes. One sign-in
  covers every role on that start URL. The callback waits only a few minutes:
  if it times out, tell me and restart it when I'm back rather than looping.
  Don't use `assume --exec` inline; it hangs without a TTY.
- **Regenerate profiles with `granted-populate`, not `granted sso populate`.**
  Populate rewrites every generated profile from scratch, dropping
  `granted_sso_registration_scopes`. Without that key Granted gets a token it
  cannot refresh, so every expiry needs a browser login. The wrapper passes
  `--default-region` and re-adds the scopes.

## Keeping Context Lean

Claude Code runs on Bedrock and is billed per token. Most of the spend is the
prompt cache re-reading long contexts on every call and re-writing them after
a gap, not output. You can't run `/compact` or `/clear` yourself, so tell me
when to, in one line at the end of your reply:

- **`/clear` or a new session** when a task is finished (PR pushed, question
  answered) and the next request is unrelated. Before suggesting it, make sure
  anything needed to resume lives outside the conversation: a commit, the PR
  body, or a notes file.
- **`/compact <focus>`** when the conversation has grown long but the work
  carries on and the early exploration is no longer needed, e.g.
  `/compact keep the migration plan and the open failures`.
- **`/compact` before a long wait**, such as a CI run or a review I'll come
  back to later. The cache lasts an hour; the next message after that re-sends
  the whole context. Idle compaction covers some of this, but only once the
  context passes 100k tokens.

Keep the context small in the first place: read the part of a file you need,
don't print large command output, and hand broad searches to a subagent so only
its conclusion comes back. Each subagent call re-reads that subagent's own
context, so don't spawn one for a lookup you can do in a few tool calls.

## Context Compaction

When compacting or summarising conversation context, **always preserve**:

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
- Errors that have already been resolved, keeping only the final fix if it's
  load-bearing, and dropping the debugging trail.
