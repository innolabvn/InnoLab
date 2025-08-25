#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bug Import API - Hệ thống import và quản lý bugs
Tích hợp với RAG MongoDB + Gemini Flash 2.0
"""

import os
import json
import csv
from datetime import datetime
from typing import List, Dict, Any, Optional
from enum import Enum
from pydantic import BaseModel, Field
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import JSONResponse
import google.generativeai as genai
from modules.mongodb_service import MongoDBManager
from dotenv import load_dotenv

# Load environment variables from root directory
root_env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), '.env')
load_dotenv(root_env_path)

# Global resources initialized at startup
mongo_manager: Optional[MongoDBManager] = None
llm_model = None

def init_resources():
    global mongo_manager, llm_model
    if llm_model is None:
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        llm_model = genai.GenerativeModel('gemini-2.0-flash-exp')
    if mongo_manager is None:
        mongo_manager = MongoDBManager()

# Bug Types Enum
class BugType(str, Enum):
    CODE_SMELL = "CODE_SMELL"
    BUG = "BUG"
    VULNERABILITY = "VULNERABILITY"
    SECURITY_HOTSPOT = "SECURITY_HOTSPOT"
    PERFORMANCE = "PERFORMANCE"
    MAINTAINABILITY = "MAINTAINABILITY"
    RELIABILITY = "RELIABILITY"
    DUPLICATION = "DUPLICATION"

# Bug Severity Enum
class BugSeverity(str, Enum):
    BLOCKER = "BLOCKER"
    CRITICAL = "CRITICAL"
    MAJOR = "MAJOR"
    MINOR = "MINOR"
    INFO = "INFO"

# Bug Status Enum
class BugStatus(str, Enum):
    OPEN = "OPEN"
    CONFIRMED = "CONFIRMED"
    REOPENED = "REOPENED"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"
    FALSE_POSITIVE = "FALSE_POSITIVE"
    WONT_FIX = "WONT_FIX"

# Pydantic Models
class BugItem(BaseModel):
    name: str = Field(..., description="Tên bug")
    description: str = Field(..., description="Mô tả chi tiết bug")
    type: BugType = Field(..., description="Loại bug")
    severity: Optional[BugSeverity] = Field(BugSeverity.MAJOR, description="Mức độ nghiêm trọng")
    status: Optional[BugStatus] = Field(BugStatus.OPEN, description="Trạng thái bug")
    labels: Optional[List[str]] = Field(default=[], description="Danh sách labels")
    file_path: Optional[str] = Field(None, description="Đường dẫn file")
    line_number: Optional[int] = Field(None, description="Số dòng")
    component: Optional[str] = Field(None, description="Component/Module")
    project: Optional[str] = Field(None, description="Tên project")
    assignee: Optional[str] = Field(None, description="Người được assign")
    reporter: Optional[str] = Field(None, description="Người báo cáo")
    created_date: Optional[str] = Field(None, description="Ngày tạo")
    updated_date: Optional[str] = Field(None, description="Ngày cập nhật")
    resolution: Optional[str] = Field(None, description="Cách giải quyết")
    effort: Optional[str] = Field(None, description="Thời gian ước tính")
    debt: Optional[str] = Field(None, description="Technical debt")
    tags: Optional[List[str]] = Field(default=[], description="Tags bổ sung")

class BugImportRequest(BaseModel):
    bugs: List[BugItem] = Field(..., description="Danh sách bugs")
    project_name: Optional[str] = Field(None, description="Tên project")
    import_source: Optional[str] = Field("manual", description="Nguồn import")
    batch_name: Optional[str] = Field(None, description="Tên batch import")

class BugSearchRequest(BaseModel):
    query: str = Field(..., description="Câu hỏi tìm kiếm")
    bug_types: Optional[List[BugType]] = Field(None, description="Lọc theo loại bug")
    severities: Optional[List[BugSeverity]] = Field(None, description="Lọc theo mức độ")
    labels: Optional[List[str]] = Field(None, description="Lọc theo labels")
    project: Optional[str] = Field(None, description="Lọc theo project")
    limit: Optional[int] = Field(5, description="Số lượng kết quả")

class BugAnalysisRequest(BaseModel):
    bug_ids: Optional[List[str]] = Field(None, description="Danh sách bug IDs")
    analysis_type: str = Field("summary", description="Loại phân tích: summary, trend, priority")
    project: Optional[str] = Field(None, description="Lọc theo project")
    time_range: Optional[str] = Field(None, description="Khoảng thời gian")

# Helper Functions
async def get_gemini_embedding(text: str) -> List[float]:
    """Get embedding from Gemini Flash 2.0"""
    try:
        result = genai.embed_content(
            model="models/text-embedding-004",
            content=text,
            task_type="retrieval_document"
        )
        return result['embedding']
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating embedding: {str(e)}")

def format_bug_content(bug: BugItem) -> str:
    """Format bug information into searchable content"""
    content_parts = [
        f"Bug Name: {bug.name}",
        f"Description: {bug.description}",
        f"Type: {bug.type.value}",
        f"Severity: {bug.severity.value if bug.severity else 'Unknown'}",
        f"Status: {bug.status.value if bug.status else 'Unknown'}"
    ]
    
    if bug.labels:
        content_parts.append(f"Labels: {', '.join(bug.labels)}")
    
    if bug.file_path:
        content_parts.append(f"File: {bug.file_path}")
    
    if bug.line_number:
        content_parts.append(f"Line: {bug.line_number}")
    
    if bug.component:
        content_parts.append(f"Component: {bug.component}")
    
    if bug.resolution:
        content_parts.append(f"Resolution: {bug.resolution}")
    
    if bug.tags:
        content_parts.append(f"Tags: {', '.join(bug.tags)}")
    
    return "\n".join(content_parts)

def create_bug_metadata(bug: BugItem, import_info: Dict) -> Dict:
    """Create metadata for bug document"""
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
        "imported_at": datetime.now().isoformat()
    }
    
    # Remove None values
    return {k: v for k, v in metadata.items() if v is not None}

def convert_mongodb_to_json(data):
    """Convert MongoDB documents to JSON-serializable format"""
    from bson import ObjectId
    from datetime import datetime
    
    if isinstance(data, list):
        return [convert_mongodb_to_json(item) for item in data]
    elif isinstance(data, dict):
        result = {}
        for key, value in data.items():
            result[key] = convert_mongodb_to_json(value)
        return result
    elif isinstance(data, ObjectId):
        return str(data)  # Convert ObjectId to string
    elif isinstance(data, datetime):
        return data.isoformat()  # Convert datetime to ISO string
    else:
        return data

async def generate_bug_analysis(bugs_data: List[Dict], analysis_type: str) -> str:
    """Generate analysis using Gemini Flash 2.0"""
    try:
        # Convert MongoDB data to JSON-serializable format
        serializable_data = convert_mongodb_to_json(bugs_data[:10])
        
        if analysis_type == "summary":
            prompt = f"""
