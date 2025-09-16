# src/app/repositories/mongo_utils.py
import os
from typing import Dict, Any, List, Optional
from pymongo import MongoClient, ASCENDING
from pymongo.errors import PyMongoError

MONGO_URI = os.getenv("MONGODB_URI", "")
MONGO_DB_NAME = os.getenv("MONGODB_DATABASE", "fixchain")

_client: Optional[MongoClient] = None

def get_client() -> MongoClient:
    global _client
    if _client is None:
        _client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)
    # ping để xác thực kết nối
    _client.admin.command("ping")
    return _client

def ensure_collection(
    collection_name: str,
    indexes: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    Đảm bảo collection tồn tại; nếu chưa có thì tạo và gắn index cơ bản.
    indexes: danh sách định nghĩa index ở dạng:
      [{"keys": [("source_id", 1)], "unique": False, "name": "idx_source_id"}]
    """
    client = get_client()
    db = client[MONGO_DB_NAME]

    existed = collection_name in db.list_collection_names()
    created = False
    if not existed:
        db.create_collection(collection_name)
        created = True

    # Thiết lập index (nếu truyền vào)
    applied_indexes = []
    if indexes:
        for spec in indexes:
            keys = spec.get("keys", [])
            name = spec.get("name")
            unique = spec.get("unique", False)
            if keys:
                db[collection_name].create_index(keys, name=name, unique=unique)
                applied_indexes.append(name or str(keys))

    # Index đề xuất mặc định (nhẹ, hữu ích cho truy vấn phổ biến)
    # Chỉ tạo nếu chưa có bất kỳ index nào được truyền
    if not indexes:
        try:
            db[collection_name].create_index([("created_at", ASCENDING)], name="idx_created_at")
            db[collection_name].create_index([("source_id", ASCENDING)],  name="idx_source_id")
            applied_indexes.extend(["idx_created_at", "idx_source_id"])
        except PyMongoError:
            # Không làm "vỡ" health nếu index gặp trục trặc
            pass

    return {
        "ok": True,
        "db": MONGO_DB_NAME,
        "collection": collection_name,
        "existed": existed,
        "created": created,
        "indexes_applied": applied_indexes,
    }
