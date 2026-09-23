"""
leetcode_client.py

Thin wrapper around LeetCode's unofficial GraphQL endpoint.

IMPORTANT — read this before touching anything here:
LeetCode does not publish or support a public API for this use case.
Everything in this file talks to the same GraphQL endpoint LeetCode's own
website uses (https://leetcode.com/graphql). Two of the three calls below
work with NO authentication (they only need your public username). The
third call - fetching the actual source code of a submission - requires
your logged-in session cookie, because LeetCode does not expose submission
source code publicly for anyone, including the author, without being
authenticated as that author.

This is why LEETCODE_SESSION / LEETCODE_CSRF_TOKEN exist as secrets. There
is no safer official alternative for retrieving your own submitted code
programmatically. See the "Limitations" and "Security" sections of the
project README for the risk this carries (LeetCode can change or block
this endpoint at any time, and the session cookie expires periodically).
"""

from __future__ import annotations

import time
import logging
from dataclasses import dataclass
from typing import Any, Optional

import requests

logger = logging.getLogger("leetcode_client")

GRAPHQL_URL = "https://leetcode.com/graphql"
BASE_URL = "https://leetcode.com"

# LeetCode's `lang` submission field -> (file extension, pretty display name)
LANGUAGE_MAP = {
    "python3": (".py", "Python3"),
    "python": (".py", "Python"),
    "java": (".java", "Java"),
    "cpp": (".cpp", "C++"),
    "c": (".c", "C"),
    "csharp": (".cs", "C#"),
    "javascript": (".js", "JavaScript"),
    "typescript": (".ts", "TypeScript"),
    "golang": (".go", "Go"),
    "ruby": (".rb", "Ruby"),
    "swift": (".swift", "Swift"),
    "kotlin": (".kt", "Kotlin"),
    "rust": (".rs", "Rust"),
    "scala": (".scala", "Scala"),
    "php": (".php", "PHP"),
    "racket": (".rkt", "Racket"),
    "erlang": (".erl", "Erlang"),
    "elixir": (".ex", "Elixir"),
    "dart": (".dart", "Dart"),
}


class LeetCodeAuthError(RuntimeError):
    """Raised when the stored session cookie is missing, invalid, or expired."""


class LeetCodeAPIError(RuntimeError):
    """Raised for any other unexpected API failure."""


@dataclass
class Submission:
    submission_id: str
    title: str
    title_slug: str
    timestamp: int  # unix seconds
    lang: str


class LeetCodeClient:
    def __init__(
        self,
        username: str,
        session_cookie: Optional[str] = None,
        csrf_token: Optional[str] = None,
        timeout: int = 15,
        max_retries: int = 3,
    ):
        self.username = username
        self.session_cookie = session_cookie
        self.csrf_token = csrf_token
        self.timeout = timeout
        self.max_retries = max_retries
        self._session = requests.Session()

    # ------------------------------------------------------------------ #
    # low-level request helpers
    # ------------------------------------------------------------------ #
    def _headers(self, authenticated: bool = False) -> dict:
        headers = {
            "Content-Type": "application/json",
            "Referer": "https://leetcode.com",
            "User-Agent": "Mozilla/5.0 (leetcode-tracker automation; +https://github.com)",
        }
        if authenticated:
            if not self.session_cookie or not self.csrf_token:
                raise LeetCodeAuthError(
                    "LEETCODE_SESSION / LEETCODE_CSRF_TOKEN are not set. "
                    "Authenticated calls (fetching submission source code) "
                    "cannot be made without them."
                )
            headers["Cookie"] = (
                f"LEETCODE_SESSION={self.session_cookie}; csrftoken={self.csrf_token}"
            )
            headers["x-csrftoken"] = self.csrf_token
        return headers

    def _post(self, payload: dict, authenticated: bool = False) -> dict:
        last_error: Optional[Exception] = None
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self._session.post(
                    GRAPHQL_URL,
                    json=payload,
                    headers=self._headers(authenticated=authenticated),
                    timeout=self.timeout,
                )
                if resp.status_code == 401 or resp.status_code == 403:
                    raise LeetCodeAuthError(
                        f"LeetCode rejected the request (HTTP {resp.status_code}). "
                        "Your LEETCODE_SESSION cookie is very likely expired. "
                        "See README > Security > 'Rotating the LeetCode session'."
                    )
                resp.raise_for_status()
                data = resp.json()
                if "errors" in data and data["errors"]:
                    raise LeetCodeAPIError(str(data["errors"]))
                return data
            except LeetCodeAuthError:
                raise  # do not retry auth failures
            except (requests.RequestException, LeetCodeAPIError) as exc:
                last_error = exc
                wait = 2 ** attempt
                logger.warning(
                    "LeetCode API call failed (attempt %s/%s): %s. Retrying in %ss.",
                    attempt, self.max_retries, exc, wait,
                )
                time.sleep(wait)
        raise LeetCodeAPIError(f"LeetCode API call failed after {self.max_retries} attempts: {last_error}")

    # ------------------------------------------------------------------ #
    # public, unauthenticated calls
    # ------------------------------------------------------------------ #
    def get_recent_accepted_submissions(self, limit: int = 20) -> list[Submission]:
        """
        Public endpoint - no login required. Returns at most the last ~20
        Accepted submissions LeetCode is willing to expose publicly for a
        username. This is used purely for DETECTING new activity.
        """
        query = """
        query recentAcSubmissions($username: String!, $limit: Int!) {
          recentAcSubmissionList(username: $username, limit: $limit) {
            id
            title
            titleSlug
            timestamp
            lang
          }
        }
        """
        data = self._post(
            {"query": query, "variables": {"username": self.username, "limit": limit}},
            authenticated=False,
        )
        items = data.get("data", {}).get("recentAcSubmissionList") or []
        return [
            Submission(
                submission_id=str(item["id"]),
                title=item["title"],
                title_slug=item["titleSlug"],
                timestamp=int(item["timestamp"]),
                lang=item.get("lang", "unknown"),
            )
            for item in items
        ]

    def get_question_metadata(self, title_slug: str) -> dict:
        """Public endpoint - problem number, difficulty, tags, URL."""
        query = """
        query questionData($titleSlug: String!) {
          question(titleSlug: $titleSlug) {
            questionFrontendId
            title
            titleSlug
            difficulty
            topicTags {
              name
              slug
            }
          }
        }
        """
        data = self._post({"query": query, "variables": {"titleSlug": title_slug}}, authenticated=False)
        q = data.get("data", {}).get("question")
        if not q:
            raise LeetCodeAPIError(f"No question metadata returned for slug '{title_slug}'")
        return q

    # ------------------------------------------------------------------ #
    # authenticated call — requires YOUR OWN session cookie
    # ------------------------------------------------------------------ #
    def get_submission_code(self, submission_id: str) -> str:
        """
        Returns the source code of one of YOUR OWN submissions.
        Requires LEETCODE_SESSION + csrftoken because LeetCode does not
        expose submission source code without authentication, even to the
        submission's own author, via this endpoint.
        """
        query = """
        query submissionDetails($submissionId: Int!) {
          submissionDetails(submissionId: $submissionId) {
            code
            statusCode
          }
        }
        """
        data = self._post(
            {"query": query, "variables": {"submissionId": int(submission_id)}},
            authenticated=True,
        )
        details = data.get("data", {}).get("submissionDetails")
        if not details or not details.get("code"):
            raise LeetCodeAPIError(
                f"Could not retrieve source for submission {submission_id}. "
                "The session cookie may be expired or the submission is not yours."
            )
        return details["code"]
