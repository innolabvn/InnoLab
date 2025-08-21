#!/usr/bin/env python3
"""
RAG Bug Management API Controller
Provides endpoints for importing bugs as RAG documents and fixing bugs
"""

import os
import json
from datetime import datetime
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel, Field
import google.generativeai as genai
from dotenv import load_dotenv
import numpy as np
from service.mongodb_service import MongoDBManager, get_mongo_manager
import uvicorn
from bson import ObjectId

# Load environment variables from root directory
root_env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), '.env')
load_dotenv(root_env_path)

# Configure Gemini
gemini_api_key = os.getenv("GEMINI_API_KEY")
if not gemini_api_key:
    raise ValueError("GEMINI_API_KEY not found in environment variables")

genai.configure(api_key=gemini_api_key)

# Initialize APIRouter
app = APIRouter()

# Pydantic Models
class BugRAGItem(BaseModel):
    """Bug item for RAG import"""
    name: str = Field(..., description="Bug name")
    description: str = Field(..., description="Bug description")
    type: str = Field(default="BUG", description="Bug type (BUG, CODE_SMELL, VULNERABILITY, etc.)")
    severity: str = Field(default="MEDIUM", description="Bug severity (LOW, MEDIUM, HIGH, CRITICAL)")
    status: str = Field(default="OPEN", description="Bug status")
    file_path: Optional[str] = Field(None, description="File path where bug is located")
    line_number: Optional[int] = Field(None, description="Line number of the bug")
    code_snippet: Optional[str] = Field(None, description="Code snippet containing the bug")
    labels: List[str] = Field(default_factory=list, description="Bug labels")
    project: Optional[str] = Field(None, description="Project name")
    component: Optional[str] = Field(None, description="Component name")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

class BugRAGImportRequest(BaseModel):
    """Request for importing bugs as RAG documents"""
    bugs: List[BugRAGItem]
    collection_name: str = Field(default="bug_rag_documents", description="MongoDB collection name")
    generate_embeddings: bool = Field(default=True, description="Whether to generate embeddings")

class BugFixRequest(BaseModel):
    """Request for fixing a bug"""
    bug_id: str = Field(..., description="Bug ID to fix")
    fix_description: str = Field(..., description="Description of the fix")
    fixed_code: Optional[str] = Field(None, description="Fixed code snippet")
    fix_type: str = Field(default="MANUAL", description="Type of fix (MANUAL, AUTOMATED, AI_SUGGESTED)")
    fixed_by: Optional[str] = Field(None, description="Person who fixed the bug")
    fix_notes: Optional[str] = Field(None, description="Additional notes about the fix")

class BugSearchRequest(BaseModel):
    """Request for searching bugs in RAG"""
    query: str = Field(..., description="Search query")
    collection_name: str = Field(default="bug_rag_documents", description="MongoDB collection name")
    top_k: int = Field(default=5, description="Number of results to return")
    filters: Dict[str, Any] = Field(default_factory=dict, description="Additional filters")

class BugFixSuggestionRequest(BaseModel):
    """Request for AI-powered bug fix suggestions"""
    bug_id: str = Field(..., description="Bug ID to get fix suggestions for")
    collection_name: str = Field(default="bug_rag_documents", description="MongoDB collection name")
    include_similar_fixes: bool = Field(default=True, description="Include similar fixes from RAG")

# Helper Functions
def generate_gemini_embedding(text: str) -> List[float]:
    """Generate embedding using Gemini"""
    try:
        model = genai.GenerativeModel('gemini-2.0-flash-exp')
        result = genai.embed_content(
            model="models/text-embedding-004",
            content=text,
            task_type="retrieval_document"
        )
        return result['embedding']
    except Exception as e:
        print(f"Error generating embedding: {e}")
        return [0.0] * 768  # Default embedding size

