#!/usr/bin/env python3
"""
sync.py — the heart of the automation.

Run by .github/workflows/leetcode-sync.yml on a schedule.

What it does, in order:
  1. Ask LeetCode (public, unauthenticated) for your recent Accepted submissions.
  2. Compare against data/synced_submissions.json to find genuinely NEW ones
     (a problem you hadn't solved before, or one you re-solved after it).
  3. For each new one:
       a. Fetch problem metadata (difficulty, tags, id) — public, unauthenticated.
       b. Fetch the submission's source code — REQUIRES your session cookie.
       c. Write solutions/<topic>/<id>-<slug>/solution.<ext> and README.md.
       d. `git add` + `git commit` that single problem with a meaningful message.
  4. Regenerate the root README dashboard from everything on disk.
  5. Commit the dashboard update (only if it changed).
  6. Exit 0 with no commits if there was nothing new — this is the common case
     and is NOT an error.

This script deliberately does the git commit/push itself (rather than only
writing files and letting an Action step commit everything as one blob) so
that each problem gets its own meaningful commit message, per the project's
requirements.
"""

from __future__ import annotations

import os
import sys
import logging
import subprocess
from datetime import datetime, timezone

from leetcode_client import (
    LeetCodeClient,
    LeetCodeAuthError,
    LeetCodeAPIError,
    LANGUAGE_MAP,
)
from utils import (
    SOLUTIONS_DIR,
    load_state,
    save_state,
    slugify,
    write_frontmatter_markdown,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("sync")

DIFFICULTY_ORDER = {"Easy": 0, "Medium": 1, "Hard": 2}


def env(name: str, required: bool = True, default: str | None = None) -> str | None:
    value = os.environ.get(name, default)
    if required and not value:
        logger.error("Required environment variable %s is not set.", name)
        sys.exit(1)
    return value


def run_git(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    logger.info("git %s", " ".join(args))
    return subprocess.run(["git", *args], check=check, capture_output=True, text=True)


def git_has_staged_changes() -> bool:
    result = run_git("diff", "--cached", "--quiet", check=False)
    return result.returncode != 0


def configure_git_identity() -> None:
    """
    CRITICAL for the GitHub contribution graph:
    Commits only count toward your profile if the commit's author email is
    an email address verified on your GitHub account. The default identity
    GitHub Actions uses (github-actions[bot]) does NOT count. So we set the
    author identity to the repo owner's own GitHub noreply address.
    """
    github_username = env("GITHUB_REPOSITORY_OWNER", required=True)
    commit_email = env(
        "GIT_COMMIT_EMAIL",
        required=False,
        default=None,
    )
    if not commit_email:
        # Fallback: GitHub's automatically-generated noreply address.
        # This only works if the user hasn't disabled it; the safest option
        # is still to set GIT_COMMIT_EMAIL explicitly (see README).
        logger.warning(
            "GIT_COMMIT_EMAIL not set — falling back to a guessed noreply "
            "address. Set the GIT_COMMIT_EMAIL secret/variable explicitly "
            "to guarantee commits count on your contribution graph."
        )
        commit_email = f"{github_username}@users.noreply.github.com"

    run_git("config", "user.name", github_username)
    run_git("config", "user.email", commit_email)


def build_solution_path(question: dict, lang: str) -> tuple[str, str]:
    frontend_id = str(question["questionFrontendId"]).zfill(4)
    title_slug = question["titleSlug"]
    tags = question.get("topicTags") or []
    primary_topic = slugify(tags[0]["name"]) if tags else "uncategorized"
    ext, _ = LANGUAGE_MAP.get(lang, (".txt", lang))
    problem_dir = SOLUTIONS_DIR / primary_topic / f"{frontend_id}-{title_slug}"
    return str(problem_dir), ext


def write_problem_files(question: dict, code: str, lang: str, solved_at: datetime) -> str:
    frontend_id = str(question["questionFrontendId"])
    title = question["title"]
    difficulty = question["difficulty"]
    tags = [t["slug"] for t in (question.get("topicTags") or [])]
    _, lang_name = LANGUAGE_MAP.get(lang, (".txt", lang))

    problem_dir_str, ext = build_solution_path(question, lang)
    from pathlib import Path
    problem_dir = Path(problem_dir_str)
    problem_dir.mkdir(parents=True, exist_ok=True)

    solution_path = problem_dir / f"solution{ext}"
    solution_path.write_text(code.rstrip() + "\n", encoding="utf-8")

    problem_url = f"https://leetcode.com/problems/{question['titleSlug']}/"
    metadata = {
        "leetcode_id": int(frontend_id),
        "title": title,
        "difficulty": difficulty,
        "url": problem_url,
        "pattern": tags,
        "language": lang_name,
        "date_solved": solved_at.strftime("%Y-%m-%d"),
        "needs_revision": False,
    }
    body = (
        f"# {frontend_id}. {title}\n\n"
        f"* LeetCode: #{frontend_id}\n"
        f"* Difficulty: {difficulty}\n"
        f"* Pattern: {', '.join(tags) if tags else 'uncategorized'}\n"
        f"* Language: {lang_name}\n"
        f"* Solved: {solved_at.strftime('%Y-%m-%d')}\n"
        f"* URL: {problem_url}\n\n"
        "## Approach\n\n"
        "_Add a short explanation of your approach here._\n\n"
        "## Complexity\n\n"
        "* Time: _fill in_\n"
        "* Space: _fill in_\n\n"
        "## Solution\n\n"
        f"See [`solution{ext}`](./solution{ext}).\n"
    )
    write_frontmatter_markdown(problem_dir / "README.md", metadata, body)
    return problem_dir_str


def main() -> int:
    username = env("LEETCODE_USERNAME")
    session_cookie = env("LEETCODE_SESSION", required=False)
    csrf_token = env("LEETCODE_CSRF_TOKEN", required=False)
    limit = int(env("SYNC_LOOKBACK", required=False, default="20"))

    client = LeetCodeClient(username=username, session_cookie=session_cookie, csrf_token=csrf_token)

    try:
	recent = client.get_all_accepted_submissions(limit=100)
   	except LeetCodeAPIError as exc:
        logger.error("Failed to fetch recent submissions: %s", exc)
        return 1

    if not recent:
        logger.info("No accepted submissions found for user '%s'. Nothing to do.", username)
        return 0

    state = load_state()
    new_items = []
    for sub in recent:
        # We key state by question, not by submission id, because a problem
        # can only need ONE canonical solved entry; re-solving it later is
        # treated as an update, not a duplicate.
        question = None
        try:
            question = client.get_question_metadata(sub.title_slug)
        except LeetCodeAPIError as exc:
            logger.warning("Skipping '%s': could not fetch metadata (%s)", sub.title, exc)
            continue
        qid = str(question["questionFrontendId"])
        last_synced_submission = state.get(qid)
        if last_synced_submission == sub.submission_id:
            continue  # already synced, exact same submission
        new_items.append((sub, question))

    if not new_items:
        logger.info("Checked %d recent submissions — nothing new to sync.", len(recent))
        return 0

    if not session_cookie or not csrf_token:
        logger.error(
            "%d new accepted submission(s) detected, but LEETCODE_SESSION / "
            "LEETCODE_CSRF_TOKEN are not configured, so the source code "
            "cannot be fetched. Add these GitHub Secrets and re-run.",
            len(new_items),
        )
        return 1

    configure_git_identity()
    synced_count = 0

    # Oldest-first so commit history reads chronologically.
    for sub, question in sorted(new_items, key=lambda pair: pair[0].timestamp):
        qid = str(question["questionFrontendId"])
        title = question["title"]
        try:
            code = client.get_submission_code(sub.submission_id)
        except LeetCodeAuthError as exc:
            logger.error("Authentication failed while fetching code for #%s %s: %s", qid, title, exc)
            return 1
        except LeetCodeAPIError as exc:
            logger.warning("Could not fetch code for #%s %s, skipping this run: %s", qid, title, exc)
            continue

        solved_at = datetime.fromtimestamp(sub.timestamp, tz=timezone.utc)
        is_update = qid in state
        problem_dir = write_problem_files(question, code, sub.lang, solved_at)

        run_git("add", problem_dir)
        if not git_has_staged_changes():
            logger.info("No file changes for #%s %s, skipping commit.", qid, title)
            continue

        verb = "update" if is_update else "add"
        commit_message = f"feat(leetcode): {verb} #{qid} {title}"
        run_git("commit", "-m", commit_message)
        logger.info("Committed: %s", commit_message)

        state[qid] = sub.submission_id
        save_state(state)
        run_git("add", "data/synced_submissions.json")
        run_git("commit", "-m", f"chore(leetcode): update sync state for #{qid}", check=False)

        synced_count += 1

    if synced_count == 0:
        logger.info("No commits were made this run.")
        return 0

    # Regenerate the dashboard README with everything now on disk.
    subprocess.run([sys.executable, str(os.path.join(os.path.dirname(__file__), "generate_readme.py"))], check=True)
    run_git("add", "README.md")
    if git_has_staged_changes():
        run_git("commit", "-m", "docs(leetcode): update progress dashboard")

    run_git("push")
    logger.info("Synced %d new/updated problem(s) and pushed to remote.", synced_count)
    return 0


if __name__ == "__main__":
    sys.exit(main())
