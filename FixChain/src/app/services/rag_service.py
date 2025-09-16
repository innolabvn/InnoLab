# src\app\services\rag_service.py
"""
RAG Service client
- Scanner: import/search
- Fixer: import/search/fix/suggest-fix
"""

import os
import time
import requests
from typing import Dict, List, Optional
from dataclasses import dataclass
from pathlib import Path
from src.app.services.log_service import logger


# ---------- Data models ----------
@dataclass
class RAGSearchResult:
    sources: List[Dict]
    query: str
    success: bool = True
    error_message: str = ""


@dataclass
class RAGAddResult:
    success: bool
    document_id: str = ""
    error_message: str = ""


# ---------- Client ----------
class RAGService:
    """
    Service for interacting with FixChain APIs.
    Endpoints (prefix /api/v1):
      - Scanner: /scanner-rag/health, /scanner-rag/import, /scanner-rag/search
      - Fixer:   /fixer-rag/health,  /fixer-rag/import,  /fixer-rag/search, /fixer-rag/fix, /fixer-rag/suggest-fix
    """

    def __init__(
        self,
        base_url: str = os.getenv("RAG_API_BASE", "http://localhost:8000/api/v1"),
        timeout: int = 30,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

        # Endpoints
        self.scanner_health = f"{self.base_url}/scanner-rag/health"
        self.scanner_import = f"{self.base_url}/scanner-rag/import"
        self.scanner_search = f"{self.base_url}/scanner-rag/search"

        self.fixer_health = f"{self.base_url}/fixer-rag/health"
        self.fixer_import = f"{self.base_url}/fixer-rag/import"
        self.fixer_search = f"{self.base_url}/fixer-rag/search"
        self.fixer_fix    = f"{self.base_url}/fixer-rag/fix"
        self.fixer_suggest= f"{self.base_url}/fixer-rag/suggest-fix"

        self.headers = {"Content-Type": "application/json", "Accept": "application/json"}

    # ---------- Internal HTTP helper ----------
    def _post_with_retry(self, url: str, payload: Dict|List[Dict], retries: int = 2) -> requests.Response:
        last_exc: Optional[Exception] = None
        for i in range(retries + 1):
            try:
                resp = requests.post(url, json=payload, headers=self.headers, timeout=self.timeout)
                if resp.ok:
                    return resp
                if 500 <= resp.status_code < 600 and i < retries:
                    time.sleep(0.6 * (i + 1))
                    continue
                return resp
            except requests.exceptions.RequestException as e:
                last_exc = e
                if i < retries:
                    time.sleep(0.6 * (i + 1))
                    continue
                raise
        # should not reach here
        raise last_exc or RuntimeError("Unknown POST error")
    
    # ---------- Scanner ----------
    def add_scanner_signals(self, items: List[Dict]) -> RAGAddResult:
        """
        Persist final labeled items (after Dify):
          items: [{text, label: BUG|CODE_SMELL, id?, lang?, source='dify'}, ...]
        """
        try:
            resp = self._post_with_retry(self.scanner_import, items)
            if not resp.ok:
                return RAGAddResult(False, error_message=f"HTTP {resp.status_code}: {resp.text[:200]}")
            data = resp.json()
            first_id = (data.get("ids") or [None])[0]
            return RAGAddResult(True, document_id=str(first_id or ""))
        except Exception as e:
            return RAGAddResult(False, error_message=str(e))
        
    def search_scanner(self, query: str, limit: int = 5, filters: Optional[Dict] = None) -> RAGSearchResult:
        payload = {"query": query, "limit": int(limit), "filters": filters or {}}
        try:
            resp = self._post_with_retry(self.scanner_search, payload)
            if not resp.ok:
                return RAGSearchResult([], query, False, f"HTTP {resp.status_code}: {resp.text[:200]}")
            data = resp.json()
            return RAGSearchResult(list(data.get("sources", [])), data.get("query", query), True)
        except Exception as e:
            return RAGSearchResult([], query, False, str(e))
        
 # ---------- Fixer ----------
    def import_fix_cases(self, bugs_payload: List[Dict], collection_name: Optional[str] = None,
                         generate_embeddings: bool = True) -> RAGAddResult:
        payload = {
            "bugs": bugs_payload,
            "generate_embeddings": bool(generate_embeddings),
        }
        if collection_name:
            payload["collection_name"] = collection_name
        try:
            resp = self._post_with_retry(self.fixer_import, payload)
            if not resp.ok:
                return RAGAddResult(False, error_message=f"HTTP {resp.status_code}: {resp.text[:200]}")
            data = resp.json()
            first = (data.get("imported_bugs") or [{}])[0]
            return RAGAddResult(True, document_id=str(first.get("bug_id", "")))
        except Exception as e:
            return RAGAddResult(False, error_message=str(e))

    def search_fixer(self, query: str, limit: int = 5, filters: Optional[Dict] = None) -> RAGSearchResult:
        payload = {"query": query, "limit": int(limit), "filters": filters or {}}
        try:
            resp = self._post_with_retry(self.fixer_search, payload)
            if not resp.ok:
                return RAGSearchResult([], query, False, f"HTTP {resp.status_code}: {resp.text[:200]}")
            data = resp.json()
            return RAGSearchResult(list(data.get("sources", [])), data.get("query", query), True)
        except Exception as e:
            return RAGSearchResult([], query, False, str(e))

    def fix_bug(self, bug_id: str, fix_description: str, fixed_code: Optional[str] = None,
                fix_notes: Optional[str] = None) -> Dict:
        payload = {
            "bug_id": bug_id,
            "fix_description": fix_description,
            "fixed_code": fixed_code,
            "fix_notes": fix_notes,
        }
        resp = self._post_with_retry(self.fixer_fix, payload)
        return resp.json()

    def suggest_fix(self, bug_id: str, include_similar_fixes: bool = True,
                    collection_name: Optional[str] = None) -> Dict:
        payload = {"bug_id": bug_id, "include_similar_fixes": include_similar_fixes}
        if collection_name:
            payload["collection_name"] = collection_name
        resp = self._post_with_retry(self.fixer_suggest, payload)
        return resp.json()

    # ---------- Health ----------
    def health_check(self) -> bool:
        try:
            s_ok = requests.get(self.scanner_health, headers=self.headers, timeout=5).ok
            f_ok = requests.get(self.fixer_health,   headers=self.headers, timeout=5).ok
            logger.info(f"RAG Health - Scanner: {'OK' if s_ok else 'FAIL'}, Fixer: {'OK' if f_ok else 'FAIL'}")
            return bool(s_ok and f_ok)
        except Exception:
            return False