Phân tích tổng quan về {len(bugs_data)} bugs sau đây:

{json.dumps(serializable_data, indent=2, ensure_ascii=False)}

Hãy cung cấp:
1. Tổng quan về số lượng bugs theo loại
2. Phân tích mức độ nghiêm trọng
3. Các vấn đề phổ biến nhất
4. Đề xuất ưu tiên xử lý
5. Xu hướng và pattern

Trả lời bằng tiếng Việt, chi tiết và có cấu trúc.
"""
        elif analysis_type == "trend":
            prompt = f"""
Phân tích xu hướng bugs từ dữ liệu sau:

{json.dumps(serializable_data, indent=2, ensure_ascii=False)}

Hãy phân tích:
1. Xu hướng theo thời gian
2. Pattern theo component/file
3. Phân bố theo loại bug
4. Dự đoán và khuyến nghị

Trả lời bằng tiếng Việt.
"""
        elif analysis_type == "priority":
            prompt = f"""
Đề xuất ưu tiên xử lý bugs dựa trên dữ liệu:

{json.dumps(serializable_data, indent=2, ensure_ascii=False)}

Hãy đưa ra:
1. Danh sách bugs ưu tiên cao
2. Lý do ưu tiên
3. Thứ tự xử lý đề xuất
4. Ước tính effort

