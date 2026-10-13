"""Create carousel drafts in Buffer (https://developers.buffer.com)."""

from __future__ import annotations

from datetime import datetime
import json
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

# Per-service metadata Buffer requires for an image post.
SERVICE_METADATA = {
    "facebook": {"facebook": {"type": "post"}},
    "instagram": {"instagram": {"type": "post", "shouldShareToFeed": True}},
}


class BufferError(Exception):
    """Buffer rejected the request."""


def create_draft(
    api_key: str,
    channel_id: str,
    service: str,
    text: str,
    images: list[tuple[str, str]],
    due_at: datetime,
) -> str:
    """Save a multi-image post as a draft and return its Buffer post id.

    `images` is a list of (public URL, alt text); several images become a carousel.
    `due_at` pre-fills the publish time shown when the draft is approved.
    """
    post_input = {
        "channelId": channel_id,
        "text": text,
        "schedulingType": "automatic",
        "mode": "customScheduled",
        "dueAt": due_at.isoformat(),
        "saveToDraft": True,
        "assets": [{"image": {"url": url, "metadata": {"altText": alt}}} for url, alt in images],
        "metadata": SERVICE_METADATA[service],
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
