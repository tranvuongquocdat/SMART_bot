import src.media.adapters  # noqa: F401  (kích hoạt self-register)
from src.media.registry import find_adapter, list_adapters


def test_adapters_registered():
    kinds = set().union(*(a.supports for a in list_adapters()))
    assert {"url", "youtube", "tiktok", "pdf", "docx", "xlsx", "txt", "image"} <= kinds


def test_find_adapter_for_url():
    a = find_adapter(url="https://example.com/article")
    assert a.__class__.__name__ == "WebExtractor"
