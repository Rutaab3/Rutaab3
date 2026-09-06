#!/usr/bin/env python3
"""Follow back GitHub followers and optionally unfollow non-followers.

The script is intentionally dry-run by default. Pass --apply to make changes.
It uses the authenticated user's GitHub account; it does not accept passwords
or scrape the GitHub website.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

API_ROOT = "https://api.github.com"
USER_AGENT = "rutaabali3-github-follow-sync"


def request_json(
    token: str,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
) -> Any:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": USER_AGENT,
        "X-GitHub-Api-Version": "2022-11-28",
        "Authorization": f"Bearer {token}",
    }
    request = urllib.request.Request(
        API_ROOT + path, data=body, headers=headers, method=method
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub API {error.code} for {method} {path}: {detail}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"Could not reach GitHub: {error.reason}") from error


def paginated_usernames(token: str, path: str) -> set[str]:
    usernames: set[str] = set()
    page = 1
    while True:
        query = urllib.parse.urlencode({"per_page": 100, "page": page})
        batch = request_json(token, "GET", f"{path}?{query}")
        if not batch:
            return usernames
        usernames.update(item["login"] for item in batch)
        if len(batch) < 100:
            return usernames
        page += 1


def follow(token: str, username: str) -> None:
    request_json(token, "PUT", f"/user/following/{urllib.parse.quote(username)}")


def unfollow(token: str, username: str) -> None:
    request_json(token, "DELETE", f"/user/following/{urllib.parse.quote(username)}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Follow back GitHub followers and optionally unfollow non-followers."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="perform follow/unfollow changes; without this flag the script only previews them",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="USERNAME",
        help="never unfollow this username; may be supplied more than once",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.5,
        metavar="SECONDS",
        help="pause between write requests (default: 0.5)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("Set GITHUB_TOKEN to a token that can follow and unfollow users.", file=sys.stderr)
        return 2
    if args.delay < 0:
        print("--delay must be zero or greater.", file=sys.stderr)
        return 2

    try:
        followers = paginated_usernames(token, "/user/followers")
        following = paginated_usernames(token, "/user/following")
    except RuntimeError as error:
        print(error, file=sys.stderr)
        return 1

    to_follow = sorted(followers - following)
    excluded = {username.casefold() for username in args.exclude}
    to_unfollow = sorted(
        username for username in following - followers if username.casefold() not in excluded
    )

    mode = "APPLYING CHANGES" if args.apply else "DRY RUN (no changes)"
    print(mode)
    print(f"Followers: {len(followers)} | Following: {len(following)}")
    print(f"Will follow back ({len(to_follow)}): {', '.join(to_follow) or 'none'}")
    print(f"Will unfollow ({len(to_unfollow)}): {', '.join(to_unfollow) or 'none'}")
    if excluded:
        print(f"Protected usernames: {', '.join(sorted(args.exclude))}")

    if not args.apply:
        print("Nothing changed. Re-run with --apply to execute this plan.")
        return 0

    failures = 0
    for username in to_follow:
        try:
            follow(token, username)
            print(f"Followed @{username}")
        except RuntimeError as error:
            failures += 1
            print(f"Could not follow @{username}: {error}", file=sys.stderr)
        time.sleep(args.delay)

    for username in to_unfollow:
        try:
            unfollow(token, username)
            print(f"Unfollowed @{username}")
        except RuntimeError as error:
            failures += 1
            print(f"Could not unfollow @{username}: {error}", file=sys.stderr)
        time.sleep(args.delay)

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
