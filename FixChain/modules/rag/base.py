from __future__ import annotations


class RAG:
    """Base RAG interface"""

    def run(self, *args, **kwargs):
        """Execute RAG operation"""
        raise NotImplementedError
