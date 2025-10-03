# src/app/services/batch_fix/validators.py
from __future__ import annotations
from difflib import SequenceMatcher

def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()