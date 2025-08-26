import requests
from utils.logger import logger
from enum import Enum

DIFY_BASE_URL = "https://api.dify.ai/v1"
DIFY_BASE_URL_LOCAL = "http://localhost:5001/v1"


class DifyMode(Enum):
    CLOUD = "CLOUD"
    LOCAL = "LOCAL"

def get_dify_base_url(mode):
    if mode == DifyMode.LOCAL or (isinstance(mode, str) and mode.upper() == "LOCAL"):
        return DIFY_BASE_URL_LOCAL
    return DIFY_BASE_URL


def get_headers(api_key):
    masked = api_key[:6] + "..." if api_key else "None"
    logger.info(f"Generating Dify headers for api_key: {masked}")
    return {"Authorization": f"Bearer {api_key}"}


def fetch_info(api_key, mode=DifyMode.CLOUD):
    try:
        base_url = get_dify_base_url(mode)
        resp = requests.get(
            f"{base_url}/info", headers=get_headers(api_key), timeout=30
        )
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.Timeout:
        logger.error("Dify API request timed out (info endpoint).")
        raise
    except Exception as e:
        logger.error(f"Failed to fetch Dify info: {e}")
        raise


def fetch_site(api_key, mode=DifyMode.CLOUD):
    try:
        base_url = get_dify_base_url(mode)
        resp = requests.get(
            f"{base_url}/site", headers=get_headers(api_key), timeout=30
        )
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.Timeout:
        logger.error("Dify API request timed out (site endpoint).")
        raise
    except Exception as e:
        logger.error(f"Failed to fetch Dify site: {e}")
        raise


def fetch_parameters(api_key, mode=DifyMode.CLOUD):
    try:
        base_url = get_dify_base_url(mode)
        resp = requests.get(
            f"{base_url}/parameters", headers=get_headers(api_key), timeout=30
        )
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.Timeout:
        logger.error("Dify API request timed out (parameters endpoint).")
        raise
    except Exception as e:
        logger.error(f"Failed to fetch Dify parameters: {e}")
        raise


def upload_document_to_dify(
    api_key, filepath, filename, mimetype, user, mode=DifyMode.CLOUD
):
    """Upload a document to Dify using the /upload endpoint and return the Dify document ID."""
    try:
        logger.info(f"Uploading file to Dify /upload endpoint: {filename}")
        base_url = get_dify_base_url(mode)
        url = f"{base_url}/files/upload"
        headers = get_headers(api_key)
        files = {"file": (filename, open(filepath, "rb"), mimetype)}
        data = {"user": user or "hieult", "type": "document"}
        logger.info(f"POST {url} with user={user} and type=document")

        response = requests.post(
            url, headers=headers, files=files, data=data, timeout=30
        )

        logger.info(f"Dify upload response status: {response.status_code}")
        logger.info(f"Dify upload response: {response.text}")
        response.raise_for_status()
        response_json = response.json()
        dify_document_id = response_json.get("id")
        if not dify_document_id:
            logger.error(f"No 'id' field in Dify response: {response_json}")
            raise ValueError("Failed to get Dify document ID from upload response.")
        return dify_document_id
    except requests.exceptions.Timeout:
        logger.error("Dify API request timed out (upload_document endpoint).")
        raise
    except Exception as e:
        logger.error(f"Failed to upload document to Dify: {str(e)}")
        raise


def run_workflow_with_dify(api_key, inputs, user, response_mode, mode=DifyMode.CLOUD):
    """Run a workflow via Dify API using the workflow's api_key."""
    try:
        logger.info(f"Running workflow with Dify API: {api_key}")
        logger.info(f"User: {user}")
        logger.info(f"Mode: {mode}")

        base_url = get_dify_base_url(mode)
        logger.info(f"Base URL: {base_url}")
        url = f"{base_url}/workflows/run"
        headers = get_headers(api_key)
        headers["Content-Type"] = "application/json"
        payload = {"inputs": inputs, "user": user, "response_mode": response_mode}
        logger.info(f"POST {url} with payload: {payload}")
        response = requests.post(url, headers=headers, json=payload, timeout=(10, 180))
        logger.info(f"Dify workflow run response status: {response.status_code}")
        logger.info(f"Dify workflow run response: {response.text}")
        response.raise_for_status()
        return response.json()  # Trả về ngay sau khi gọi API
    except requests.exceptions.Timeout:
        logger.error("Dify API request timed out (run_workflow endpoint).")
        raise
    except Exception as e:
        logger.error(f"Failed to run workflow via Dify: {str(e)}")
        raise


def get_workflow_logs(api_key, mode=DifyMode.CLOUD):
    """Get workflow logs from Dify API."""
    try:
        base_url = get_dify_base_url(mode)
        url = f"{base_url}/workflows/logs"
        headers = get_headers(api_key)
        logger.info(f"GET {url} for workflow logs")
        response = requests.get(url, headers=headers, timeout=30)
        logger.info(f"Dify logs response status: {response.status_code}")
        logger.info(f"Dify logs response: {response.text}")
        response.raise_for_status()
        return response.json()
    except requests.exceptions.Timeout:
        logger.error("Dify API request timed out (logs endpoint).")
        raise
    except Exception as e:
        logger.error(f"Failed to fetch Dify workflow logs: {str(e)}")
        raise

