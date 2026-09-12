# Public research launcher

This branch intentionally contains no private research data or results. Existing main/history are preserved separately.

1. Configure authentication limited to `staryocean0/factorlab-multifactor-research-private` in your cloud environment's secret store. Do not paste a token into chat or repository files.
2. Run `python bootstrap.py --destination ../factorlab-private-work`.
3. Change to the private checkout. Read its AGENTS.md and CLOUD_CURRENT.json.
4. Work and commit only in that private checkout. Download exact private data packages as needed.

This does not enable GitHub Actions, grant production authority, or create a blind-test boundary. Missing private access requires operator setup, not a workaround through public files.
