import re
import inspect
import pandas as pd
import pytest
import auth
from auth import get_app_password, is_valid_password


def replace_images_in_markdown(markdown_text, images):
    """Copy of function under test (avoids importing streamlit)."""
    if not images:
        return markdown_text
    for img in images:
        img_id = img.get('id', '')
        img_data = img.get('image_base64', '')
        if img_id and img_data:
            markdown_text = markdown_text.replace(f"]({img_id})", f"]({img_data})")
    return markdown_text


def markdown_table_to_dataframe(table_lines):
    """Copy of function under test (avoids importing streamlit)."""
    rows = []
    for line in table_lines:
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        rows.append(cells)
    if len(rows) < 2:
        return None
    headers = rows[0]
    data_rows = [r for r in rows[1:] if not all(re.match(r'^[-:]+$', c) for c in r)]
    if not data_rows:
        return None
    seen = {}
    unique_headers = []
    for h in headers:
        if h in seen:
            seen[h] += 1
            unique_headers.append(f"{h}_{seen[h]}" if h else f"_{seen[h]}")
        else:
            seen[h] = 0
            unique_headers.append(h)
    num_cols = len(unique_headers)
    data_rows = [r[:num_cols] + [''] * (num_cols - len(r)) for r in data_rows]
    return pd.DataFrame(data_rows, columns=unique_headers)


def test_unique_columns():
    """Normal table with unique headers."""
    lines = [
        "| Name | Age | City |",
        "|------|-----|------|",
        "| Alice | 30 | NYC |",
    ]
    df = markdown_table_to_dataframe(lines)
    assert list(df.columns) == ["Name", "Age", "City"]
    assert df.shape == (1, 3)


def test_duplicate_columns():
    """Table with duplicate column names should get suffixes."""
    lines = [
        "| Name | Value | Name | Value |",
        "|------|-------|------|-------|",
        "| a    | 1     | b    | 2     |",
    ]
    df = markdown_table_to_dataframe(lines)
    assert list(df.columns) == ["Name", "Value", "Name_1", "Value_1"]
    assert df.shape == (1, 4)


def test_empty_column_names():
    """Table with empty column names (the exact error scenario)."""
    lines = [
        "|  | Date: |  |  |  | Species/Variety: |",
        "|--|-------|--|--|--|------------------|",
        "| x | 2024 | a | b | c | Rose |",
    ]
    df = markdown_table_to_dataframe(lines)
    # Empty strings should get deduplicated: '', '_1', '_2', '_3'
    assert df.columns.is_unique
    assert df.shape == (1, 6)


def test_mixed_duplicate_empty():
    """Table with both duplicate named and empty columns."""
    lines = [
        "| A |  | A |  |",
        "|---|--|---|--|",
        "| 1 | 2 | 3 | 4 |",
    ]
    df = markdown_table_to_dataframe(lines)
    assert df.columns.is_unique
    assert list(df.columns) == ["A", "", "A_1", "_1"]


def test_no_duplicates_unchanged():
    """Columns without duplicates should remain unchanged."""
    lines = [
        "| X | Y | Z |",
        "|---|---|---|",
        "| 1 | 2 | 3 |",
    ]
    df = markdown_table_to_dataframe(lines)
    assert list(df.columns) == ["X", "Y", "Z"]


def _get_api_key(environ_get, secrets_lookup):
    """Replicate the API key retrieval logic from streamlit_app.py (avoids importing streamlit)."""
    api_key = environ_get("MISTRAL_API_KEY")
    if not api_key:
        try:
            api_key = secrets_lookup("MISTRAL_API_KEY")
        except (KeyError, FileNotFoundError):
            api_key = None
    return api_key


def test_api_key_from_env():
    """API key found in environment variable should be returned."""
    api_key = _get_api_key(
        environ_get=lambda k: "env-key-123",
        secrets_lookup=lambda k: (_ for _ in ()).throw(KeyError(k)),
    )
    assert api_key == "env-key-123"


def test_api_key_from_secrets_fallback():
    """When env var is missing, API key should fall back to Streamlit secrets."""
    api_key = _get_api_key(
        environ_get=lambda k: None,
        secrets_lookup=lambda k: "secrets-key-456",
    )
    assert api_key == "secrets-key-456"


def test_api_key_missing_everywhere():
    """When neither env var nor secrets have the key, result should be None."""
    api_key = _get_api_key(
        environ_get=lambda k: None,
        secrets_lookup=lambda k: (_ for _ in ()).throw(KeyError(k)),
    )
    assert api_key is None


