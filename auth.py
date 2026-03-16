import os


def get_app_password():
    """Read app password from environment secret."""
    return os.environ.get("TUBER_TRACKER_PASSWORD")


def is_valid_password(entered_password, expected_password):
    """Check entered password against the configured secret."""
    return bool(expected_password) and entered_password == expected_password
