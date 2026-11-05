"""Minimal GitHub REST client for the review workflow (standard library only).

Reads the token from GH_TOKEN (or GITHUB_TOKEN) and the API root from
GITHUB_API_URL, as set in GitHub Actions.
"""
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

API = os.environ.get("GITHUB_API_URL", "https://api.github.com")


class GitHubError(Exception):
    def __init__(self, status, message, body=None):
        super().__init__(f"GitHub API {status}: {message}")
        self.status = status
        self.body = body


def request(method, path, data=None, params=None, accept="application/vnd.github+json"):
    url = path if path.startswith("http") else f"{API}/{path.lstrip('/')}"
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    headers = {"Accept": accept, "X-GitHub-Api-Version": "2022-11-28",
               "User-Agent": "homework-review"}
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    body = None
    if data is not None:
        body = json.dumps(data).encode()
        headers["Content-Type"] = "application/json"
    for attempt in range(3):
        req = urllib.request.Request(url, data=body, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read()
                link = resp.headers.get("Link", "")
                return (json.loads(raw) if raw and "json" in resp.headers.get("Content-Type", "") else raw), link
        except urllib.error.HTTPError as e:
            raw = e.read()
            try:
                parsed = json.loads(raw)
            except ValueError:
                parsed = None
            if e.code >= 500 and attempt < 2:
                time.sleep(2 * (attempt + 1))
                continue
            msg = parsed.get("message", "") if isinstance(parsed, dict) else raw[:200]
            raise GitHubError(e.code, msg, parsed) from None
        except urllib.error.URLError:
            if attempt < 2:
                time.sleep(2 * (attempt + 1))
                continue
            raise


def get(path, **params):
    return request("GET", path, params=params or None)[0]


def get_all(path, limit=3000, **params):
    """GET every page of a list endpoint (up to `limit` items)."""
    params.setdefault("per_page", 100)
    out, url, first = [], path, True
    while url and len(out) < limit:
        data, link = request("GET", url, params=params if first else None)
        first = False
        out += data
        url = None
        for part in link.split(","):
            if 'rel="next"' in part:
                url = part[part.index("<") + 1:part.index(">")]
    return out[:limit]


def post(path, data):
    return request("POST", path, data=data)[0]


def patch(path, data):
    return request("PATCH", path, data=data)[0]


def put(path, data):
    return request("PUT", path, data=data)[0]


def delete(path):
    return request("DELETE", path)[0]
