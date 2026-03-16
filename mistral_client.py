"""Compatibility import shim for Mistral client across mistralai versions."""

from importlib import import_module

_mistralai = import_module("mistralai")

if hasattr(_mistralai, "Mistral"):
    Mistral = _mistralai.Mistral
else:
    try:
        from mistralai.client import Mistral
    except ImportError as exc:
        raise ImportError(
            "Unable to import `Mistral` from `mistralai` or `mistralai.client`. "
            "Please install a compatible `mistralai` version."
        ) from exc

__all__ = ["Mistral"]
