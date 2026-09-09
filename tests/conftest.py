"""Make repository script helpers importable by delivered historical tests.

This adds the repository namespace during pytest collection only. The frozen
V1.3 packaging configuration and all research execution guards remain intact.
"""
import sys
from pathlib import Path

REPOSITORY_ROOT = str(Path(__file__).resolve().parents[1])
if REPOSITORY_ROOT not in sys.path:
    sys.path.insert(0, REPOSITORY_ROOT)
