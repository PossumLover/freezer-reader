import os
import secrets


def _lookup_streamlit_secret(secret_key):
    import streamlit as st

    return st.secrets[secret_key]


def get_app_password():
    """Read app password from environment or Streamlit secrets."""
    app_password = os.environ.get("TUBER_TRACKER_PASSWORD")
    if not app_password:
        try:
            app_password = _lookup_streamlit_secret("TUBER_TRACKER_PASSWORD")
        except (KeyError, FileNotFoundError, ModuleNotFoundError):
            app_password = None
    return app_password


def is_valid_password(entered_password, expected_password):
    """Check entered password against the configured secret."""
    return (
        isinstance(entered_password, str)
        and isinstance(expected_password, str)
        and bool(entered_password)
        and bool(expected_password)
        and secrets.compare_digest(entered_password, expected_password)
    )
