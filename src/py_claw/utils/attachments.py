"""
Attachments utility for handling message attachments.

Provides types and utilities for managing file attachments and pasted content
in messages, aligning with TypeScript reference ClaudeCode-main/src/utils/attachments.ts.

Handles:
- Text and image paste handling
- Attachment slot tracking
- File size limits and token estimation
"""
from __future__ import annotations

import base64
import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


# Token estimation: roughly 4 characters per token
CHARS_PER_TOKEN = 4

# Default limits
DEFAULT_MAX_FILE_SIZE_MB = 10
MAX_IMAGE_DIMENSION = 4096
MAX_IMAGE_DIMENSION_LG = 4096


class ImageDimensions(BaseModel):
    """Image dimensions for coordinate mapping."""

    width: int
    height: int


@dataclass
class PastedContent:
    """Represents pasted content (text or image).

    Corresponds to PastedContent in TS attachments.ts.
    """

    id: int  # Sequential numeric ID
    type: str  # 'text' or 'image'
    content: str
    media_type: str | None = None  # e.g., 'image/png', 'image/jpeg'
    filename: str | None = None  # Display name for images
    dimensions: ImageDimensions | None = None
    source_path: str | None = None  # Original file path for dragged images


@dataclass
class HistoryEntry:
    """A history entry with display text and pasted contents."""

    display: str
    pasted_contents: dict[int, PastedContent] = field(default_factory=dict)


@dataclass
class SerializedStructuredHistoryEntry:
    """Serialized form of history entry for storage."""

    display: str
    pasted_contents: dict[int, PastedContent] | None = None
    pasted_text: str | None = None


# Content type constants
CONTENT_TYPE_TEXT = "text"
CONTENT_TYPE_IMAGE = "image"


class AttachmentError(Exception):
    """Base exception for attachment-related errors."""

    pass


class FileTooLargeError(AttachmentError):
    """Raised when a file exceeds size limits."""

    def __init__(self, filename: str, size_mb: float, max_mb: float) -> None:
        self.filename = filename
        self.size_mb = size_mb
        self.max_mb = max_mb
        super().__init__(f"File '{filename}' is {size_mb:.1f}MB, exceeds limit of {max_mb}MB")


class MaxTokenExceededError(AttachmentError):
    """Raised when content exceeds token budget."""

    def __init__(self, content: str, tokens: int, max_tokens: int) -> None:
        self.content = content
        self.tokens = tokens
        self.max_tokens = max_tokens
        super().__init__(f"Content is {tokens} tokens, exceeds limit of {max_tokens}")


def count_tokens(text: str) -> int:
    """Estimate token count for text content.

    Args:
        text: Text content to count

    Returns:
        Estimated token count
    """
    return len(text) // CHARS_PER_TOKEN


def is_valid_image_type(media_type: str | None) -> bool:
    """Check if a media type is a valid image type.

    Args:
        media_type: The MIME type to check

    Returns:
        True if it's a valid image type
    """
    if not media_type:
        return False
    return media_type.startswith("image/") and media_type not in (
        "image/gif",
        "image/webp",  # Some terminals don't support these well
    )


def get_image_dimensions(image_path: Path) -> ImageDimensions | None:
    """Get dimensions of an image file.

    Args:
        image_path: Path to the image file

    Returns:
        ImageDimensions or None if unable to determine
    """
    try:
        # Try using Pillow if available
        from PIL import Image

        with Image.open(image_path) as img:
            return ImageDimensions(width=img.width, height=img.height)
    except ImportError:
        # Pillow not available, return None
        return None
    except Exception:
        return None


def resize_image_if_needed(
    image_path: Path,
    max_dimension: int = MAX_IMAGE_DIMENSION,
) -> tuple[Path, ImageDimensions]:
    """Resize an image if it exceeds maximum dimensions.

    Args:
        image_path: Path to the image
        max_dimension: Maximum width or height

    Returns:
        Tuple of (path to resized image or original, resulting dimensions)
    """
    try:
        from PIL import Image

        with Image.open(image_path) as img:
            width, height = img.size
            if width <= max_dimension and height <= max_dimension:
                return image_path, ImageDimensions(width=width, height=height)

            # Calculate resize ratio
            ratio = min(max_dimension / width, max_dimension / height)
            new_width = int(width * ratio)
            new_height = int(height * ratio)

            # Resize with high quality
            resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            output_path = image_path.parent / f"{image_path.stem}_resized{image_path.suffix}"
            resized.save(output_path, quality=95)

            return output_path, ImageDimensions(width=new_width, height=new_height)
    except ImportError:
        # Pillow not available, return original
        return image_path, ImageDimensions(width=0, height=0)
    except Exception:
        return image_path, ImageDimensions(width=0, height=0)


def encode_image_base64(image_path: Path) -> str:
    """Encode an image file as base64.

    Args:
        image_path: Path to the image

    Returns:
        Base64-encoded image content
    """
    return base64.b64encode(image_path.read_bytes()).decode("utf-8")


def get_file_size_mb(file_path: Path) -> float:
    """Get file size in megabytes.

    Args:
        file_path: Path to the file

    Returns:
        File size in MB
    """
    return file_path.stat().st_size / (1024 * 1024)


