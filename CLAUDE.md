# Claude Code

Read `AGENTS.md` first; it is the repository policy.

## Tool use

- Read and edit files with the Read, Edit and Write tools. Never use Bash for
  it: no `cat`, `sed`, `awk`, `echo >`, heredocs or `python - <<EOF` rewrites.
  Each of those triggers an approval prompt that the dedicated tools do not.
- Reserve Bash for commands that have to run: Docker (Ruff, pytest), git, ssh.
- Do not prefix commands with `cd <repo> &&`; the working directory is already
  the repository root.
