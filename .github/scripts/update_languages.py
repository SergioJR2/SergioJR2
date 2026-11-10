#!/usr/bin/env python3
"""Update the profile README with language names from accessible non-fork repos."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path


API_ROOT = "https://api.github.com"
README_PATH = Path("README.md")
START_MARKER = "<!-- LANGUAGES:START -->"
END_MARKER = "<!-- LANGUAGES:END -->"


def github_get(path: str, token: str) -> tuple[object, dict[str, str]]:
    request = urllib.request.Request(
        f"{API_ROOT}{path}",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "SergioJR2-profile-language-summary",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
            headers = {key.lower(): value for key, value in response.headers.items()}
            return payload, headers
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"GitHub API returned HTTP {error.code}: {detail}"
        ) from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"Could not reach the GitHub API: {error.reason}") from error


def list_repositories(token: str, expected_login: str) -> list[dict[str, object]]:
    identity, _ = github_get("/user", token)
    actual_login = str(identity.get("login", ""))
    if actual_login.casefold() != expected_login.casefold():
        raise RuntimeError(
            "The token belongs to a different GitHub account than the profile repository."
        )

    repositories: list[dict[str, object]] = []
    page = 1
    query = urllib.parse.urlencode(
        {
            "visibility": "all",
            "affiliation": "owner,collaborator,organization_member",
            "per_page": 100,
        }
    )
    while True:
        page_query = f"{query}&page={page}"
        result, _ = github_get(f"/user/repos?{page_query}", token)
        if not isinstance(result, list):
            raise RuntimeError("GitHub returned an unexpected repository list.")
        repositories.extend(result)
        if len(result) < 100:
            break
        page += 1
    return repositories


def collect_languages(token: str, expected_login: str) -> dict[str, int]:
    totals: defaultdict[str, int] = defaultdict(int)
    for repository in list_repositories(token, expected_login):
        if repository.get("fork"):
            continue

        owner = repository["owner"]["login"]
        name = repository["name"]
        path = "/repos/" + urllib.parse.quote(f"{owner}/{name}", safe="/") + "/languages"
        languages, _ = github_get(path, token)
        if not isinstance(languages, dict):
            raise RuntimeError(f"GitHub returned invalid language data for {owner}/{name}.")
        for language, size in languages.items():
            totals[str(language)] += int(size)
    return dict(totals)


def render_language_list(languages: dict[str, int]) -> str:
    if not languages:
        return "*Todavía no se encontraron lenguajes en los repositorios accesibles.*"

    labels = [f"`{name.replace('`', '')}`" for name in sorted(languages, key=str.casefold)]
    return " · ".join(labels)


def update_readme(language_list: str) -> None:
    readme = README_PATH.read_text(encoding="utf-8")
    if readme.count(START_MARKER) != 1 or readme.count(END_MARKER) != 1:
        raise RuntimeError("README.md must contain exactly one language marker pair.")

    start = readme.index(START_MARKER) + len(START_MARKER)
    end = readme.index(END_MARKER, start)
    replacement = f"\n{language_list}\n"
    updated = readme[:start] + replacement + readme[end:]
    if updated != readme:
        README_PATH.write_text(updated, encoding="utf-8", newline="\n")


def main() -> int:
    token = os.environ.get("SUMMARY_CARDS_TOKEN", "").strip()
    username = os.environ.get("GITHUB_USERNAME", "").strip()
    if not token or not username:
        print("SUMMARY_CARDS_TOKEN and GITHUB_USERNAME are required.", file=sys.stderr)
        return 1

    languages = collect_languages(token, username)
    update_readme(render_language_list(languages))
    print(f"Updated the profile language list with {len(languages)} languages.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
