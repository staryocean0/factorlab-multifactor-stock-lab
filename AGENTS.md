# Public launcher only

This is a PUBLIC bootstrap workspace, not the private research repository. Read README, then run `python bootstrap.py --destination PATH_OUTSIDE_THIS_WORKTREE` after the cloud operator configures repo-scoped private authentication.

Before any research, change into the returned PRIVATE checkout and read its own AGENTS.md and CLOUD_CURRENT.json. All real code changes, datasets, findings and commits belong there. Never copy private files or patches into this public Git tree, commit, PR, issue, log or Actions artifact. Do not echo credentials or request tokens in chat. .gitignore is not access control.

This launcher cannot grant private access. If authentication is absent, report the missing permission and stop before data fetch. Never reuse the public workspace token by assuming it can access another repository; never copy the local controller's OAuth token.

Do not run old public-main strategies, data or historical instructions as current authority. Do not clean/delete/rewrite old branches or PRs. No training or production starts merely from bootstrap. No Actions compute or untrusted PR execution with private credentials.

Returning work means a commit/PR in the private repository, not publishing private patches here. GitHub storage privacy is not scientific lockbox isolation; the private research instructions define data roles.
