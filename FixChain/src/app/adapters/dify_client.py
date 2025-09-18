from __future__ import annotations
import os
from typing import Any, Dict, Optional, TypedDict
from pydantic import BaseModel
import requests
from requests.adapters import HTTPAdapter, Retry

from src.app.services.log_service import logger

# ---- Config ----
DEFAULT_BASE_URL = "https://api.dify.ai/v1"

def _get_base_url() -> str:
    return os.getenv("DIFY_BASE_URL", DEFAULT_BASE_URL).rstrip("/")

class DifyRunResponse(BaseModel):
    # Những field phổ biến của Dify workflow/text generation; tuỳ app có thể dư/thiếu   
    id: Optional[str] = None
    status: Optional[str] = None               # e.g. "succeeded", "failed", "processing"
    data: Optional[Dict[str, Any]] = None      # payload chính (output, variables, files, ...)
    message: Optional[str] = None              # thông điệp lỗi/diag
    usage: Optional[float] = None              # tokens, latency, ...
    time: Optional[float] = None               # thời gian thực thi (giây)
    raw: Dict[str, Any]                        # giữ bản gốc JSON để debug

def _make_session() -> requests.Session:
    """Session với retry hợp lý cho lỗi mạng/tạm thời."""
    session = requests.Session()
    retries = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("POST", "GET"),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session

def _headers(api_key: str) -> Dict[str, str]:
    if not api_key or not api_key.strip():
        logger.error("Missing Dify API key")
    return {
        "Authorization": f"Bearer {api_key.strip()}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

def run_workflow_with_dify(
    api_key: str,
    inputs: Dict[str, Any],
    response_mode: str = "blocking",
    user_id: str = "user",
    timeout: tuple[float, float] = (10.0, 180.0),
) -> DifyRunResponse:
    """
    Gọi Dify Workflow API: POST /workflows/run

    Args:
        api_key: DIFY_CLOUD_API_KEY của workflow
        inputs: payload inputs cho workflow
        response_mode: "blocking" hoặc "streaming" (ở đây ta dùng blocking)
        user_id: id người dùng (Dify bắt buộc có trường user)
        timeout: (connect_timeout, read_timeout)

    Returns:
        DifyRunResponse (dict có thể chứa "data" -> "outputs"...)
    """
    base_url = _get_base_url()
    url = f"{base_url}/workflows/run"

    # Log an toàn, không in key
    logger.info("[DIFY LLM] 🚀 Starting workflow call: %s (mode=%s)", url, response_mode)
    logger.info("[DIFY LLM] 📝 Request payload - user: %s, inputs keys: %s", user_id, list(inputs.keys()))
    logger.debug("[DIFY LLM] 📋 Full inputs content: %s", inputs)

    payload = {"inputs": inputs, "user": user_id, "response_mode": response_mode}

    session = _make_session()
    logger.info("[DIFY LLM] ⏱️ Sending request with timeout: %s", timeout)
    try:
        resp = session.post(url, headers=_headers(api_key), json=payload, timeout=timeout)
        logger.info("[DIFY LLM] ✅ Request completed with status: %s", resp.status_code)
    except requests.exceptions.Timeout:
        logger.error("[DIFY LLM] ❌ Request timed out: %s", url)
        raise
    except requests.exceptions.RequestException as e:
        logger.error("[DIFY LLM] ❌ Network error: %s", e)
        raise

    # Tự xử lý lỗi HTTP để trả message dễ hiểu hơn
    if not (200 <= resp.status_code < 300):
        # cố lấy message/json
        text = resp.text[:300] if resp.text else ""
        logger.error("[DIFY LLM] ❌ HTTP error %s: %s", resp.status_code, text)
        resp.raise_for_status()  # raise để upstream biết failed

    try:
        data = resp.json()
        logger.info("[DIFY LLM] 📊 Response keys: %s", list(data.keys()))
        logger.info("[DIFY LLM] 🆔 Task ID: %s", data.get("task_id"))
        logger.info("[DIFY LLM] 📤 Output keys: %s", list(data.get("data", {}).get("outputs", {}).keys()))
        logger.debug("[DIFY LLM] 📋 Full response data: %s", data)
    except ValueError:
        logger.error("[DIFY LLM] ❌ Invalid JSON response: %r", resp.text[:200])
        raise

    if isinstance(data, dict) and "error" in data:
        logger.warning("[DIFY LLM] ⚠️ Response contains error: %s", data.get("error"))

    # Log token usage and timing
    total_tokens = data.get("total_tokens")
    elapsed_time = data.get("elapsed_time")
    if total_tokens:
        logger.info("[DIFY LLM] 🔢 Token usage: %s tokens", total_tokens)
    if elapsed_time:
        logger.info("[DIFY LLM] ⏱️ Execution time: %s seconds", elapsed_time)
    
    logger.info("[DIFY LLM] ✅ Successfully created DifyRunResponse")
    
    return DifyRunResponse(
            id=data.get("task_id"),
            status=data.get("status") or data.get("data", {}).get("status"),
            data=data.get("data") or data.get("output"),
            message=data.get("message") or data.get("error"),
            usage=data.get("total_tokens"),
            time=data.get("elapsed_time"),
            raw=data,
        )
