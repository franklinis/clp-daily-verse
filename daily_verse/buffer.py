"""Create drafts in Buffer (https://developers.buffer.com)."""

from __future__ import annotations

from datetime import datetime
import json
from typing import Any
import urllib.error
import urllib.request

API_URL = "https://api.buffer.com"

CREATE_POST = """
mutation CreateDraft($input: CreatePostInput!) {
  createPost(input: $input) {
    ... on PostActionSuccess { post { id status } }
    ... on MutationError { message }
  }
}
"""


class BufferError(Exception):
    """Buffer rejected the request."""


def carousel_metadata(service: str) -> dict[str, Any]:
    """Settings for a multi-image feed post."""
    return {
        "facebook": {"facebook": {"type": "post"}},
        "instagram": {"instagram": {"type": "post", "shouldShareToFeed": True}},
    }[service]


def video_metadata(service: str, title: str, ai_voice: bool = False) -> dict[str, Any]:
    """Settings for a Reel (Facebook, Instagram) or a YouTube Short.

    A computer-generated reading voice is disclosed as AI-generated where
    Buffer supports the label (Instagram, YouTube).
    """
    return {
        "facebook": {"facebook": {"type": "reel"}},
        "instagram": {"instagram": {"type": "reel", "shouldShareToFeed": True, "isAiGenerated": ai_voice}},
        # 22 = People & Blogs. Vertical videos under three minutes become Shorts.
        "youtube": {"youtube": {"title": title, "categoryId": "22", "privacy": "public", "madeForKids": False,
                                "isAiGenerated": ai_voice}},
    }[service]


def create_draft(
    api_key: str,
    channel_id: str,
    text: str,
    assets: list[dict[str, Any]],
    metadata: dict[str, Any],
    due_at: datetime,
) -> str:
    """Save a post as a draft and return its Buffer post id.

    `due_at` pre-fills the publish time shown when the draft is approved.
    """
    post_input = {
        "channelId": channel_id,
        "text": text,
        "schedulingType": "automatic",
        "mode": "customScheduled",
        "dueAt": due_at.isoformat(),
        "saveToDraft": True,
        "assets": assets,
        "metadata": metadata,
    }
    request = urllib.request.Request(
        API_URL,
        data=json.dumps({"query": CREATE_POST, "variables": {"input": post_input}}).encode(),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            body = json.load(response)
    except urllib.error.HTTPError as err:
        raise BufferError(f"Buffer returned HTTP {err.code}: {err.read().decode(errors='replace')}") from err

    if body.get("errors"):
        raise BufferError("; ".join(e.get("message", str(e)) for e in body["errors"]))
    result = (body.get("data") or {}).get("createPost") or {}
    if "post" not in result:
        raise BufferError(result.get("message", f"Unexpected response: {body}"))
    return result["post"]["id"]
