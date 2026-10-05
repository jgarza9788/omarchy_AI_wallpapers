"""The signed-in GitHub account, summarised for the character sheets (36, 37).

Uses the `gh` CLI's GraphQL access (whatever account `gh auth status` shows):
profile, every owned non-fork repo (stars, primary language) and the last
year's contribution calendar. Cached in .wip/github.json like the inventory;
`python3 src/github_stats.py --refresh` re-fetches and prints a summary.
load() returns None when gh is missing or not signed in, and the sheets then
simply leave the GitHub parts out.
"""
import collections
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
CACHE = ROOT / ".wip" / "github.json"
PROFILE = """query{viewer{login name createdAt followers{totalCount} following{totalCount}
  contributionsCollection{totalCommitContributions totalPullRequestContributions totalIssueContributions
    contributionCalendar{totalContributions weeks{contributionDays{date contributionCount}}}}}}"""
REPOS = """query($after:String){viewer{repositories(ownerAffiliations:OWNER,isFork:false,first:100,after:$after){
  totalCount pageInfo{hasNextPage endCursor} nodes{name stargazerCount isPrivate primaryLanguage{name}}}}}"""


def gql(query, **vars):
    cmd = ["gh", "api", "graphql", "-f", f"query={query}"]
    for k, v in vars.items():
        if v is not None:
            cmd += ["-f", f"{k}={v}"]
    return json.loads(subprocess.run(cmd, capture_output=True, text=True, check=True).stdout)["data"]["viewer"]


def collect():
    v = gql(PROFILE)
    repos, after = [], None
    while True:
        page = gql(REPOS, after=after)["repositories"]
        repos += page["nodes"]
        if not page["pageInfo"]["hasNextPage"]:
            break
        after = page["pageInfo"]["endCursor"]
    c = v["contributionsCollection"]
    days = [d["contributionCount"] for w in c["contributionCalendar"]["weeks"] for d in w["contributionDays"]]
    longest = run = 0
    for n in days:
        run = run + 1 if n else 0
        longest = max(longest, run)
    current = 0
    for n in reversed(days[:-1] if days and not days[-1] else days):   # today may not have started yet
        if not n:
            break
        current += 1
    public = [r for r in repos if not r["isPrivate"]]
    top = max(public, key=lambda r: r["stargazerCount"]) if public else None
    langs = collections.Counter(r["primaryLanguage"]["name"] for r in repos if r["primaryLanguage"])
    return {"login": v["login"], "name": v["name"], "since": v["createdAt"][:4],
            "followers": v["followers"]["totalCount"], "following": v["following"]["totalCount"],
            "repos": len(repos), "stars": sum(r["stargazerCount"] for r in repos),
            "contributions": c["contributionCalendar"]["totalContributions"],
            "commits": c["totalCommitContributions"], "prs": c["totalPullRequestContributions"],
            "issues": c["totalIssueContributions"], "longest_streak": longest, "current_streak": current,
            "calendar": days, "top_repo": [top["name"], top["stargazerCount"]] if top else None,
            "languages": langs.most_common(8)}


def load(refresh=False):
    if refresh or not CACHE.exists():
        try:
            data = collect()
        except (OSError, subprocess.CalledProcessError, KeyError, json.JSONDecodeError, TypeError):
            return json.loads(CACHE.read_text()) if CACHE.exists() else None
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps(data))
    return json.loads(CACHE.read_text())


if __name__ == "__main__":
    g = load(refresh="--refresh" in sys.argv)
    if not g:
        sys.exit("no GitHub data (is `gh auth status` signed in?)")
    print(f"@{g['login']} since {g['since']}: {g['repos']} repos, {g['stars']} stars, {g['followers']} followers")
    print(f"{g['contributions']} contributions this year ({g['commits']} commits, {g['prs']} PRs, {g['issues']} issues), "
          f"longest streak {g['longest_streak']} days, current {g['current_streak']}")
    print("top repo:", g["top_repo"], " languages:", g["languages"])
