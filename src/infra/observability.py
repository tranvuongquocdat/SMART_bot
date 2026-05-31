import logging

import structlog

REDACT_FIELDS = {"text", "media_text", "sender_name", "credentials_blob", "auth_blob", "api_key"}


def _redact(_, __, event_dict):
    for k in list(event_dict):
        if k in REDACT_FIELDS:
            v = event_dict[k]
            event_dict[k] = f"<redacted len={len(str(v))}>"
    return event_dict


def configure_logging():
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            _redact,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    )