def validate_file_size(
    file_path: Path,
    max_size_mb: float = DEFAULT_MAX_FILE_SIZE_MB,
) -> None:
    """Validate that a file doesn't exceed size limits.

    Args:
        file_path: Path to the file
        max_size_mb: Maximum allowed size in MB

    Raises:
        FileTooLargeError: If file exceeds size limit
    """
    size_mb = get_file_size_mb(file_path)
    if size_mb > max_size_mb:
        raise FileTooLargeError(file_path.name, size_mb, max_size_mb)


def get_content_type_from_extension(file_path: Path) -> str:
    """Get MIME type from file extension.

    Args:
        file_path: Path to the file

    Returns:
        MIME type string
    """
    ext = file_path.suffix.lower()
    type_map = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".bmp": "image/bmp",
        ".svg": "image/svg+xml",
        ".txt": "text/plain",
        ".md": "text/markdown",
        ".py": "text/x-python",
        ".js": "text/javascript",
        ".ts": "text/typescript",
        ".json": "application/json",
        ".xml": "application/xml",
        ".html": "text/html",
        ".css": "text/css",
    }
    return type_map.get(ext, "application/octet-stream")


def parse_attachment_reference(text: str) -> list[str]:
    """Parse attachment references from text (e.g., @file:path).

    Args:
        text: Text that may contain attachment references

    Returns:
        List of file paths mentioned as attachments
    """
    pattern = r"@file:([^\s]+)"
    return re.findall(pattern, text)


def format_attachment_for_display(
    attachment: PastedContent,
    include_metadata: bool = True,
) -> str:
    """Format an attachment for display in a message.

    Args:
        attachment: The attachment to format
        include_metadata: Whether to include metadata like dimensions

    Returns:
        Formatted string representation
    """
    if attachment.type == CONTENT_TYPE_IMAGE:
        parts = [f"[Image: {attachment.filename or 'untitled'}]"]
        if include_metadata and attachment.dimensions:
            parts.append(f"{attachment.dimensions.width}x{attachment.dimensions.height}")
        if attachment.media_type:
            parts.append(f"({attachment.media_type})")
        return " ".join(parts)
    else:
        return f"[Text: {len(attachment.content)} chars]"


def estimate_attachment_tokens(
    attachment: PastedContent,
    chars_per_token: int = CHARS_PER_TOKEN,
) -> int:
    """Estimate token count for an attachment.

    Args:
        attachment: The attachment to estimate
        chars_per_token: Characters per token ratio

    Returns:
        Estimated token count
    """
    if attachment.type == CONTENT_TYPE_TEXT:
        return len(attachment.content) // chars_per_token
    elif attachment.type == CONTENT_TYPE_IMAGE:
        # Image tokens: base + per-dimension
        # Rough estimate: 1000 base + pixels / 750
        if attachment.dimensions:
            pixels = attachment.dimensions.width * attachment.dimensions.height
            return 1000 + pixels // 750
        return 1000
    return 0


def truncate_content_to_tokens(
    content: str,
    max_tokens: int,
    chars_per_token: int = CHARS_PER_TOKEN,
) -> str:
    """Truncate content to fit within token budget.

    Args:
        content: Text content to truncate
        max_tokens: Maximum tokens allowed
        chars_per_token: Characters per token ratio

    Returns:
        Truncated content
    """
    max_chars = max_tokens * chars_per_token
    if len(content) <= max_chars:
        return content
    return content[:max_chars]


# Global state for managing pasted content
_pasted_content_counter = 0
_pasted_content_store: dict[int, PastedContent] = {}


def create_pasted_content(
    content: str,
    content_type: str = CONTENT_TYPE_TEXT,
    media_type: str | None = None,
    filename: str | None = None,
    source_path: str | None = None,
) -> PastedContent:
    """Create a new pasted content entry.

    Args:
        content: The content (text or base64 image)
        content_type: Type of content ('text' or 'image')
        media_type: MIME type for images
        filename: Display name for images
        source_path: Original file path for dragged images

    Returns:
        Created PastedContent with assigned ID
    """
    global _pasted_content_counter, _pasted_content_store

    _pasted_content_counter += 1
    pasted = PastedContent(
        id=_pasted_content_counter,
        type=content_type,
        content=content,
        media_type=media_type,
        filename=filename,
        source_path=source_path,
    )
    _pasted_content_store[_pasted_content_counter] = pasted
    return pasted


def get_pasted_content(content_id: int) -> PastedContent | None:
    """Get pasted content by ID.

    Args:
        content_id: The pasted content ID

    Returns:
        PastedContent or None if not found
    """
    return _pasted_content_store.get(content_id)


def clear_pasted_content(content_id: int) -> None:
    """Remove pasted content from store.

    Args:
        content_id: The pasted content ID to remove
    """
    _pasted_content_store.pop(content_id, None)


def get_image_paste_ids(text: str) -> list[int]:
    """Extract image paste IDs from text.

    Args:
        text: Text that may contain image paste references

    Returns:
        List of paste IDs found in text
    """
    # Match patterns like [image:123] or @image:123
    patterns = [
        r"\[image:(\d+)\]",
        r"@image:(\d+)",
        r"image-paste-(\d+)",
    ]
    ids: set[int] = set()
    for pattern in patterns:
        matches = re.findall(pattern, text)
        for match in matches:
            try:
                ids.add(int(match))
            except ValueError:
                pass
    return sorted(ids)


def is_valid_image_paste(text: str) -> bool:
    """Check if text represents a valid image paste reference.

    Args:
        text: Text to check

    Returns:
        True if text contains a valid image paste reference
    """
    return len(get_image_paste_ids(text)) > 0
