#!/usr/bin/env python3
"""
revision.py — query your solved problems for DSA revision.

All of these work on plain metadata read straight from
solutions/*/*/README.md — no external service, no network calls, works
completely offline.

Examples
--------
    python scripts/revision.py --topic binary-search
    python scripts/revision.py --difficulty medium
    python scripts/revision.py --old                  # solved > 90 days ago
    python scripts/revision.py --old --days 30         # custom threshold
    python scripts/revision.py --random                # one random pick
    python scripts/revision.py --random -n 5           # five random picks
    python scripts/revision.py --needs-revision         # flagged problems
    python scripts/revision.py --least-practiced        # weakest topics
    python scripts/revision.py --flag 42 --revision-status true
"""

from __future__ import annotations

import argparse
import random
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from utils import iter_problem_readmes, read_frontmatter_markdown, write_frontmatter_markdown, REPO_ROOT


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Query solved LeetCode problems for revision.")
    parser.add_argument("--topic", help="Filter by topic/pattern slug, e.g. binary-search")
    parser.add_argument("--difficulty", choices=["easy", "medium", "hard"], help="Filter by difficulty")
    parser.add_argument("--language", help="Filter by language, e.g. Python3")
    parser.add_argument("--old", action="store_true", help="Show problems solved more than --days ago")
    parser.add_argument("--days", type=int, default=90, help="Threshold for --old (default: 90)")
    parser.add_argument("--needs-revision", action="store_true", help="Show problems flagged needs_revision: true")
    parser.add_argument("--least-practiced", action="store_true", help="Show the topics you've solved the fewest problems in")
    parser.add_argument("--random", action="store_true", help="Pick random problem(s) for a quick drill")
    parser.add_argument("-n", type=int, default=1, help="How many results for --random (default: 1)")
    parser.add_argument("--flag", type=int, metavar="LEETCODE_ID", help="Set needs_revision on a problem by its LeetCode id")
    parser.add_argument("--revision-status", choices=["true", "false"], default="true", help="Value to set with --flag")
    return parser.parse_args()


def load_all():
    return list(iter_problem_readmes())


def print_results(results, header: str) -> None:
    print(f"\n{header} ({len(results)})\n" + "-" * len(header))
    if not results:
        print("  (none)")
        return
    for path, meta, _ in results:
        rel = path.relative_to(REPO_ROOT).parent.as_posix()
        tags = ", ".join(meta.get("pattern", []) or [])
        print(f"  #{meta['leetcode_id']:<5} {meta['title']:<40} {meta['difficulty']:<7} {meta['date_solved']}  [{tags}]  -> {rel}")
    print()


def cmd_flag(leetcode_id: int, value: bool) -> int:
    for path, meta, body in load_all():
        if meta.get("leetcode_id") == leetcode_id:
            meta["needs_revision"] = value
            write_frontmatter_markdown(path, meta, body)
            print(f"Set needs_revision={value} for #{leetcode_id} ({meta['title']}) -> {path}")
            return 0
    print(f"No solved problem found with LeetCode id {leetcode_id}")
    return 1


def main() -> int:
    args = parse_args()

    if args.flag is not None:
        return cmd_flag(args.flag, args.revision_status == "true")

    problems = load_all()
    if not problems:
        print("No solved problems found yet under solutions/. Run scripts/sync.py first.")
        return 0

    if args.topic:
        problems = [p for p in problems if args.topic.lower() in [t.lower() for t in (p[1].get("pattern") or [])]]
        print_results(problems, f"Problems tagged '{args.topic}'")
        return 0

    if args.difficulty:
        problems = [p for p in problems if p[1]["difficulty"].lower() == args.difficulty]
        print_results(problems, f"{args.difficulty.title()} problems")
        return 0

    if args.language:
        problems = [p for p in problems if p[1]["language"].lower() == args.language.lower()]
        print_results(problems, f"Problems solved in {args.language}")
        return 0

    if args.old:
        cutoff = datetime.now(timezone.utc) - timedelta(days=args.days)
        old_ones = [
            p for p in problems
            if datetime.strptime(p[1]["date_solved"], "%Y-%m-%d").replace(tzinfo=timezone.utc) < cutoff
        ]
        print_results(old_ones, f"Solved more than {args.days} days ago")
        return 0

    if args.needs_revision:
        flagged = [p for p in problems if p[1].get("needs_revision")]
        print_results(flagged, "Flagged for revision")
        return 0

    if args.least_practiced:
        counts: Counter[str] = Counter()
        for _, meta, _ in problems:
            for tag in meta.get("pattern") or []:
                counts[tag] += 1
        print("\nLeast-practiced patterns\n------------------------")
        for topic, count in sorted(counts.items(), key=lambda kv: kv[1])[:15]:
            print(f"  {topic:<25} {count}")
        print()
        return 0

    if args.random:
        picks = random.sample(problems, k=min(args.n, len(problems)))
        print_results(picks, "Random pick(s) for practice")
        return 0

    # default: summary
    print_results(problems, "All solved problems")
    return 0


if __name__ == "__main__":
    sys.exit(main())
