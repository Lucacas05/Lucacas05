"""
GitHub Profile README Updater
Fetches GitHub stats via GraphQL API and updates the neofetch-style SVGs.
Adapted from github.com/Andrew6rant/Andrew6rant
"""

import os
import time
import hashlib
import datetime
import requests
from dateutil.relativedelta import relativedelta
from lxml import etree

# ── Configuration ──────────────────────────────────────────────────────────────
BIRTHDAY = "2005-06-06"
USERNAME = os.environ.get("USER_NAME", "Lucacas05")
ACCESS_TOKEN = os.environ.get("ACCESS_TOKEN", "")
GRAPHQL_URL = "https://api.github.com/graphql"

OWNER_ID = ""
QUERY_COUNT = 0
HEADERS = {"Authorization": f"Bearer {ACCESS_TOKEN}"}


# ── GraphQL helpers ────────────────────────────────────────────────────────────
def query_graphql(query, variables=None):
    global QUERY_COUNT
    QUERY_COUNT += 1
    payload = {"query": query}
    if variables:
        payload["variables"] = variables
    resp = requests.post(GRAPHQL_URL, json=payload, headers=HEADERS)
    if resp.status_code == 200:
        data = resp.json()
        if "errors" in data:
            print(f"  GraphQL error: {data['errors']}")
        return data
    if resp.status_code == 403:
        raise Exception("GitHub API rate limit hit (403). Try again later.")
    raise Exception(f"Query failed: {resp.status_code} — {resp.text[:200]}")


def user_getter(username):
    result = query_graphql('''
    query($login: String!) {
        user(login: $login) { id createdAt }
    }''', {"login": username})
    user = result["data"]["user"]
    return user["id"], user["createdAt"]


def daily_readme(birthday):
    diff = relativedelta(datetime.date.today(),
                         datetime.datetime.strptime(birthday, "%Y-%m-%d").date())
    return f"{diff.years} years, {diff.months} months, {diff.days} days"


# ── Stats fetchers ─────────────────────────────────────────────────────────────
def follower_getter(username):
    result = query_graphql('''
    query($login: String!) {
        user(login: $login) { followers { totalCount } }
    }''', {"login": username})
    return result["data"]["user"]["followers"]["totalCount"]


def graph_repos_stars(count_type, owner_affiliation, cursor=None):
    result = query_graphql('''
    query($login: String!, $aff: [RepositoryAffiliation]!, $after: String) {
        user(login: $login) {
            repositories(first: 100, after: $after, ownerAffiliations: $aff) {
                totalCount
                edges { node { stargazerCount } }
                pageInfo { hasNextPage endCursor }
            }
        }
    }''', {"login": USERNAME, "aff": owner_affiliation, "after": cursor})
    repos = result["data"]["user"]["repositories"]
    if count_type == "repos":
        return repos["totalCount"]
    stars = sum(e["node"]["stargazerCount"] for e in repos["edges"])
    if repos["pageInfo"]["hasNextPage"]:
        stars += graph_repos_stars("stars", owner_affiliation,
                                   repos["pageInfo"]["endCursor"])
    return stars


# ── Lines of code ──────────────────────────────────────────────────────────────
def loc_query(owner_affiliation, cursor=None, edges=None):
    if edges is None:
        edges = []
    result = query_graphql('''
    query($login: String!, $aff: [RepositoryAffiliation]!, $after: String) {
        user(login: $login) {
            repositories(first: 60, after: $after, ownerAffiliations: $aff) {
                edges {
                    node {
                        nameWithOwner
                        defaultBranchRef {
                            target { ... on Commit { history { totalCount } } }
                        }
                    }
                }
                pageInfo { hasNextPage endCursor }
            }
        }
    }''', {"login": USERNAME, "aff": owner_affiliation, "after": cursor})
    repos = result["data"]["user"]["repositories"]
    edges.extend(repos["edges"])
    if repos["pageInfo"]["hasNextPage"]:
        return loc_query(owner_affiliation, repos["pageInfo"]["endCursor"], edges)
    return edges


def recursive_loc(owner, repo_name, data, cursor=None):
    result = query_graphql('''
    query($owner: String!, $name: String!, $after: String) {
        repository(owner: $owner, name: $name) {
            defaultBranchRef {
                target { ... on Commit {
                    history(first: 100, after: $after) {
                        edges { node {
                            author { user { id } }
                            additions deletions
                        }}
                        pageInfo { hasNextPage endCursor }
                    }
                }}
            }
        }
    }''', {"owner": owner, "name": repo_name, "after": cursor})

    branch = result["data"]["repository"].get("defaultBranchRef")
    if not branch:
        return data
    history = branch["target"]["history"]
    for edge in history["edges"]:
        node = edge["node"]
        if (node["author"].get("user") and
                node["author"]["user"]["id"] == OWNER_ID):
            data["additions"] += node["additions"]
            data["deletions"] += node["deletions"]
            data["my_commits"] += 1
    if history["pageInfo"]["hasNextPage"]:
        return recursive_loc(owner, repo_name, data,
                             history["pageInfo"]["endCursor"])
    return data


