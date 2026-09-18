"""Primary-display PNG capture via Pillow."""
from __future__ import annotations

import io


def grab_primary(_scope: str = "primary") -> bytes:
    from PIL import ImageGrab

    image = ImageGrab.grab()
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()
