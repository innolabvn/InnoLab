from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Literal, Optional, Dict, Any
import os
from datetime import datetime
from src.app.repositories.mongo import get_mongo_manager
from src.app.adapters.llm.google_genai import client, EMBEDDING_MODEL

router = APIRouter(prefix="/scanner-kb", tags=["Scanner KB"])

class ScannerSignal(BaseModel):
    text: str = Field(..., max_length=1000)
    label: Literal["REAL_BUG", "CODE_SMELL"]
    rule_id: Optional[str] = None
    lang: Optional[str] = None
    source: str = "manual"

class ModerateReq(BaseModel):
    ids: List[str]
    action: Literal["APPROVE","REJECT"]

@router.post("/import")
def import_signals(items: List[ScannerSignal]):
    mm = get_mongo_manager()
    col = mm.get_collection("staging_scanner_signals")
    docs = []
    for it in items:
        docs.append({
            "content": it.text,
            "metadata": {
                "kind": "scanner",
                "label": it.label,
                "rule_id": it.rule_id,
                "lang": it.lang,
                "source": it.source,
                "moderation_status": "PENDING",
                "created_at": datetime.utcnow()
            },
            "embedding": None
        })
    r = col.insert_many(docs)
    return {"success": True, "inserted": len(r.inserted_ids), "ids": [str(x) for x in r.inserted_ids]}

@router.post("/moderate")
def moderate(req: ModerateReq):
    from bson import ObjectId
    mm = get_mongo_manager()
    st = mm.get_collection("staging_scanner_signals")
    kb = mm.get_collection(os.getenv("SCANNER_RAG_COLLECTION","kb_scanner_signals"))
    ids = [ObjectId(i) for i in req.ids]
    if req.action == "REJECT":
        res = st.delete_many({"_id": {"$in": ids}})
        return {"success": True, "deleted": res.deleted_count}

    # APPROVE: embed + move
    pend = list(st.find({"_id": {"$in": ids}}))
    if not pend:
        raise HTTPException(404, "No pending items")
    def _embed(t: str):
        r = client.models.embed_content(model=EMBEDDING_MODEL, contents=t)
        return r.embeddings[0].values
    to_insert = []
    for d in pend:
        d["embedding"] = _embed(d["content"][:4000])
        d["metadata"]["moderation_status"] = "APPROVED"
        to_insert.append(d)
    kb.insert_many(to_insert)
    st.delete_many({"_id": {"$in": ids}})
    return {"success": True, "approved": len(to_insert)}
