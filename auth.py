import os
import secrets


def get_app_password():
    """Read app password from environment secret."""
    return os.environ.get("TUBER_TRACKER_PASSWORD")


def is_valid_password(entered_password, expected_password):
    """Check entered password against the configured secret."""
    return (
        isinstance(entered_password, str)
        and isinstance(expected_password, str)
        and bool(entered_password)
        and bool(expected_password)
        and secrets.compare_digest(entered_password, expected_password)
    )
