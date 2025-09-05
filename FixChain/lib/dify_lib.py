import requests
from utils.logger import logger
from enum import Enum

DIFY_BASE_URL = "https://api.dify.ai/v1"


class DifyMode(Enum):
    CLOUD = "CLOUD"

def get_headers(api_key):
    masked = api_key[:6] + "..." if api_key else "None"
    logger.info(f"Generating Dify headers")
    return {"Authorization": f"Bearer {api_key}"}

def run_workflow_with_dify(api_key, inputs, response_mode):
    """Run a workflow via Dify API using the workflow's api_key."""
    try:
        logger.info(f"Running workflow with Dify API: {api_key}")
        base_url = DIFY_BASE_URL
        url = f"{base_url}/workflows/run"
        headers = get_headers(api_key)
        headers["Content-Type"] = "application/json"
        payload = {"inputs": inputs, "response_mode": response_mode}
        # logger.info(f"POST {url} with payload: {payload}")
        response = requests.post(url, headers=headers, json=payload, timeout=(10, 180))
        # logger.info(f"Dify workflow run response status: {response.status_code}")
        # logger.info(f"Dify workflow run response: {response.text}")
        response.raise_for_status()
        return response.json()  # Trả về ngay sau khi gọi API
    except requests.exceptions.Timeout:
        logger.error("Dify API request timed out.")
        raise
    except Exception as e:
        logger.error(f"Failed to run workflow via Dify: {str(e)}")
        raise