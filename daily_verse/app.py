"""Send each day's posts to the church app for approval, instead of Buffer drafts.

Switched on with the repo variable POST_TARGET=app. The church app
(https://app.christ-livingpetra.de) shows the day to its social media
approvers, who approve it with one tap; the app then sends the posts to
Buffer exactly as prepared here. Days nobody approves aren't posted.

No secret is needed: the workflow asks GitHub for an identity token
(permission `id-token: write`, audience "clp-app") and the app checks it.
"""

from __future__ import annotations

from datetime import date
import json
import os
import urllib.error
import urllib.parse
import urllib.request

AUDIENCE = "clp-app"


class AppError(Exception):
    """The church app refused the request."""


def enabled() -> bool:
    return os.environ.get("POST_TARGET", "buffer").strip().lower() == "app"


def app_url() -> str:
    return os.environ.get("APP_URL", "https://app.christ-livingpetra.de").rstrip("/")


def batch_key(day: date) -> str:
    return f"daily-verse:{day.isoformat()}"


def review_url(day: date) -> str:
    """The day's approval page in the app."""
    return f"{app_url()}/en/admin/social/batch/{urllib.parse.quote(batch_key(day), safe='')}"


def _identity_token() -> str:
    url = os.environ.get("ACTIONS_ID_TOKEN_REQUEST_URL")
    token = os.environ.get("ACTIONS_ID_TOKEN_REQUEST_TOKEN")
    if not url or not token:
        raise AppError("No GitHub identity token: the workflow needs `permissions: id-token: write`")
    request = urllib.request.Request(f"{url}&audience={AUDIENCE}", headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)["value"]


def _call(method: str, path: str, body: dict | None = None) -> dict:
    request = urllib.request.Request(
        f"{app_url()}{path}",
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Bearer {_identity_token()}", "Content-Type": "application/json"},
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.load(response)
    except urllib.error.HTTPError as err:
        raise AppError(f"Church app returned HTTP {err.code}: {err.read().decode(errors='replace')[:500]}") from err


def send_day(day: date, title: str, due_at: str, expires_at: str, posts: list[dict]) -> bool:
    """Send (or update) a day's posts; returns True if the day is already approved (then nothing changed)."""
    result = _call("POST", "/api/social/inbox", {
        "batch": batch_key(day), "title": title, "dueAt": due_at, "expiresAt": expires_at, "posts": posts,
    })
    return bool(result.get("approved"))


def approved(day: date) -> bool:
    return bool(_call("GET", f"/api/social/inbox?batch={urllib.parse.quote(batch_key(day))}").get("approved"))


def fetch_picks() -> list[dict]:
    """The church's upcoming verse picks from the app: [{"date", "reference", "theme"}]."""
    return list(_call("GET", "/api/social/verse-picks").get("picks", []))


def send_pick_results(results: list[dict]) -> None:
    """What this run made of each pick: {"date", "found"} or {"date", "problem"}."""
    if results:
        _call("POST", "/api/social/verse-picks", {"results": results})
