#!/usr/bin/env python3
"""
AutoFixModule - Automated Code Fixing Service
Tập trung vào các chức năng auto-fix từ SonarQ và FixChain
"""

import uvicorn
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from typing import List, Dict, Optional
from pydantic import BaseModel
import json

# Add current directory to path for imports
sys.path.append(str(Path(__file__).parent))

# Load environment variables
load_dotenv()

# Import batch_fix functionality
from batch_fix import SecureFixProcessor, FixResult
from utils.logger import logger

# Create AutoFix FastAPI application
app = FastAPI(
    title="AutoFixModule - Automated Code Fixing Service",
    description="""
    Hệ thống tự động sửa lỗi code sử dụng AI (Gemini) với các template prompt.
    
    ## Tính năng chính:
    
    ### 🔧 Auto Fix (Core)
    - Tự động sửa lỗi code với AI
    - Hỗ trợ nhiều ngôn ngữ lập trình
    - Validation và backup tự động
    - Template prompt có thể tùy chỉnh
    
    ### 📊 Batch Processing
    - Xử lý hàng loạt file
    - Báo cáo chi tiết kết quả
    - Theo dõi tiến độ real-time
    
    ### 🛡️ Security & Safety
    - Backup tự động trước khi fix
    - Code validation
    - Similarity checking
    - Safe rollback
    
    ## Technology Stack:
    - **AI Model**: Google Gemini 2.0 Flash
    - **Framework**: FastAPI + Python
    - **Template Engine**: Jinja2
    - **Validation**: AST parsing
    """,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic models
class FixRequest(BaseModel):
    file_path: str
    template_type: str = "fix"
    custom_prompt: Optional[str] = None
    max_retries: int = 2
    enable_rag: bool = False

class BatchFixRequest(BaseModel):
    source_directory: str
    file_patterns: List[str] = ["*.py", "*.js", "*.html", "*.css"]
    template_type: str = "fix"
    custom_prompt: Optional[str] = None
    max_retries: int = 2
    enable_rag: bool = False

# Global processor instance
processor = None

def get_processor():
    global processor
    if processor is None:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise HTTPException(status_code=500, detail="GEMINI_API_KEY not found in environment")
        
        source_dir = os.getenv("SOURCE_DIR", "./temp")
        backup_dir = os.getenv("BACKUP_DIR", "./backups")
        
        processor = SecureFixProcessor(
            api_key=api_key,
            source_dir=source_dir,
            backup_dir=backup_dir
        )
    return processor

@app.get("/")
async def root():
    return {
        "message": "AutoFixModule - Automated Code Fixing Service is running!",
        "version": "1.0.0",
        "docs": "/docs"
    }

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "AutoFixModule"}

@app.post("/api/v1/fix/single")
async def fix_single_file(request: FixRequest):
    """
    Sửa một file đơn lẻ
    """
    try:
        proc = get_processor()
        result = proc.fix_file_with_validation(
            file_path=request.file_path,
            template_type=request.template_type,
            custom_prompt=request.custom_prompt,
            max_retries=request.max_retries,
            enable_rag=request.enable_rag
        )
        
        return {
            "success": result.success,
            "file_path": result.file_path,
            "issues_found": result.issues_found,
            "validation_errors": result.validation_errors,
            "backup_path": result.backup_path,
            "processing_time": result.processing_time,
            "similarity_ratio": result.similarity_ratio,
            "token_usage": {
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "total_tokens": result.total_tokens
            }
        }
    except Exception as e:
        logger.error(f"Error fixing file {request.file_path}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/fix/scan-only")
async def scan_file_only(file_path: str):
    """
    Chỉ scan file để tìm lỗi, không sửa
    """
    try:
        proc = get_processor()
        result = proc.scan_file_only(file_path)
        
        return {
            "success": result.success,
            "file_path": result.file_path,
            "issues_found": result.issues_found,
            "validation_errors": result.validation_errors,
            "processing_time": result.processing_time
        }
    except Exception as e:
        logger.error(f"Error scanning file {file_path}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/fix/batch")