def format_bug_for_rag(bug: BugRAGItem) -> str:
    """Format bug information for RAG processing"""
    content_parts = [
        f"Bug Name: {bug.name}",
        f"Description: {bug.description}",
        f"Type: {bug.type}",
        f"Severity: {bug.severity}",
        f"Status: {bug.status}"
    ]
    
    if bug.file_path:
        content_parts.append(f"File: {bug.file_path}")
    
    if bug.line_number:
        content_parts.append(f"Line: {bug.line_number}")
    
    if bug.code_snippet:
        content_parts.append(f"Code Snippet:\n{bug.code_snippet}")
    
    if bug.labels:
        content_parts.append(f"Labels: {', '.join(bug.labels)}")
    
    if bug.project:
        content_parts.append(f"Project: {bug.project}")
    
    if bug.component:
        content_parts.append(f"Component: {bug.component}")
    
    return "\n".join(content_parts)

def create_bug_rag_metadata(bug: BugRAGItem) -> Dict[str, Any]:
    """Create metadata for bug RAG document"""
    metadata = {
        "bug_name": bug.name,
        "bug_type": bug.type,
        "severity": bug.severity,
        "status": bug.status,
        "labels": bug.labels,
        "created_at": datetime.utcnow(),
        "document_type": "bug_rag"
    }
    
    if bug.file_path:
        metadata["file_path"] = bug.file_path
    
    if bug.line_number:
        metadata["line_number"] = bug.line_number
    
    if bug.project:
        metadata["project"] = bug.project
    
    if bug.component:
        metadata["component"] = bug.component
    
    # Add custom metadata
    metadata.update(bug.metadata)
    
    return metadata

