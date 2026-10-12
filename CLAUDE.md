# workbench: agent instructions

Read README.md first, then docs/EXPANSION_IDEAS.md for the ranked backlog.

## Hygiene (hard rules)

- No personal information: no names, emails, hostnames, home paths, employer
  details. The owner is "the maintainer" if a reference is unavoidable.
- `workbench.toml` is the maintainer's private registry and is gitignored.
  Never commit one; `workbench.example.toml` is the template. Tests build a
  synthetic registry in a temp dir.
- Commit as the repo's configured git author only: no Co-Authored-By, no
  session links, no extra identities. Open a pull request against main; do
  not push to main directly.
- Open licenses only (OSI). No new dependency without saying so in the PR.

## Engineering

- Python 3.11+, uv for environments, pytest for tests. The catalog is
  imported into every project's notebook environment, so keep its
  dependencies minimal (numpy, pyarrow, safetensors, mcap).
- The sandbox is usually Linux. `wb/launch.py`, `wb/launcher.py` and
  `wb/tray.py` are Windows-first (pywin32, winreg, Windows Terminal). Guard
  imports so modules load everywhere, test the pure functions that return
  argv and paths, and skip Windows-only behaviour with `pytest.mark.skipif`.
  Do not refactor the platform layer unless the task is that refactor.
- Launchers return argv before spawning; test them without spawning.
- Docs state what a thing does and how to tell it works. Keep rationale short.