async def batch_fix_files(request: BatchFixRequest):
    """
    Sửa hàng loạt file trong thư mục
    """
    try:
        proc = get_processor()
        results = []
        
        # Tìm tất cả file matching patterns
        source_path = Path(request.source_directory)
        if not source_path.exists():
            raise HTTPException(status_code=404, detail=f"Directory not found: {request.source_directory}")
        
        files_to_process = []
        for pattern in request.file_patterns:
            files_to_process.extend(source_path.rglob(pattern))
        
        # Process each file
        for file_path in files_to_process:
            if proc.should_ignore_file(str(file_path), request.source_directory):
                continue
                
            result = proc.fix_file_with_validation(
                file_path=str(file_path),
                template_type=request.template_type,
                custom_prompt=request.custom_prompt,
                max_retries=request.max_retries,
                enable_rag=request.enable_rag
            )
            
            results.append({
                "file_path": result.file_path,
                "success": result.success,
                "issues_found": len(result.issues_found),
                "validation_errors": len(result.validation_errors),
                "processing_time": result.processing_time,
                "similarity_ratio": result.similarity_ratio
            })
        
        # Summary statistics
        total_files = len(results)
        successful_fixes = sum(1 for r in results if r["success"])
        total_issues = sum(r["issues_found"] for r in results)
        
        return {
            "summary": {
                "total_files": total_files,
                "successful_fixes": successful_fixes,
                "failed_fixes": total_files - successful_fixes,
                "total_issues_found": total_issues
            },
            "results": results
        }
        
    except Exception as e:
        logger.error(f"Error in batch fix: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Additional models for new endpoints
class AnalyzeRequest(BaseModel):
    bugs: List[Dict]
    use_rag: bool = False
    mode: str = "local"

class FixRequest(BaseModel):
    bugs: List[Dict]
    project_path: str
    use_rag: bool = False
    mode: str = "local"

@app.post("/analyze")
async def analyze_bugs(request: AnalyzeRequest):
    """
    Analyze bugs to determine which ones are real and need fixing
    """
    try:
        logger.info(f"Analyzing {len(request.bugs)} bugs")
        
        # For now, we'll implement a simple analysis
        # In a full implementation, this would use AI analysis
        real_bugs = []
        
        for bug in request.bugs:
            # Simple filtering - consider bugs with high severity as real
            severity = bug.get('severity', '').upper()
            if severity in ['BLOCKER', 'CRITICAL', 'MAJOR']:
                real_bugs.append(bug)
        
        result = {
            "status": "success",
            "total_bugs": len(request.bugs),
            "bugs_to_fix": len(real_bugs),
            "list_bugs": real_bugs,
            "analysis_summary": {
                "high_priority": len([b for b in real_bugs if b.get('severity', '').upper() in ['BLOCKER', 'CRITICAL']]),
                "medium_priority": len([b for b in real_bugs if b.get('severity', '').upper() == 'MAJOR']),
                "filtered_out": len(request.bugs) - len(real_bugs)
            }
        }
        
        logger.info(f"Analysis completed: {len(real_bugs)} real bugs identified")
        return result
        
    except Exception as e:
        logger.error(f"Error analyzing bugs: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/fix")
async def fix_bugs(request: FixRequest):
    """
    Fix bugs in the specified project
    """
    try:
        logger.info(f"Fixing {len(request.bugs)} bugs in project: {request.project_path}")
        
        # Get API key from environment
        api_key = os.getenv('GEMINI_API_KEY')
        if not api_key:
            raise HTTPException(status_code=500, detail="GEMINI_API_KEY not found in environment")
        
        # Initialize the fix processor
        processor = SecureFixProcessor(
            api_key=api_key,
            source_dir=request.project_path,
            backup_dir=os.path.join(request.project_path, "backups")
        )
        
        fixed_count = 0
        failed_count = 0
        fix_details = []
        
        for bug in request.bugs:
            try:
                # Extract file path from bug info
                component = bug.get('component', '')
                if component:
                    file_path = os.path.join(request.project_path, component)
                    
                    if os.path.exists(file_path):
                        # Process the file
                        result = processor.fix_file_with_validation(
                            file_path=file_path,
                            template_type="fix",  # Use fix template
                            custom_prompt=f"Fix this security issue: {bug.get('message', '')}",
                            enable_rag=request.use_rag
                        )
                        
                        if result.success:
                            fixed_count += 1
                            fix_details.append({
                                "file": component,
                                "bug_key": bug.get('key', ''),
                                "status": "fixed",
                                "message": "Successfully fixed"
                            })
                        else:
                            failed_count += 1
                            fix_details.append({
                                "file": component,
                                "bug_key": bug.get('key', ''),
                                "status": "failed",
                                "message": "Fix failed"
                            })
                    else:
                        failed_count += 1
                        fix_details.append({
                            "file": component,
                            "bug_key": bug.get('key', ''),
                            "status": "failed",
                            "message": "File not found"
                        })
                        
            except Exception as bug_error:
                logger.error(f"Error fixing bug {bug.get('key', '')}: {str(bug_error)}")
                failed_count += 1
                fix_details.append({
                    "file": bug.get('component', ''),
                    "bug_key": bug.get('key', ''),
                    "status": "failed",
                    "message": str(bug_error)
                })
        
        result = {
            "success": fixed_count > 0,
            "fixed_count": fixed_count,
            "failed_count": failed_count,
            "total_bugs": len(request.bugs),
            "fix_details": fix_details,
            "summary": {
                "success_rate": (fixed_count / len(request.bugs)) * 100 if request.bugs else 0,
                "project_path": request.project_path,
                "use_rag": request.use_rag,
                "mode": request.mode
            }
        }
        
        logger.info(f"Fix completed: {fixed_count} fixed, {failed_count} failed")
        return result
        
    except Exception as e:
        logger.error(f"Error fixing bugs: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/templates")
async def list_templates():
    """
    Liệt kê các template prompt có sẵn
    """
    try:
        prompt_dir = Path(__file__).parent / "prompt"
        templates = []
        
        if prompt_dir.exists():
            for template_file in prompt_dir.glob("*.j2"):
                templates.append({
                    "name": template_file.stem,
                    "file": template_file.name,
                    "path": str(template_file)
                })
        
        return {"templates": templates}
    except Exception as e:
        logger.error(f"Error listing templates: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    port = int(os.getenv("AUTOFIX_PORT", 8002))
    logger.info(f"Starting AutoFixModule on port {port}")
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=True,
        log_level="info"
    )