def convert_objectid_to_str(obj):
    """Convert ObjectId to string for JSON serialization"""
    if isinstance(obj, ObjectId):
        return str(obj)
    elif isinstance(obj, datetime):
        return obj.isoformat()
    elif isinstance(obj, dict):
        return {key: convert_objectid_to_str(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [convert_objectid_to_str(item) for item in obj]
    return obj

# API Endpoints
@app.post("/rag-bugs/import")
async def import_bugs_as_rag(request: BugRAGImportRequest):
    """Import bugs as RAG documents into MongoDB"""
    try:
        mongo_manager = get_mongo_manager()
        collection = mongo_manager.get_collection(request.collection_name)
        
        imported_bugs = []
        
        for bug in request.bugs:
            # Format bug content for RAG
            content = format_bug_for_rag(bug)
            
            # Generate embedding if requested
            embedding = None
            if request.generate_embeddings:
                embedding = generate_gemini_embedding(content)
            
            # Create metadata
            metadata = create_bug_rag_metadata(bug)
            
            # Create document
            document = {
                "content": content,
                "metadata": metadata,
                "embedding": embedding,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
            
            # Insert into MongoDB
            result = collection.insert_one(document)
            
            imported_bugs.append({
                "bug_id": str(result.inserted_id),
                "bug_name": bug.name,
                "status": "imported"
            })
        
        return {
            "message": f"Successfully imported {len(imported_bugs)} bugs as RAG documents",
            "collection": request.collection_name,
            "imported_bugs": imported_bugs,
            "total_imported": len(imported_bugs)
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error importing bugs: {str(e)}")

@app.post("/rag-bugs/search")
async def search_bugs_in_rag(request: BugSearchRequest):
    """Search for bugs in RAG collection"""
    try:
        mongo_manager = get_mongo_manager()
        collection = mongo_manager.get_collection(request.collection_name)
        
        # Generate query embedding
        query_embedding = generate_gemini_embedding(request.query)
        
        # Build search pipeline
        pipeline = [
            {
                "$vectorSearch": {
                    "index": "vector_index",
                    "path": "embedding",
                    "queryVector": query_embedding,
                    "numCandidates": request.top_k * 10,
                    "limit": request.top_k
                }
            }
        ]
        
        # Add filters if provided
        if request.filters:
            match_stage = {"$match": {}}
            for key, value in request.filters.items():
                match_stage["$match"][f"metadata.{key}"] = value
            pipeline.append(match_stage)
        
        # Execute search
        results = list(collection.aggregate(pipeline))
        
        # Convert ObjectId to string
        results = convert_objectid_to_str(results)
        
        return {
            "query": request.query,
            "results": results,
            "total_found": len(results),
            "collection": request.collection_name
        }
    
    except Exception as e:
        # Fallback to text search if vector search fails
        try:
            mongo_manager = get_mongo_manager()
            collection = mongo_manager.get_collection(request.collection_name)
            
            search_filter = {
                "$or": [
                    {"content": {"$regex": request.query, "$options": "i"}},
                    {"metadata.bug_name": {"$regex": request.query, "$options": "i"}},
                    {"metadata.description": {"$regex": request.query, "$options": "i"}}
                ]
            }
            
            # Add additional filters
            for key, value in request.filters.items():
                search_filter[f"metadata.{key}"] = value
            
            results = list(collection.find(search_filter).limit(request.top_k))
            results = convert_objectid_to_str(results)
            
            return {
                "query": request.query,
                "results": results,
                "total_found": len(results),
                "collection": request.collection_name,
                "search_type": "text_fallback"
            }
        except Exception as fallback_error:
            raise HTTPException(status_code=500, detail=f"Error searching bugs: {str(fallback_error)}")

@app.post("/rag-bugs/fix")
async def fix_bug(request: BugFixRequest):
    """Fix a bug and update its status in the collection"""
    try:
        mongo_manager = get_mongo_manager()
        collection = mongo_manager.get_collection("bug_rag_documents")
        
        # Find the bug
        bug_doc = collection.find_one({"_id": ObjectId(request.bug_id)})
        if not bug_doc:
            raise HTTPException(status_code=404, detail="Bug not found")
        
        # Create fix record
        fix_record = {
            "fix_description": request.fix_description,
            "fixed_code": request.fixed_code,
            "fix_type": request.fix_type,
            "fixed_by": request.fixed_by,
            "fix_notes": request.fix_notes,
            "fixed_at": datetime.utcnow()
        }
        
        # Update bug document
        update_data = {
            "$set": {
                "metadata.status": "FIXED",
                "metadata.fix_record": fix_record,
                "updated_at": datetime.utcnow()
            }
        }
        
        # Add fix information to content for better RAG retrieval
        if request.fixed_code:
            fix_content = f"\n\nFIX APPLIED:\nDescription: {request.fix_description}\nFixed Code:\n{request.fixed_code}"
            update_data["$set"]["content"] = bug_doc["content"] + fix_content
            
            # Regenerate embedding with fix information
            new_embedding = generate_gemini_embedding(update_data["$set"]["content"])
            update_data["$set"]["embedding"] = new_embedding
        
        # Update the document
        result = collection.update_one(
            {"_id": ObjectId(request.bug_id)},
            update_data
        )
        
        if result.modified_count == 0:
            raise HTTPException(status_code=500, detail="Failed to update bug")
        
        return {
            "message": "Bug fixed successfully",
            "bug_id": request.bug_id,
            "fix_record": fix_record,
            "status": "FIXED"
        }
    
    except Exception as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=404, detail=str(e))
        raise HTTPException(status_code=500, detail=f"Error fixing bug: {str(e)}")

@app.post("/rag-bugs/suggest-fix")
async def suggest_bug_fix(request: BugFixSuggestionRequest):
    """Get AI-powered fix suggestions for a bug"""
    try:
        mongo_manager = get_mongo_manager()
        collection = mongo_manager.get_collection(request.collection_name)
        
        # Find the bug
        bug_doc = collection.find_one({"_id": ObjectId(request.bug_id)})
        if not bug_doc:
            raise HTTPException(status_code=404, detail="Bug not found")
        
        bug_content = bug_doc["content"]
        
        # Find similar fixed bugs if requested
        similar_fixes = []
        if request.include_similar_fixes:
            # Search for similar bugs that have been fixed
            search_filter = {
                "metadata.status": "FIXED",
                "metadata.bug_type": bug_doc["metadata"].get("bug_type"),
                "_id": {"$ne": ObjectId(request.bug_id)}
            }
            
            similar_bugs = list(collection.find(search_filter).limit(3))
            for similar_bug in similar_bugs:
                if "fix_record" in similar_bug["metadata"]:
                    similar_fixes.append({
                        "bug_name": similar_bug["metadata"].get("bug_name"),
                        "fix_description": similar_bug["metadata"]["fix_record"].get("fix_description"),
                        "fixed_code": similar_bug["metadata"]["fix_record"].get("fixed_code")
                    })
        
        # Generate AI fix suggestion
        model = genai.GenerativeModel('gemini-2.0-flash-exp')
        
        prompt = f"""
Analyze the following bug and provide fix suggestions:

BUG INFORMATION:
{bug_content}

"""
        
        if similar_fixes:
            prompt += "\nSIMILAR FIXES FOR REFERENCE:\n"
            for i, fix in enumerate(similar_fixes, 1):
                prompt += f"\n{i}. {fix['bug_name']}\n"
                prompt += f"   Fix: {fix['fix_description']}\n"
                if fix['fixed_code']:
                    prompt += f"   Code: {fix['fixed_code']}\n"
        
        prompt += """

Please provide:
1. Root cause analysis
2. Recommended fix approach
3. Code suggestions (if applicable)
4. Potential risks or considerations
5. Testing recommendations

Format your response in a clear, structured manner.
"""
        
        response = model.generate_content(prompt)
        
        return {
            "bug_id": request.bug_id,
            "bug_content": bug_content,
            "ai_suggestion": response.text,
            "similar_fixes": similar_fixes,
            "generated_at": datetime.utcnow().isoformat()
        }
    
    except Exception as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=404, detail=str(e))
        raise HTTPException(status_code=500, detail=f"Error generating fix suggestion: {str(e)}")

@app.get("/rag-bugs/stats")
async def get_rag_bug_stats():
    """Get statistics about bugs in RAG collection"""
    try:
        mongo_manager = get_mongo_manager()
        collection = mongo_manager.get_collection("bug_rag_documents")
        
        # Get total count
        total_bugs = collection.count_documents({})
        
        # Get stats by status
        status_pipeline = [
            {"$group": {
                "_id": "$metadata.status",
                "count": {"$sum": 1}
            }}
        ]
        status_stats = list(collection.aggregate(status_pipeline))
        
        # Get stats by type
        type_pipeline = [
            {"$group": {
                "_id": "$metadata.bug_type",
                "count": {"$sum": 1}
            }}
        ]
        type_stats = list(collection.aggregate(type_pipeline))
        
        # Get stats by severity
        severity_pipeline = [
            {"$group": {
                "_id": "$metadata.severity",
                "count": {"$sum": 1}
            }}
        ]
        severity_stats = list(collection.aggregate(severity_pipeline))
        
        return {
            "total_bugs": total_bugs,
            "by_status": {stat["_id"]: stat["count"] for stat in status_stats},
            "by_type": {stat["_id"]: stat["count"] for stat in type_stats},
            "by_severity": {stat["_id"]: stat["count"] for stat in severity_stats},
            "collection": "bug_rag_documents"
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting stats: {str(e)}")

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        mongo_manager = get_mongo_manager()
        # Test MongoDB connection
        mongo_manager.client.admin.command('ping')
        return {
            "status": "healthy",
            "mongodb": "connected",
            "gemini": "configured" if gemini_api_key else "not_configured",
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }

if __name__ == "__main__":
    print("Starting RAG Bug Management API...")
    print("MongoDB connection:", os.getenv("MONGODB_URI", "Not configured"))
    print("Gemini API:", "Configured" if gemini_api_key else "Not configured")
    print("API Documentation: http://localhost:8002/docs")
    
    uvicorn.run(app, host="0.0.0.0", port=8002)