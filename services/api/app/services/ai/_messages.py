"""Shared chat-message shaping for AI providers.

The OpenAI-compatible chat API accepts either a plain string or a list of content
parts for the user turn. When an image is attached (vision), the user turn becomes
a multimodal list: a text part plus an ``image_url`` part carrying a base64 data
URI. Both `OllamaProvider` and `CloudAiProvider` build the user turn identically,
so the logic lives here rather than being duplicated per provider.
"""
from __future__ import annotations

import base64


def build_user_content(user: str, image: bytes | None, image_media_type: str) -> object:
    """Return the chat ``content`` for the user turn.

    Plain string when there's no image; otherwise a ``[text, image_url]`` list with
    the image inlined as a ``data:`` URI (what the OpenAI-compatible vision API
    expects).
    """
    if image is None:
        return user
    b64 = base64.b64encode(image).decode("ascii")
    return [
        {"type": "text", "text": user},
        {
            "type": "image_url",
            "image_url": {"url": f"data:{image_media_type};base64,{b64}"},
        },
    ]
