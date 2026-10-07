#!/usr/bin/env python3
"""Refresh the two generated blocks in README.md: "Building now" numbers and "Recent releases".

Runs in GitHub Actions (see .github/workflows/update.yml) with GITHUB_TOKEN, or locally with
`GITHUB_TOKEN=$(gh auth token) python3 build_readme.py`. Standard library only.
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

# repo, display name, blurb, npm package whose past-year downloads go after the stars (or None)
BUILDING = [
    ("Crokily/pi-discord-gateway", "Piscord", "Discord gateway for the pi coding agent.", "piscord"),
    ("Crokily/herdr-lazygit", "herdr-lazygit", "lazygit in a herdr sidebar: one key to open, one to commit with AI.", None),
    ("InvolutionHell/involutionhell", "Involution Hell", "a student-led learning community, co-founded 2025.", None),
]


def get(url, headers=None):
    req = urllib.request.Request(url, headers={"User-Agent": "Crokily profile README", **(headers or {})})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def gh(path):
    h = {"Accept": "application/vnd.github+json"}
    if TOKEN:
        h["Authorization"] = f"Bearer {TOKEN}"
    return get(f"https://api.github.com{path}", h)


def graphql(query, variables):
    data = json.dumps({"query": query, "variables": variables}).encode()
    req = urllib.request.Request(
        "https://api.github.com/graphql", data=data,
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json", "User-Agent": "Crokily profile README"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)["data"]


def npm_year(pkg):
    d = get(f"https://api.npmjs.org/downloads/point/last-year/{pkg}")
    return d.get("downloads", 0)


def building_block():
    lines = []
    for full, name, blurb, pkg in BUILDING:
        repo = gh(f"/repos/{full}")
        facts = [f"{repo['stargazers_count']:,} stars"]
        if pkg:
            facts.append(f"{npm_year(pkg):,} installs in the past year")
        if full == "InvolutionHell/involutionhell":
            contributors = gh(f"/repos/{full}/contributors?per_page=100&anon=0")
            facts.append(f"{len(contributors)} contributors")
        lines.append(f"- **[{name}](https://github.com/{full})** — {blurb} {', '.join(facts)}.")
    return "\n".join(lines)


def releases_block(limit=8):
    if not TOKEN:
        return None
    q = """
    query($login:String!, $after:String) {
      user(login:$login) {
        repositories(first:100, after:$after, ownerAffiliations:OWNER, privacy:PUBLIC, isFork:false) {
          pageInfo { hasNextPage endCursor }
          nodes {
            name url
            releases(first:3, orderBy:{field:CREATED_AT, direction:DESC}) {
              nodes { name tagName url publishedAt isDraft isPrerelease }
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
        out.append(f"[{repo} {tag}]({url}) - {day}")
        if len(out) >= limit:
            break
    return "\n\n".join(out)


def replace_block(text, marker, body):
    pattern = re.compile(rf"(<!-- {marker} starts -->\n)(.*?)(<!-- {marker} ends -->)", re.S)
    if not pattern.search(text):
        sys.exit(f"marker '{marker}' not found in README")
    return pattern.sub(lambda m: f"{m.group(1)}{body}\n{m.group(3)}", text)


if __name__ == "__main__":
    text = open(README, encoding="utf-8").read()
    new = replace_block(text, "building", building_block())
    rel = releases_block()
    if rel is not None:
        new = replace_block(new, "releases", rel)
    if new != text:
        open(README, "w", encoding="utf-8").write(new)
        print("README updated")
    else:
        print("no change")