Trả lời bằng tiếng Việt.
"""
        elif analysis_type == "search_answer":
            # For search results, create a summary of found bugs
            bug_summaries = []
            for bug in serializable_data:
                metadata = bug.get("metadata", {})
                bug_summaries.append({
                    "name": metadata.get("bug_name"),
                    "type": metadata.get("bug_type"),
                    "severity": metadata.get("severity"),
                    "component": metadata.get("component"),
                    "description": bug.get("content", "")[:200]
                })
            
            prompt = f"""
Dựa trên kết quả tìm kiếm, hãy tóm tắt và phân tích các bugs sau:

{json.dumps(bug_summaries, indent=2, ensure_ascii=False)}

Hãy cung cấp:
1. Tóm tắt các bugs tìm thấy
2. Mức độ nghiêm trọng và ưu tiên
3. Khuyến nghị xử lý
4. Mối liên hệ giữa các bugs

Trả lời bằng tiếng Việt, ngắn gọn và súc tích.
"""
        else:
            prompt = f"Phân tích dữ liệu bugs: {json.dumps(serializable_data[:5], ensure_ascii=False)}"
        
        response = llm_model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Không thể tạo phân tích: {str(e)}"

# API Endpoints
from fastapi import APIRouter

app = APIRouter()

@app.on_event("startup")
async def startup_event():
    init_resources()

@app.get("/health")
async def health_check():
    """Health check endpoint for Bug Management API"""
    try:
        # Test MongoDB connection
        total_bugs = mongo_manager.documents_collection.count_documents({
            "metadata.document_type": "bug"
        })
        return {
            "status": "healthy",
            "service": "bug_management",
            "database": "connected",
            "total_bugs": total_bugs,
            "ai_model": "gemini-2.0-flash-exp"
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "service": "bug_management",
            "error": str(e)
        }

@app.post("/bugs/import")
async def import_bugs(request: BugImportRequest):
    """Import danh sách bugs vào hệ thống"""
    try:
        imported_bugs = []
        failed_bugs = []
        
        import_info = {
            "project_name": request.project_name,
            "import_source": request.import_source,
            "batch_name": request.batch_name or f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        }
        
        for i, bug in enumerate(request.bugs):
            try:
                # Format bug content for embedding
                bug_content = format_bug_content(bug)
                
                # Generate embedding
                embedding = await get_gemini_embedding(bug_content)
                
                # Create metadata
                metadata = create_bug_metadata(bug, import_info)
                
                # Add to MongoDB
                doc_id = mongo_manager.add_document(
                    content=bug_content,
                    embedding=embedding,
                    metadata=metadata
                )
                
                imported_bugs.append({
                    "bug_name": bug.name,
                    "document_id": doc_id,
                    "type": bug.type.value,
                    "severity": bug.severity.value if bug.severity else None
                })
                
            except Exception as e:
                failed_bugs.append({
                    "bug_name": bug.name,
                    "error": str(e),
                    "index": i
                })
        
        return {
            "message": f"Import completed: {len(imported_bugs)} success, {len(failed_bugs)} failed",
            "batch_name": import_info["batch_name"],
            "imported_count": len(imported_bugs),
            "failed_count": len(failed_bugs),
            "imported_bugs": imported_bugs,
            "failed_bugs": failed_bugs,
            "project": request.project_name
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Import failed: {str(e)}")

@app.post("/bugs/search")
async def search_bugs(request: BugSearchRequest):
    """Tìm kiếm bugs với AI-powered search"""
    try:
        # Generate query embedding
        query_embedding = await get_gemini_embedding(request.query)
        
        # Search in MongoDB
        results = mongo_manager.search_by_embedding(
            query_embedding=query_embedding,
            top_k=request.limit * 2  # Get more results for filtering
        )
        
        # Filter results based on criteria
        filtered_results = []
        for result in results:
            metadata = result.get("metadata", {})
            
            # Filter by bug type
            if request.bug_types and metadata.get("bug_type") not in [t.value for t in request.bug_types]:
                continue
            
            # Filter by severity
            if request.severities and metadata.get("severity") not in [s.value for s in request.severities]:
                continue
            
            # Filter by labels
            if request.labels:
                bug_labels = metadata.get("labels", [])
                if not any(label in bug_labels for label in request.labels):
                    continue
            
            # Filter by project
            if request.project and metadata.get("project") != request.project:
                continue
            
            filtered_results.append(result)
            
            if len(filtered_results) >= request.limit:
                break
        
        # Generate AI answer
        if filtered_results:
            answer = await generate_bug_analysis(filtered_results, "search_answer")
        else:
            answer = "Không tìm thấy bugs phù hợp với tiêu chí tìm kiếm."
        
        # Format response
        bugs_info = []
        for result in filtered_results:
            metadata = result.get("metadata", {})
            bugs_info.append({
                "bug_name": metadata.get("bug_name"),
                "type": metadata.get("bug_type"),
                "severity": metadata.get("severity"),
                "status": metadata.get("status"),
                "component": metadata.get("component"),
                "project": metadata.get("project"),
                "labels": metadata.get("labels", []),
                "similarity_score": result.get("similarity", 0),
                "content_preview": result["content"][:200] + "..." if len(result["content"]) > 200 else result["content"]
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
                "project": request.project
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")

@app.post("/bugs/analyze")
async def analyze_bugs(request: BugAnalysisRequest):
    """Phân tích bugs với AI"""
    try:
        # Get bugs data from MongoDB
        if request.bug_ids:
            # Get specific bugs by IDs
            bugs_data = []
            for bug_id in request.bug_ids:
                doc = mongo_manager.documents_collection.find_one({"doc_id": bug_id})
                if doc:
                    bugs_data.append(doc)
        else:
            # Get all bugs with filters
            query_filter = {"metadata.document_type": "bug"}
            
            if request.project:
                query_filter["metadata.project"] = request.project
            
            bugs_data = list(mongo_manager.documents_collection.find(query_filter).limit(100))
        
        if not bugs_data:
            return {
                "message": "Không tìm thấy bugs để phân tích",
                "analysis": "Không có dữ liệu bugs phù hợp."
            }
        
        # Generate analysis
        analysis = await generate_bug_analysis(bugs_data, request.analysis_type)
        
        # Calculate statistics
        stats = {
            "total_bugs": len(bugs_data),
            "by_type": {},
            "by_severity": {},
            "by_status": {},
            "projects": set()
        }
        
        for bug in bugs_data:
            metadata = bug.get("metadata", {})
            
            # Count by type
            bug_type = metadata.get("bug_type", "Unknown")
            stats["by_type"][bug_type] = stats["by_type"].get(bug_type, 0) + 1
            
            # Count by severity
            severity = metadata.get("severity", "Unknown")
            stats["by_severity"][severity] = stats["by_severity"].get(severity, 0) + 1
            
            # Count by status
            status = metadata.get("status", "Unknown")
            stats["by_status"][status] = stats["by_status"].get(status, 0) + 1
            
            # Collect projects
            if metadata.get("project"):
                stats["projects"].add(metadata["project"])
        
        stats["projects"] = list(stats["projects"])
        
        return {
            "analysis_type": request.analysis_type,
            "analysis": analysis,
            "statistics": stats,
            "analyzed_bugs_count": len(bugs_data)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")

@app.get("/bugs/stats")
async def get_bug_stats():
    """Lấy thống kê tổng quan về bugs"""
    try:
        # Count total bugs
        total_bugs = mongo_manager.documents_collection.count_documents({
            "metadata.document_type": "bug"
        })
        
        # Get aggregation stats
        pipeline = [
            {"$match": {"metadata.document_type": "bug"}},
            {"$group": {
                "_id": {
                    "type": "$metadata.bug_type",
                    "severity": "$metadata.severity",
                    "status": "$metadata.status",
                    "project": "$metadata.project"
                },
                "count": {"$sum": 1}
            }}
        ]
        
        aggregation_results = list(mongo_manager.documents_collection.aggregate(pipeline))
        
        # Process results
        stats = {
            "total_bugs": total_bugs,
            "by_type": {},
            "by_severity": {},
            "by_status": {},
            "by_project": {},
            "database": "MongoDB",
            "ai_model": "gemini-2.0-flash-exp"
        }
        
        for result in aggregation_results:
            group_id = result["_id"]
            count = result["count"]
            
            if group_id.get("type"):
                stats["by_type"][group_id["type"]] = stats["by_type"].get(group_id["type"], 0) + count
            
            if group_id.get("severity"):
                stats["by_severity"][group_id["severity"]] = stats["by_severity"].get(group_id["severity"], 0) + count
            
            if group_id.get("status"):
                stats["by_status"][group_id["status"]] = stats["by_status"].get(group_id["status"], 0) + count
            
            if group_id.get("project"):
                stats["by_project"][group_id["project"]] = stats["by_project"].get(group_id["project"], 0) + count
        
        return stats
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Stats failed: {str(e)}")

@app.post("/bugs/import/csv")
async def import_bugs_from_csv(file: UploadFile = File(...)):
    """Import bugs từ CSV file"""
    try:
        if not file.filename.endswith('.csv'):
            raise HTTPException(status_code=400, detail="File must be CSV format")
        
        # Read CSV content
        content = await file.read()
        csv_content = content.decode('utf-8')
        
        # Parse CSV
        csv_reader = csv.DictReader(csv_content.splitlines())
        bugs = []
        
        for row in csv_reader:
            try:
                bug = BugItem(
                    name=row.get('name', ''),
                    description=row.get('description', ''),
                    type=BugType(row.get('type', 'BUG')),
                    severity=BugSeverity(row.get('severity', 'MAJOR')) if row.get('severity') else BugSeverity.MAJOR,
                    status=BugStatus(row.get('status', 'OPEN')) if row.get('status') else BugStatus.OPEN,
                    labels=row.get('labels', '').split(',') if row.get('labels') else [],
                    file_path=row.get('file_path'),
                    line_number=int(row.get('line_number', 0)) if row.get('line_number') else None,
                    component=row.get('component'),
                    project=row.get('project'),
                    assignee=row.get('assignee'),
                    reporter=row.get('reporter'),
                    created_date=row.get('created_date'),
                    updated_date=row.get('updated_date'),
                    resolution=row.get('resolution'),
                    effort=row.get('effort'),
                    debt=row.get('debt'),
                    tags=row.get('tags', '').split(',') if row.get('tags') else []
                )
                bugs.append(bug)
            except Exception as e:
                print(f"Error parsing row: {row}, error: {e}")
                continue
        
        if not bugs:
            raise HTTPException(status_code=400, detail="No valid bugs found in CSV")
        
        # Import bugs
        import_request = BugImportRequest(
            bugs=bugs,
            project_name=f"csv_import_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            import_source="csv_file",
            batch_name=f"csv_{file.filename}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        )
        
        result = await import_bugs(import_request)
        result["source_file"] = file.filename
        result["total_rows_processed"] = len(bugs)
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"CSV import failed: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "bug_import_api:app",
        host="0.0.0.0",
        port=8001,
        reload=True
    )