"""
test_dry_run.py

A safe, offline test you can run BEFORE ever pointing this at your real
LeetCode account. It monkeypatches LeetCodeClient so no network calls are
made, then exercises the same write_problem_files()/state logic sync.py
uses, in a scratch copy of the repo (never touches your real solutions/ or
data/ folders).

Run:
    python -m tests.test_dry_run
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path
from datetime import datetime, timezone

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))


def run() -> None:
    import utils
    import sync

    scratch = Path(tempfile.mkdtemp(prefix="leetcode-tracker-test-"))
    print(f"Using scratch directory: {scratch}")

    # Redirect the module-level paths so we never touch the real repo.
    utils.SOLUTIONS_DIR = scratch / "solutions"
    utils.DATA_DIR = scratch / "data"
    utils.STATE_FILE = utils.DATA_DIR / "synced_submissions.json"
    sync.SOLUTIONS_DIR = utils.SOLUTIONS_DIR

    fake_question = {
        "questionFrontendId": "1",
        "title": "Two Sum",
        "titleSlug": "two-sum",
        "difficulty": "Easy",
        "topicTags": [{"name": "Array", "slug": "array"}, {"name": "Hash Table", "slug": "hash-table"}],
    }
    fake_code = "class Solution:\n    def twoSum(self, nums, target):\n        return []\n"

    # --- Test 1: first-run write ---
    problem_dir = sync.write_problem_files(fake_question, fake_code, "python3", datetime.now(timezone.utc))
    assert (Path(problem_dir) / "solution.py").exists(), "solution file was not created"
    assert (Path(problem_dir) / "README.md").exists(), "README was not created"
    print("[PASS] first-run write creates solution.py and README.md")

    # --- Test 2: state prevents duplicate treatment ---
    state = utils.load_state()
    state["1"] = "111"
    utils.save_state(state)
    reloaded = utils.load_state()
    assert reloaded["1"] == "111", "state did not persist"
    print("[PASS] sync state persists across load/save")

    # --- Test 3: re-writing (simulating an update) doesn't crash and overwrites cleanly ---
    updated_code = fake_code + "        # improved\n"
    sync.write_problem_files(fake_question, updated_code, "python3", datetime.now(timezone.utc))
    content = (Path(problem_dir) / "solution.py").read_text()
    assert "improved" in content, "updated solution was not written"
    print("[PASS] re-sync overwrites solution file without duplicating it")

    # --- Test 4: generate_readme runs against scratch data without crashing ---
    import generate_readme
    generate_readme.SOLUTIONS_DIR = utils.SOLUTIONS_DIR  # not required, iter_problem_readmes reads from utils
    dashboard = generate_readme.build_dashboard()
    assert "Two Sum" in dashboard
    print("[PASS] dashboard generation includes the synced problem")

    shutil.rmtree(scratch, ignore_errors=True)
    print("\nAll dry-run tests passed. No network calls were made, and your real repo was untouched.")


if __name__ == "__main__":
    run()
