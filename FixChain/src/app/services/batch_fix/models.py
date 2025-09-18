# src/app/services/batch_fix/models.py
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Optional

@dataclass
class FixResult:
    success: bool
    file_path: str
    original_size: int
    fixed_size: int
    message: str
    validation_errors: Optional[List[str]] = None
    processing_time: float = 0.0
    similarity_ratio: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    meets_threshold: bool = True
