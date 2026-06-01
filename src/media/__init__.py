"""Media adapters — URL/YouTube/document/image extraction.

Importing ``src.media`` registers all bundled adapters via their
``@media_adapter`` decorators so ``find_adapter`` can resolve them.
"""

# Force-import adapters so their @media_adapter decorators run.
from src.media.adapters import document, image, web  # noqa: F401
from src.media.base import MediaAdapter, MediaExtractResult
from src.media.registry import find_adapter, list_adapters, media_adapter

__all__ = [
    "MediaAdapter",
    "MediaExtractResult",
    "find_adapter",
    "list_adapters",
    "media_adapter",
]
