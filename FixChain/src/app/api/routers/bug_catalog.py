# src/app/api/routers/bug_catalog.py
"""
Import CSV/JSON, search, analyze, stats
"""
import os, json, csv
from datetime import datetime
from typing import List, Dict, Optional
from enum import Enum
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException, UploadFile, File
from dotenv import load_dotenv
from src.app.adapters.llm.google_genai import client, EMBEDDING_MODEL, GENERATION_MODEL
from src.app.repositories.mongo import MongoDBManager

# Load .env (từ root). Có thể chuyển sang config chung sau
root_env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))), '.env')
load_dotenv(root_env_path)

# ----- Lazy init tài nguyên (APIRouter không có on_event) -----
mongo_manager: Optional[MongoDBManager] = None

def ensure_inited():
    global mongo_manager
    if mongo_manager is None:
        mongo_manager = MongoDBManager()

# ----- Enums & Models -----
class BugType(str, Enum):
    CODE_SMELL = "CODE_SMELL"
    BUG = "BUG"
    VULNERABILITY = "VULNERABILITY"
    SECURITY_HOTSPOT = "SECURITY_HOTSPOT"
    PERFORMANCE = "PERFORMANCE"
    MAINTAINABILITY = "MAINTAINABILITY"
    RELIABILITY = "RELIABILITY"
    DUPLICATION = "DUPLICATION"

class BugSeverity(str, Enum):
    BLOCKER = "BLOCKER"
    CRITICAL = "CRITICAL"
    MAJOR = "MAJOR"
    MINOR = "MINOR"
    INFO = "INFO"

class BugStatus(str, Enum):
    OPEN = "OPEN"
    CONFIRMED = "CONFIRMED"
    REOPENED = "REOPENED"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"
    FALSE_POSITIVE = "FALSE_POSITIVE"
    WONT_FIX = "WONT_FIX"

class BugItem(BaseModel):
    name: str
    description: str
    type: BugType
    severity: Optional[BugSeverity] = BugSeverity.MAJOR
    status: Optional[BugStatus] = BugStatus.OPEN
    labels: Optional[List[str]] = Field(default=[])
    file_path: Optional[str] = None
    line_number: Optional[int] = None
    component: Optional[str] = None
    project: Optional[str] = None
    assignee: Optional[str] = None
    reporter: Optional[str] = None
    created_date: Optional[str] = None
    updated_date: Optional[str] = None
    resolution: Optional[str] = None
    effort: Optional[str] = None
    debt: Optional[str] = None
    tags: Optional[List[str]] = Field(default=[])

class BugImportRequest(BaseModel):
    bugs: List[BugItem]
    project_name: Optional[str] = None
    import_source: Optional[str] = "manual"
    batch_name: Optional[str] = None

class BugSearchRequest(BaseModel):
    query: str
    bug_types: Optional[List[BugType]] = None
    severities: Optional[List[BugSeverity]] = None
    labels: Optional[List[str]] = None
    project: Optional[str] = None
    limit: Optional[int] = 5

class BugAnalysisRequest(BaseModel):
    bug_ids: Optional[List[str]] = None
    analysis_type: str = "summary"
    project: Optional[str] = None
    time_range: Optional[str] = None

# ----- Helpers -----
async def get_gemini_embedding(text: str) -> List[float]:
    try:
        resp = client.models.embed_content(
            model=EMBEDDING_MODEL,
            contents=text,
        )
        return resp.embeddings[0].values
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating embedding: {str(e)}")

def format_bug_content(bug: BugItem) -> str:
    parts = [
        f"Bug Name: {bug.name}",
        f"Description: {bug.description}",
        f"Type: {bug.type.value}",
        f"Severity: {bug.severity.value if bug.severity else 'Unknown'}",
        f"Status: {bug.status.value if bug.status else 'Unknown'}",
    ]
    if bug.labels: parts.append(f"Labels: {', '.join(bug.labels)}")
    if bug.file_path: parts.append(f"File: {bug.file_path}")
    if bug.line_number: parts.append(f"Line: {bug.line_number}")
    if bug.component: parts.append(f"Component: {bug.component}")
    if bug.resolution: parts.append(f"Resolution: {bug.resolution}")
    if bug.tags: parts.append(f"Tags: {', '.join(bug.tags)}")
    return "\n".join(parts)

