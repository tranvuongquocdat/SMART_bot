"""Pure text helpers — no I/O."""


def full_name(user: dict) -> str:
    """Compose 'first_name last_name' from a provider-supplied user dict.

    Handles missing fields. Used by any channel that exposes split
    first/last name fields (Telegram today; other providers may use it later).
    """
    return (f"{user.get('first_name', '')} {user.get('last_name', '')}").strip()