def cache_builder(edges):
    filename = f"cache/{hashlib.sha256(USERNAME.encode()).hexdigest()}.txt"
    # Read existing cache
    cache = {}
    if os.path.exists(filename):
        with open(filename, "r") as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) == 5:
                    cache[parts[0]] = list(map(int, parts[1:]))

    new_cache = {}
    total_add, total_del = 0, 0
    was_cached = True

    for edge in edges:
        node = edge["node"]
        if node["defaultBranchRef"] is None:
            continue
        nwo = node["nameWithOwner"]
        owner, repo = nwo.split("/")
        total_commits = node["defaultBranchRef"]["target"]["history"]["totalCount"]
        rh = hashlib.sha256(nwo.encode()).hexdigest()[:8]

        if rh in cache and cache[rh][0] == total_commits:
            new_cache[rh] = cache[rh]
        else:
            was_cached = False
            data = {"additions": 0, "deletions": 0, "my_commits": 0}
            try:
                data = recursive_loc(owner, repo, data)
            except Exception as e:
                print(f"  Error on {nwo}: {e}")
            new_cache[rh] = [total_commits, data["my_commits"],
                             data["additions"], data["deletions"]]

        total_add += new_cache[rh][2]
        total_del += new_cache[rh][3]

    with open(filename, "w") as f:
        for rh, vals in new_cache.items():
            f.write(f"{rh} {' '.join(map(str, vals))}\n")

    return total_add, total_del, total_add - total_del, was_cached


def commit_counter():
    filename = f"cache/{hashlib.sha256(USERNAME.encode()).hexdigest()}.txt"
    total = 0
    if os.path.exists(filename):
        with open(filename, "r") as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) == 5:
                    total += int(parts[1])  # my_commits
    return total


# ── SVG updater ────────────────────────────────────────────────────────────────
def svg_overwrite(filename, **kwargs):
    tree = etree.parse(filename)
    root = tree.getroot()

    def find_and_replace(element_id, new_text):
        els = root.xpath(f'//*[@id="{element_id}"]')
        if els:
            els[0].text = str(new_text)
        else:
            print(f"  Warning: element '{element_id}' not found in {filename}")

    for key, value in kwargs.items():
        find_and_replace(key, value)

    tree.write(filename, xml_declaration=True, encoding="UTF-8")


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    global OWNER_ID
    t0 = time.time()
    print(f"Updating profile for {USERNAME}...")

    # User ID
    OWNER_ID, _ = user_getter(USERNAME)
    print(f"  ID: {OWNER_ID}")

    # Age
    age = daily_readme(BIRTHDAY)
    print(f"  Uptime: {age}")

    # Lines of code
    print("  Counting lines of code...")
    all_edges = []
    for aff in [["OWNER"], ["COLLABORATOR"], ["ORGANIZATION_MEMBER"]]:
        all_edges.extend(loc_query(aff))
    additions, deletions, net_loc, cached = cache_builder(all_edges)
    print(f"  LOC: {net_loc:,} ({additions:,}++ {deletions:,}--)"
          f" {'(cached)' if cached else '(updated)'}")

    # Commits
    commits = commit_counter()
    print(f"  Commits: {commits:,}")

    # Stars & repos
    stars = graph_repos_stars("stars", ["OWNER"])
    repos = graph_repos_stars("repos", ["OWNER"])
    contrib = repos
    for aff in [["COLLABORATOR"], ["ORGANIZATION_MEMBER"]]:
        contrib += graph_repos_stars("repos", aff)
    print(f"  Stars: {stars} | Repos: {repos} (Contributed: {contrib})")

    # Followers
    followers = follower_getter(USERNAME)
    print(f"  Followers: {followers}")

    # Update SVGs
    fmt = lambda n: f"{n:,}"
    data = dict(
        age_data=age,
        repo_data=fmt(repos),
        contrib_data=fmt(contrib),
        star_data=fmt(stars),
        commit_data=fmt(commits),
        follower_data=fmt(followers),
        loc_data=fmt(net_loc),
        loc_add=fmt(additions),
        loc_del=fmt(deletions),
    )
    for svg in ["light_mode.svg", "dark_mode.svg"]:
        svg_overwrite(svg, **data)
        print(f"  Updated {svg}")

    print(f"\nDone in {time.time() - t0:.1f}s ({QUERY_COUNT} API calls)")


if __name__ == "__main__":
    main()