def create_bug_metadata(bug: BugItem, import_info: Dict) -> Dict:
    metadata = {
        "document_type": "bug",
        "bug_name": bug.name,
        "bug_type": bug.type.value,
        "severity": bug.severity.value if bug.severity else None,
        "status": bug.status.value if bug.status else None,
        "labels": bug.labels or [],
        "tags": bug.tags or [],
        "file_path": bug.file_path,
        "line_number": bug.line_number,
        "component": bug.component,
        "project": bug.project or import_info.get("project_name"),
        "assignee": bug.assignee,
        "reporter": bug.reporter,
        "created_date": bug.created_date,
        "updated_date": bug.updated_date,
        "resolution": bug.resolution,
        "effort": bug.effort,
        "debt": bug.debt,
        "import_source": import_info.get("import_source", "manual"),
        "batch_name": import_info.get("batch_name"),
        "imported_at": datetime.utcnow().isoformat(),
    }
    return {k: v for k, v in metadata.items() if v is not None}

def convert_mongodb_to_json(data):
    from bson import ObjectId
    from datetime import datetime as dt
    if isinstance(data, list):
        return [convert_mongodb_to_json(item) for item in data]
    if isinstance(data, dict):
        return {k: convert_mongodb_to_json(v) for k, v in data.items()}
    if isinstance(data, ObjectId):
        return str(data)
    if isinstance(data, dt):
        return data.isoformat()
    return data

async def generate_bug_analysis(bugs_data: List[Dict], analysis_type: str) -> str:
    try:
        serializable_data = convert_mongodb_to_json(bugs_data[:10])
        if analysis_type == "summary":
            prompt = f"""
Phân tích tổng quan về {len(bugs_data)} bugs sau đây:
{json.dumps(serializable_data, indent=2, ensure_ascii=False)}
Hãy cung cấp:
1. Tổng quan theo loại
2. Mức độ nghiêm trọng
3. Vấn đề phổ biến
4. Ưu tiên xử lý
5. Xu hướng/pattern
Trả lời tiếng Việt, có cấu trúc.
"""
        elif analysis_type == "trend":
            prompt = f"""
Phân tích xu hướng bugs:
{json.dumps(serializable_data, indent=2, ensure_ascii=False)}
1. Xu hướng theo thời gian
2. Pattern theo component/file
3. Phân bố theo loại
4. Dự đoán & khuyến nghị
"""
        elif analysis_type == "priority":
            prompt = f"""
Đề xuất ưu tiên xử lý:
{json.dumps(serializable_data, indent=2, ensure_ascii=False)}
1. Danh sách ưu tiên cao
2. Lý do
3. Thứ tự xử lý
4. Ước tính effort
"""
        elif analysis_type == "search_answer":
            bug_summaries = []
            for bug in serializable_data:
                md = bug.get("metadata", {})
                bug_summaries.append({
                    "name": md.get("bug_name"),
                    "type": md.get("bug_type"),
                    "severity": md.get("severity"),
                    "component": md.get("component"),
                    "description": bug.get("content", "")[:200],
                })
            prompt = f"""
Tóm tắt & phân tích các bugs sau (từ kết quả tìm kiếm):
{json.dumps(bug_summaries, indent=2, ensure_ascii=False)}
1. Tóm tắt
2. Mức độ & ưu tiên
3. Khuyến nghị
4. Liên hệ giữa các bugs
Trả lời ngắn gọn, tiếng Việt.
"""
        else:
            prompt = f"Phân tích dữ liệu bugs: {json.dumps(serializable_data[:5], ensure_ascii=False)}"

        response = client.models.generate_content(model=GENERATION_MODEL, contents=prompt)
        return response.text
    except Exception as e:
        return f"Can't generate bug analysis: {str(e)}"

# ----- Router -----
router = APIRouter()

