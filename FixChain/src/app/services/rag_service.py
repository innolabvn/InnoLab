#!/usr/bin/env python3
"""
RAG Service client
- Search Knowledge Base (RAG Scanner support)
- Add generic doc to Knowledge
- Add Fix Case to Fix Cases collection (RAG Fixer support)
"""

import os
import requests
from typing import Dict, List, Optional
from dataclasses import dataclass
from pathlib import Path

from src.app.services.log_service import logger


# ---------- Data models ----------
@dataclass
class RAGSearchResult:
    answer: str
    sources: List[Dict]
    query: str
    success: bool = True
    error_message: str = ""


@dataclass
class RAGAddResult:
    success: bool
    document_id: str = ""
    error_message: str = ""
    content_length: int = 0


# ---------- Client ----------
class RAGService:
    """
    Service for interacting with FixChain APIs.
    Defaults assume the new router prefixes:
      - Knowledge Base:   /api/v1/knowledge
      - Fix Cases:        /api/v1/fix-cases
    """

    def __init__(
        self,
        base_url: str = os.getenv("RAG_API_BASE", "http://localhost:8000/api/v1"),
        timeout: int = 30,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

        # Endpoints
        self.knowledge_search = f"{self.base_url}/knowledge/search"
        self.knowledge_add = f"{self.base_url}/knowledge/add"
        self.knowledge_health = f"{self.base_url}/knowledge/health"

        self.fix_cases_import = f"{self.base_url}/fix-cases/import"
        self.fix_cases_health = f"{self.base_url}/fix-cases/health"

        self.headers = {"Content-Type": "application/json", "Accept": "application/json"}

    # ---------- Public: Search ----------
    def search_rag_knowledge(self, issues_data: List[Dict], limit: int = 5) -> RAGSearchResult:
        """
        Search Knowledge Base for similar rules/notes that inform bug classification or fixes.
        Sends an OR-combined list of rule descriptions.
        """
        try:
            payload = self._transform_issues_to_search_query(issues_data, limit)
            if not payload.get("query"):
                return RAGSearchResult(
                    answer="No relevant issues found for RAG search.",
                    sources=[],
                    query="",
                    success=False,
                    error_message="No searchable issues found",
                )

            logger.info(f"[RAG] Knowledge search: {str(payload['query'])[:120]} ...")
            resp = requests.post(self.knowledge_search, json=payload, headers=self.headers, timeout=self.timeout)

            if resp.ok:
                data = resp.json()
                return RAGSearchResult(
                    answer=str(data.get("answer", "")),
                    sources=list(data.get("sources", [])),
                    query=str(data.get("query", "")),
                    success=True,
                )

            msg = f"Knowledge search failed ({resp.status_code}): {resp.text[:200]}"
            logger.error(msg)
            return RAGSearchResult(answer="", sources=[], query="", success=False, error_message=msg)

        except requests.exceptions.RequestException as e:
            msg = f"Knowledge search request error: {e}"
            logger.error(msg)
            return RAGSearchResult(answer="", sources=[], query="", success=False, error_message=msg)
        except Exception as e:
            msg = f"Knowledge search unexpected error: {e}"
            logger.error(msg)
            return RAGSearchResult(answer="", sources=[], query="", success=False, error_message=msg)

    # ---------- Public: Add (Knowledge) ----------
    def add_fix_to_rag(
        self,
        fix_context: Dict,
        issues_data: Optional[List[Dict]] = None,
        raw_response: str = "",
        fixed_code: str = "",
    ) -> RAGAddResult:
        """
        Backward-compatible: add a summarized doc to Knowledge Base (/knowledge/add).
        Use add_fix_case(...) if you want a proper Fix Case in /fix-cases/import.
        """
        try:
            payload = self._transform_fix_to_knowledge_document(
                fix_context=fix_context,
                issues_data=issues_data,
                raw_response=raw_response,
                fixed_code=fixed_code,
            )

            logger.info(f"[RAG] Add to Knowledge: {fix_context.get('file_path', 'unknown')}")
            resp = requests.post(self.knowledge_add, json=payload, headers=self.headers, timeout=self.timeout)

            if resp.ok:
                data = resp.json()
                return RAGAddResult(
                    success=True,
                    document_id=str(data.get("document_id", "")),
                    content_length=int(data.get("content_length", len(payload.get("content", "")))),
                )

            msg = f"Knowledge add failed ({resp.status_code}): {resp.text[:200]}"
            logger.error(msg)
            return RAGAddResult(success=False, error_message=msg)

        except requests.exceptions.RequestException as e:
            msg = f"Knowledge add request error: {e}"
            logger.error(msg)
            return RAGAddResult(success=False, error_message=msg)
        except Exception as e:
            msg = f"Knowledge add unexpected error: {e}"
            logger.error(msg)
            return RAGAddResult(success=False, error_message=msg)

    # ---------- Public: Add (Fix Cases) ----------
    def add_fix_case(
        self,
        fix_context: Dict,
        issues_data: Optional[List[Dict]] = None,
        fixed_code: str = "",
        generate_embeddings: bool = True,
        collection_name: str = "bug_rag_documents",
    ) -> RAGAddResult:
        """
        Add a Fix Case into Fix Cases service (/fix-cases/import).
        Payload matches BugRAGImportRequest in fix_cases router:
          {
            "bugs": [BugRAGItem, ...],
            "collection_name": "...",
            "generate_embeddings": true/false
          }
        """
        try:
            bugs_payload = self._transform_to_fix_case_items(
                fix_context=fix_context,
                issues_data=issues_data,
                fixed_code=fixed_code,
            )

            import_payload = {
                "bugs": bugs_payload,
                "collection_name": collection_name,
                "generate_embeddings": bool(generate_embeddings),
            }

            logger.info(f"[RAG] Add Fix Case: {fix_context.get('file_path', 'unknown')}")
            resp = requests.post(self.fix_cases_import, json=import_payload, headers=self.headers, timeout=self.timeout)

            if resp.ok:
                data = resp.json()
                # Return the first inserted id if available
                first = (data.get("imported_bugs") or [{}])[0]
                return RAGAddResult(success=True, document_id=str(first.get("bug_id", "")), content_length=0)

            msg = f"Fix Case import failed ({resp.status_code}): {resp.text[:200]}"
            logger.error(msg)
            return RAGAddResult(success=False, error_message=msg)

        except requests.exceptions.RequestException as e:
            msg = f"Fix Case import request error: {e}"
            logger.error(msg)
            return RAGAddResult(success=False, error_message=msg)
        except Exception as e:
            msg = f"Fix Case import unexpected error: {e}"
            logger.error(msg)
            return RAGAddResult(success=False, error_message=msg)

    # ---------- Public: Health ----------
    def health_check(self) -> bool:
        """
        Health check Knowledge Base endpoint (default).
        """
        try:
            resp = requests.get(self.knowledge_health, timeout=5)
            return resp.ok
        except Exception:
            return False

    # ---------- Public: Prompt helper ----------
    def get_rag_context_for_prompt(self, issues_data: List[Dict]) -> str:
        """
        Summarize top-3 knowledge sources to append into a Fix prompt.
        """
        result = self.search_rag_knowledge(issues_data, limit=3)
        if not result.success or not result.sources:
            return "No relevant previous fixes found in knowledge base."

        parts: List[str] = ["\n=== RELEVANT PREVIOUS FIXES FROM KNOWLEDGE BASE ==="]
        for i, src in enumerate(result.sources[:3], 1):
            content: str = str(src.get("content", ""))[:200]
            sim = float(src.get("similarity_score", 0))
            parts.append(f"\n{i}. Similar Fix (Similarity: {sim:.2f}):")
            parts.append(f"   {content}...")
            md = src.get("metadata", {}) or {}
            if md.get("code_language"):
                parts.append(f"   Language: {md['code_language']}")
            if md.get("fix_summary"):
                fs = md["fix_summary"]
                if isinstance(fs, list) and fs:
                    parts.append(f"   Fix approach: {str(fs[0].get('change', ''))}")
        parts.append("\n=== END OF KNOWLEDGE BASE CONTEXT ===\n")
        return "\n".join(parts)

    # ---------- Transforms ----------
    def _transform_issues_to_search_query(self, issues_data: List[Dict], limit: int) -> Dict:
        """
        Build a Knowledge search payload:
          { "query": [<rule1>, <rule2>, ...], "limit": N, "combine_mode": "OR" }
        """
        query_list: List[str] = []
        for issue in issues_data or []:
            classification = str(issue.get("classification", "")).lower()
            action = str(issue.get("action", "")).lower()
            if classification == "true bug" and action == "fix":
                rule_desc = str(issue.get("rule_description", "")).strip()
                if rule_desc and rule_desc not in query_list:
                    query_list.append(rule_desc)

        return {"query": query_list, "limit": int(limit), "combine_mode": "OR"}

    def _transform_fix_to_knowledge_document(
        self,
        fix_context: Dict,
        issues_data: Optional[List[Dict]] = None,
        raw_response: str = "",
        fixed_code: str = "",
    ) -> Dict:
        """
        Build a Knowledge document payload:
          { "content": "...", "metadata": {...} }
        """
        bug_context: List[str] = []
        fix_summary: List[Dict] = []

        file_path = str(fix_context.get("file_path", "") or "")
        file_name = Path(file_path).name if file_path else "unknown file"

        if issues_data:
            for issue in issues_data:
                # crude match: same leaf filename
                if str(issue.get("component", "")).endswith(file_name):
                    bug_context.append(f"Line {issue.get('line', 'N/A')}: {issue.get('message', 'No message')}")
                    fix_summary.append({
                        "title": issue.get("message", "Bug fix"),
                        "why": f"Issue type: {issue.get('type', 'Unknown')}, Severity: {issue.get('severity', 'Unknown')}",
                        "change": "Applied AI-generated fix to resolve the issue",
                    })

        # language inference
        code_language = self._ext_to_lang(Path(file_path).suffix.lower())

        content = f"Bug: Fixed {len(fix_summary) if fix_summary else 0} issues in {file_name}"

        metadata: Dict = {
            "bug_title": f"Fixed issues in {file_name}",
            "bug_context": bug_context or ["No specific bug context available"],
            "fix_summary": fix_summary or [{
                "title": "General code improvement",
                "why": "Applied AI-generated fixes",
                "change": "Code quality and bug fixes",
            }],
            "fixed_source_present": bool(fixed_code),
            "code_language": code_language,
            "code": fixed_code or "",
        }

        # merge extra keys from fix_context without overriding above
        for k, v in (fix_context or {}).items():
            if k not in metadata:
                metadata[k] = v

        if raw_response:
            metadata["raw_ai_response"] = str(raw_response)[:1000]

        return {"content": content, "metadata": metadata}

    def _transform_to_fix_case_items(
        self,
        fix_context: Dict,
        issues_data: Optional[List[Dict]] = None,
        fixed_code: str = "",
    ) -> List[Dict]:
        """
        Build Fix Cases import payload -> list of BugRAGItem objects (dict-typed):
          {
            "name": str, "description": str, "type": "BUG", "severity": "MEDIUM", "status": "OPEN|FIXED",
            "file_path": str|None, "line_number": int|None, "code_snippet": str|None,
            "labels": [], "project": str|None, "component": str|None, "metadata": {...}
          }
        """
        file_path = str(fix_context.get("file_path", "") or "")
        file_name = Path(file_path).name if file_path else "unknown file"
        project = str(fix_context.get("project", "") or None) or None
        component = str(fix_context.get("component", "") or None) or None

        # derive severity/type from issues if possible
        severity = "MEDIUM"
        bug_type = "BUG"
        line_number: Optional[int] = None
        labels: List[str] = []

        if issues_data:
            for issue in issues_data:
                if str(issue.get("component", "")).endswith(file_name):
                    severity = str(issue.get("severity", "") or severity or "MEDIUM").upper()
                    bug_type = str(issue.get("type", "") or bug_type or "BUG").upper()
                    try:
                        line_number = int(issue.get("line", line_number or 0)) or line_number
                    except Exception:
                        pass
                    rule = str(issue.get("rule", "") or "").strip()
                    if rule and rule not in labels:
                        labels.append(rule)

        description = f"Fix applied to {file_name}. See metadata.fix_summary and code_snippet."
        code_snippet = fixed_code or str(fix_context.get("fixed_code", "") or "")

        bug_item = {
            "name": f"Fix: {file_name}",
            "description": description,
            "type": bug_type or "BUG",
            "severity": severity or "MEDIUM",
            "status": "FIXED" if code_snippet else "OPEN",
            "file_path": file_path or None,
            "line_number": line_number,
            "code_snippet": code_snippet or None,
            "labels": labels,
            "project": project,
            "component": component,
            "metadata": {
                "source": "SonarQ|FixChain",
                "bug_title": f"Fixed issues in {file_name}",
                "fix_context": fix_context or {},
            },
        }

        return [bug_item]

    @staticmethod
    def _ext_to_lang(ext: str) -> str:
        mapping = {
            ".py": "python",
            ".js": "javascript", ".jsx": "javascript",
            ".ts": "typescript", ".tsx": "typescript",
            ".java": "java", ".kt": "kotlin",
            ".cpp": "cpp", ".cc": "cpp", ".cxx": "cpp", ".c": "c",
            ".rb": "ruby", ".go": "go", ".rs": "rust",
            ".php": "php",
            ".html": "html", ".css": "css",
            ".sql": "sql",
        }
        return mapping.get(ext, "text")


# ---------- Quick self-test ----------
if __name__ == "__main__":
    svc = RAGService()
    healthy = svc.health_check()
    print(f"Knowledge health: {'OK' if healthy else 'FAIL'}")

    sample_issues = [{
        "classification": "True Bug",
        "action": "Fix",
        "rule_description": "SQL injection vulnerability in user input",
        "message": "Potential SQL injection",
        "line": 42,
        "component": "src/main/java/Example.java",
        "severity": "CRITICAL",
        "type": "BUG",
        "rule": "java:S3649"
    }]

    sr = svc.search_rag_knowledge(sample_issues)
    print("Search OK:", sr.success, "hits:", len(sr.sources))

    # Example add to Knowledge (legacy behavior)
    add_res = svc.add_fix_to_rag({"file_path": "src/main/java/Example.java"}, sample_issues, fixed_code="safeQuery(...)")
    print("Add to knowledge OK:", add_res.success)

    # Example add to Fix Cases
    add_case = svc.add_fix_case({"file_path": "src/main/java/Example.java"}, sample_issues, fixed_code="safeQuery(...)")
    print("Add fix case OK:", add_case.success)
