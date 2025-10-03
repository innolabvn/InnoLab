# src/app/domains/fix/models.py
from dataclasses import dataclass

@dataclass
class RealBug:
    key: str
    label: str
    id: str
    classification: str
    reason: str
    title: str
    lang: str
    file_name: str
    code_snippet: str
    line_number: str
    severity: str