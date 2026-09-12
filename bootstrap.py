"""Public-only launcher. Never copy private content into this worktree."""

import argparse
import json
import subprocess
from pathlib import Path

REPO = "staryocean0/factorlab-multifactor-research-private"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    target = args.destination.expanduser().resolve()
    if target == root or target.is_relative_to(root) or root.is_relative_to(target) or target.exists():
        raise ValueError("destination must be new and outside the public worktree")
    result = subprocess.run(["gh", "repo", "view", REPO, "--json", "nameWithOwner,isPrivate"], capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError("Private access missing. Configure a repo-scoped secret in the cloud environment; do not paste it in chat.")
    identity = json.loads(result.stdout)
    if identity != {"isPrivate": True, "nameWithOwner": REPO}:
        raise ValueError("private repository identity/visibility mismatch")
    subprocess.run(
        ["gh", "repo", "clone", REPO, str(target), "--", "--depth", "1"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    print("Private checkout ready. Change directory there and read AGENTS.md before work.")
    print(target)


if __name__ == "__main__":
    main()
