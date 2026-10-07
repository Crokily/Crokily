#!/usr/bin/env python3
"""Refresh the "Recent releases" block in README.md.

The banner and the project cards are live SVGs served by coly.cc, so their numbers never
live in this file. Runs in GitHub Actions (see .github/workflows/update.yml) with
GITHUB_TOKEN, or locally with `GITHUB_TOKEN=$(gh auth token) python3 build_readme.py`.
Standard library only.
"""
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone

OWNER = "Crokily"
TOKEN = os.environ.get("GITHUB_TOKEN", "")
README = os.path.join(os.path.dirname(os.path.abspath(__file__)), "README.md")
LIMIT = 8


def graphql(query, variables):
    data = json.dumps({"query": query, "variables": variables}).encode()
    req = urllib.request.Request(
        "https://api.github.com/graphql", data=data,
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json", "User-Agent": "Crokily profile README"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)["data"]


def releases_block():
    q = """
    query($login:String!, $after:String) {
      user(login:$login) {
        repositories(first:100, after:$after, ownerAffiliations:OWNER, privacy:PUBLIC, isFork:false) {
          pageInfo { hasNextPage endCursor }
          nodes {
            name url
            releases(first:3, orderBy:{field:CREATED_AT, direction:DESC}) {
              nodes { tagName url publishedAt isDraft }
            }
          }
        }
      }
    }"""
    items, after = [], None
    while True:
        d = graphql(q, {"login": OWNER, "after": after})["user"]["repositories"]
        for repo in d["nodes"]:
            for rel in repo["releases"]["nodes"]:
                if rel["isDraft"] or not rel["publishedAt"]:
                    continue
                items.append((rel["publishedAt"], repo["name"], rel["tagName"], rel["url"]))
        if not d["pageInfo"]["hasNextPage"]:
            break
        after = d["pageInfo"]["endCursor"]
    items.sort(reverse=True)
    out, seen = [], set()
    for published, repo, tag, url in items:
        day = datetime.fromisoformat(published.replace("Z", "+00:00")).astimezone(timezone.utc).date()
        if (repo, day) in seen:  # several tags on one day: keep the latest only
            continue
        seen.add((repo, day))
        out.append(f"- [{repo} {tag}]({url}) · {day}")
        if len(out) >= LIMIT:
            break
    return "\n".join(out)


def replace_block(text, marker, body):
    pattern = re.compile(rf"(<!-- {marker} starts -->\n)(.*?)(<!-- {marker} ends -->)", re.S)
    if not pattern.search(text):
        sys.exit(f"marker '{marker}' not found in README")
    return pattern.sub(lambda m: f"{m.group(1)}{body}\n{m.group(3)}", text)


if __name__ == "__main__":
    if not TOKEN:
        sys.exit("GITHUB_TOKEN is required")
    text = open(README, encoding="utf-8").read()
    new = replace_block(text, "releases", releases_block())
    if new != text:
        open(README, "w", encoding="utf-8").write(new)
        print("README updated")
    else:
        print("no change")