@router.get("/health")
async def health_check():
    """Health check endpoint for Bug Management API"""
    ensure_inited()
    try:
        total_bugs = mongo_manager.documents_collection.count_documents({
            "metadata.document_type": "bug"
        })
        return {"status": "healthy", "service": "bug_management", "total_bugs": total_bugs}
    except Exception as e:
        return {"status": "unhealthy", "service": "bug_management", "error": str(e)}

@router.post("/bug-catalog/import")
async def import_bugs(request: BugImportRequest):
    ensure_inited()
    try:
        imported_bugs, failed_bugs = [], []
        import_info = {
            "project_name": request.project_name,
            "import_source": request.import_source,
            "batch_name": request.batch_name or f"batch_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
        }
        for i, bug in enumerate(request.bugs):
            try:
                bug_content = format_bug_content(bug)[:4000]  # chặn dài quá
                embedding = await get_gemini_embedding(bug_content)
                metadata = create_bug_metadata(bug, import_info)
                doc_id = mongo_manager.add_document(content=bug_content, embedding=embedding, metadata=metadata)
                imported_bugs.append({
                    "bug_name": bug.name, "document_id": doc_id,
                    "type": bug.type.value,
                    "severity": bug.severity.value if bug.severity else None
                })
            except Exception as e:
                failed_bugs.append({"bug_name": bug.name, "error": str(e), "index": i})
        return {
            "message": f"Import completed: {len(imported_bugs)} success, {len(failed_bugs)} failed",
            "batch_name": import_info["batch_name"],
            "imported_count": len(imported_bugs),
            "failed_count": len(failed_bugs),
            "imported_bugs": imported_bugs,
            "failed_bugs": failed_bugs,
            "project": request.project_name,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Import failed: {str(e)}")

@router.post("/search")
async def search_bugs(request: BugSearchRequest):
    ensure_inited()
    try:
        query_embedding = await get_gemini_embedding(request.query)
        results = mongo_manager.search_by_embedding(query_embedding=query_embedding, top_k=request.limit * 2)
        filtered = []
        for r in results:
            md = r.get("metadata", {})
            if request.bug_types and md.get("bug_type") not in [t.value for t in request.bug_types]:
                continue
            if request.severities and md.get("severity") not in [s.value for s in request.severities]:
                continue
            if request.labels:
                bug_labels = md.get("labels", [])
                if not any(l in bug_labels for l in request.labels):
                    continue
            if request.project and md.get("project") != request.project:
                continue
            filtered.append(r)
            if len(filtered) >= request.limit:
                break
        answer = await generate_bug_analysis(filtered, "search_answer") if filtered else "Không tìm thấy bugs phù hợp."
        bugs_info = []
        for r in filtered:
            md = r.get("metadata", {})
            content = r["content"]
            bugs_info.append({
                "bug_name": md.get("bug_name"),
                "type": md.get("bug_type"),
                "severity": md.get("severity"),
                "status": md.get("status"),
                "component": md.get("component"),
                "project": md.get("project"),
                "labels": md.get("labels", []),
                "similarity_score": r.get("similarity", 0),
                "content_preview": content[:200] + "..." if len(content) > 200 else content,
            })
        return {
            "query": request.query,
            "answer": answer,
            "found_bugs": len(bugs_info),
            "bugs": bugs_info,
            "filters_applied": {
                "bug_types": [t.value for t in request.bug_types] if request.bug_types else None,
                "severities": [s.value for s in request.severities] if request.severities else None,
                "labels": request.labels,
                "project": request.project,
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")

@router.post("/analyze")
async def analyze_bugs(request: BugAnalysisRequest):
    ensure_inited()
    try:
        if request.bug_ids:
            bugs_data = []
            for bug_id in request.bug_ids:
                doc = mongo_manager.documents_collection.find_one({"doc_id": bug_id})
                if doc:
                    bugs_data.append(doc)
        else:
            q = {"metadata.document_type": "bug"}
            if request.project:
                q["metadata.project"] = request.project
            bugs_data = list(mongo_manager.documents_collection.find(q).limit(100))

        if not bugs_data:
            return {"message": "Không tìm thấy bugs để phân tích", "analysis": "Không có dữ liệu phù hợp."}

        analysis = await generate_bug_analysis(bugs_data, request.analysis_type)
        stats = {"total_bugs": len(bugs_data), "by_type": {}, "by_severity": {}, "by_status": {}, "projects": set()}
        for bug in bugs_data:
            md = bug.get("metadata", {})
            stats["by_type"][md.get("bug_type", "Unknown")] = stats["by_type"].get(md.get("bug_type", "Unknown"), 0) + 1
            stats["by_severity"][md.get("severity", "Unknown")] = stats["by_severity"].get(md.get("severity", "Unknown"), 0) + 1
            stats["by_status"][md.get("status", "Unknown")] = stats["by_status"].get(md.get("status", "Unknown"), 0) + 1
            if md.get("project"): stats["projects"].add(md["project"])
        stats["projects"] = list(stats["projects"])
        return {"analysis_type": request.analysis_type, "analysis": analysis, "statistics": stats, "analyzed_bugs_count": len(bugs_data)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")

@router.get("/stats")
async def get_bug_stats():
    ensure_inited()
    try:
        total_bugs = mongo_manager.documents_collection.count_documents({"metadata.document_type": "bug"})
        pipeline = [
            {"$match": {"metadata.document_type": "bug"}},
            {"$group": {
                "_id": {
                    "type": "$metadata.bug_type",
                    "severity": "$metadata.severity",
                    "status": "$metadata.status",
                    "project": "$metadata.project",
                },
                "count": {"$sum": 1},
            }},
        ]
        agg = list(mongo_manager.documents_collection.aggregate(pipeline))
        stats = {"total_bugs": total_bugs, "by_type": {}, "by_severity": {}, "by_status": {}, "by_project": {}, "database": "MongoDB", "ai_model": "gemini-2.0-flash-exp"}
        for r in agg:
            gid, count = r["_id"], r["count"]
            if gid.get("type"):     stats["by_type"][gid["type"]] = stats["by_type"].get(gid["type"], 0) + count
            if gid.get("severity"): stats["by_severity"][gid["severity"]] = stats["by_severity"].get(gid["severity"], 0) + count
            if gid.get("status"):   stats["by_status"][gid["status"]] = stats["by_status"].get(gid["status"], 0) + count
            if gid.get("project"):  stats["by_project"][gid["project"]] = stats["by_project"].get(gid["project"], 0) + count
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Stats failed: {str(e)}")

@router.post("/bug-catalog/import/csv")
async def import_bugs_from_csv(file: UploadFile = File(...)):
    ensure_inited()
    try:
        if not file.filename.endswith(".csv"):
            raise HTTPException(status_code=400, detail="File must be CSV")
        content = await file.read()
        csv_content = content.decode("utf-8")
        csv_reader = csv.DictReader(csv_content.splitlines())
        bugs = []
        for row in csv_reader:
            try:
                bug = BugItem(
                    name=row.get("name",""),
                    description=row.get("description",""),
                    type=BugType(row.get("type","BUG")),
                    severity=BugSeverity(row.get("severity","MAJOR")) if row.get("severity") else BugSeverity.MAJOR,
                    status=BugStatus(row.get("status","OPEN")) if row.get("status") else BugStatus.OPEN,
                    labels=row.get("labels","").split(",") if row.get("labels") else [],
                    file_path=row.get("file_path"),
                    line_number=int(row.get("line_number", 0)) if row.get("line_number") else None,
                    component=row.get("component"),
                    project=row.get("project"),
                    assignee=row.get("assignee"),
                    reporter=row.get("reporter"),
                    created_date=row.get("created_date"),
                    updated_date=row.get("updated_date"),
                    resolution=row.get("resolution"),
                    effort=row.get("effort"),
                    debt=row.get("debt"),
                    tags=row.get("tags","").split(",") if row.get("tags") else [],
                )
                bugs.append(bug)
            except Exception:
                continue
        if not bugs:
            raise HTTPException(status_code=400, detail="No valid bugs found in CSV")
        import_request = BugImportRequest(
            bugs=bugs,
            project_name=f"csv_import_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
            import_source="csv_file",
            batch_name=f"csv_{file.filename}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
        )
        result = await import_bugs(import_request)
        result["source_file"] = file.filename
        result["total_rows_processed"] = len(bugs)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"CSV import failed: {str(e)}")