def test_api_key_secrets_file_not_found():
    """When secrets file does not exist, FileNotFoundError should be caught."""
    api_key = _get_api_key(
        environ_get=lambda k: None,
        secrets_lookup=lambda k: (_ for _ in ()).throw(FileNotFoundError()),
    )
    assert api_key is None


def test_get_app_password_from_env(monkeypatch):
    """App password should be read from environment secret."""
    monkeypatch.setenv("TUBER_TRACKER_PASSWORD", "potato-pass")
    assert get_app_password() == "potato-pass"


def test_get_app_password_from_secrets_fallback(monkeypatch):
    """Missing env var should fall back to Streamlit secrets."""
    monkeypatch.delenv("TUBER_TRACKER_PASSWORD", raising=False)
    monkeypatch.setattr(auth, "_lookup_streamlit_secret", lambda k: "secret-potato-pass")
    assert get_app_password() == "secret-potato-pass"


def test_get_app_password_env_precedence(monkeypatch):
    """Environment password should take precedence over Streamlit secrets."""
    monkeypatch.setenv("TUBER_TRACKER_PASSWORD", "env-potato-pass")
    monkeypatch.setattr(auth, "_lookup_streamlit_secret", lambda k: "secret-potato-pass")
    assert get_app_password() == "env-potato-pass"


def test_get_app_password_missing(monkeypatch):
    """Missing password in env and Streamlit secrets should return None."""
    monkeypatch.delenv("TUBER_TRACKER_PASSWORD", raising=False)
    monkeypatch.setattr(auth, "_lookup_streamlit_secret", lambda k: (_ for _ in ()).throw(KeyError(k)))
    assert get_app_password() is None


def test_is_valid_password():
    """Password comparison should only pass on exact match."""
    assert is_valid_password("potato-pass", "potato-pass") is True
    assert is_valid_password("wrong", "potato-pass") is False
    assert is_valid_password("", "potato-pass") is False
    assert is_valid_password(None, "potato-pass") is False
    assert is_valid_password("potato-pass", None) is False


def test_replace_images_single():
    """Single image reference should be replaced with base64 data URI."""
    md = "Some text\n![figure.png](figure.png)\nMore text"
    images = [{"id": "figure.png", "image_base64": "data:image/png;base64,abc123"}]
    result = replace_images_in_markdown(md, images)
    assert "](figure.png)" not in result
    assert "](data:image/png;base64,abc123)" in result
    assert "Some text" in result
    assert "More text" in result


def test_replace_images_multiple():
    """Multiple image references should all be replaced."""
    md = "![img1.png](img1.png) and ![img2.jpg](img2.jpg)"
    images = [
        {"id": "img1.png", "image_base64": "data:image/png;base64,AAA"},
        {"id": "img2.jpg", "image_base64": "data:image/jpeg;base64,BBB"},
    ]
    result = replace_images_in_markdown(md, images)
    assert "](img1.png)" not in result
    assert "](img2.jpg)" not in result
    assert "](data:image/png;base64,AAA)" in result
    assert "](data:image/jpeg;base64,BBB)" in result


def test_replace_images_no_images():
    """When images list is empty or None, markdown should be unchanged."""
    md = "![figure.png](figure.png)"
    assert replace_images_in_markdown(md, []) == md
    assert replace_images_in_markdown(md, None) == md


def test_replace_images_no_matching_reference():
    """When image id doesn't match any reference, markdown should be unchanged."""
    md = "![figure.png](figure.png)"
    images = [{"id": "other.png", "image_base64": "data:image/png;base64,xyz"}]
    result = replace_images_in_markdown(md, images)
    assert result == md


def test_replace_images_preserves_non_image_content():
    """Non-image markdown content should be preserved."""
    md = "# Title\n\nSome paragraph\n\n![chart.png](chart.png)\n\n| Col |\n|---|\n| val |"
    images = [{"id": "chart.png", "image_base64": "data:image/png;base64,CHART"}]
    result = replace_images_in_markdown(md, images)
    assert "# Title" in result
    assert "Some paragraph" in result
    assert "| Col |" in result
    assert "](data:image/png;base64,CHART)" in result


def test_mistral_client_compat_import():
    """Mistral client should be importable via local compatibility shim."""
    from mistral_client import Mistral

    assert Mistral is not None
    assert "api_key" in inspect.signature(Mistral).parameters
