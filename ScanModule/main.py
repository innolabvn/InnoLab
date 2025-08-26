#!/usr/bin/env python3
"""
ScanModule - Code Security Scanning Service
Tập trung vào các chức năng scan từ FixChain
"""

import uvicorn
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from typing import List, Dict, Optional
from pydantic import BaseModel
import asyncio
from datetime import datetime

# Add current directory to path for imports
sys.path.append(str(Path(__file__).parent))

# Load environment variables
load_dotenv()

# Import scanning functionality
from modules import BearerScanner, SonarQScanner, ScannerRegistry
from utils.logger import logger

# Create Scan FastAPI application
app = FastAPI(
    title="ScanModule - Code Security Scanning Service",
    description="""
    Hệ thống quét bảo mật code sử dụng nhiều scanner khác nhau.
    
    ## Tính năng chính:
    
    ### 🔍 Multi-Scanner Support
    - Bearer Scanner - Security vulnerability detection
    - SonarQube Scanner - Code quality and security
    - Extensible scanner registry
    
    ### 📊 Comprehensive Analysis
    - Vulnerability detection
    - Code quality metrics
    - Security hotspots
    - Technical debt analysis
    
    ### 🚀 Batch Processing
    - Scan multiple projects
    - Parallel scanning
    - Progress tracking
    - Detailed reporting
    
    ### 📈 Reporting & Export
    - JSON/CSV export
    - Dashboard integration
    - Historical tracking
    - Custom filters
    
    ## Supported Scanners:
    - **Bearer**: Security-focused static analysis
    - **SonarQube**: Comprehensive code quality
    - **Custom**: Extensible scanner framework
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
class ScanRequest(BaseModel):
    project_path: str
    scanner_type: str = "bearer"  # bearer, sonar, all
    output_format: str = "json"  # json, csv
    include_patterns: Optional[List[str]] = None
    exclude_patterns: Optional[List[str]] = None

class BatchScanRequest(BaseModel):
    projects: List[Dict[str, str]]  # [{"name": "project1", "path": "/path/to/project1"}]
    scanner_type: str = "bearer"
    output_format: str = "json"
    parallel: bool = True
    max_workers: int = 3

class ScanResult(BaseModel):
    project_name: str
    project_path: str
    scanner_type: str
    scan_time: datetime
    status: str  # success, failed, running
    issues_count: int
    vulnerabilities: List[Dict]
    code_smells: List[Dict]
    bugs: List[Dict]
    security_hotspots: List[Dict]
    execution_time: float
    error_message: Optional[str] = None

# Global scanner registry
scanner_registry = ScannerRegistry()

# Initialize scanners
def initialize_scanners():
    """Initialize available scanners"""
    try:
        # Register Bearer scanner
        bearer_config = {
            "bearer_path": os.getenv("BEARER_PATH", "bearer"),
            "timeout": int(os.getenv("BEARER_TIMEOUT", "300"))
        }
        scanner_registry.register("bearer", BearerScanner, bearer_config)
        
        # Register SonarQube scanner
        sonar_config = {
            "sonar_host": os.getenv("SONAR_HOST", "http://localhost:9000"),
            "sonar_token": os.getenv("SONAR_TOKEN"),
            "sonar_scanner_path": os.getenv("SONAR_SCANNER_PATH", "sonar-scanner")
        }
        if sonar_config["sonar_token"]:
            scanner_registry.register("sonar", SonarQScanner, sonar_config)
        
        logger.info(f"Initialized {len(scanner_registry.list_scanners())} scanners")
    except Exception as e:
        logger.error(f"Error initializing scanners: {str(e)}")

# Initialize on startup
initialize_scanners()

@app.get("/")
async def root():
    return {
        "message": "ScanModule - Code Security Scanning Service is running!",
        "version": "1.0.0",
        "docs": "/docs"
    }

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "ScanModule"}

@app.get("/api/v1/scanners")
async def list_scanners():
    """
    Liệt kê các scanner có sẵn
    """
    try:
        scanners = scanner_registry.list_scanners()
        return {
            "scanners": scanners,
            "total": len(scanners)
        }
    except Exception as e:
        logger.error(f"Error listing scanners: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/scan/single")
async def scan_single_project(request: ScanRequest):
    """
    Quét một project đơn lẻ
    """
    try:
        project_path = Path(request.project_path)
        if not project_path.exists():
            raise HTTPException(status_code=404, detail=f"Project path not found: {request.project_path}")
        
        # Get scanner
        if request.scanner_type not in scanner_registry.list_scanners():
            raise HTTPException(status_code=400, detail=f"Scanner '{request.scanner_type}' not available")
        
        scanner = scanner_registry.get_scanner(request.scanner_type)
        
        # Perform scan
        start_time = datetime.now()
        scan_result = await asyncio.to_thread(
            scanner.scan_project,
            str(project_path),
            include_patterns=request.include_patterns,
            exclude_patterns=request.exclude_patterns
        )
        end_time = datetime.now()
        
        # Process results
        issues_count = len(scan_result.get("vulnerabilities", [])) + \
                      len(scan_result.get("bugs", [])) + \
                      len(scan_result.get("code_smells", []))
        
        result = ScanResult(
            project_name=project_path.name,
            project_path=str(project_path),
            scanner_type=request.scanner_type,
            scan_time=start_time,
            status="success",
            issues_count=issues_count,
            vulnerabilities=scan_result.get("vulnerabilities", []),
            code_smells=scan_result.get("code_smells", []),
            bugs=scan_result.get("bugs", []),
            security_hotspots=scan_result.get("security_hotspots", []),
            execution_time=(end_time - start_time).total_seconds()
        )
        
        return result.dict()
        
    except Exception as e:
        logger.error(f"Error scanning project {request.project_path}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/scan/batch")
async def batch_scan_projects(request: BatchScanRequest, background_tasks: BackgroundTasks):
    """
    Quét hàng loạt projects
    """
    try:
        # Validate scanner
        if request.scanner_type not in scanner_registry.list_scanners():
            raise HTTPException(status_code=400, detail=f"Scanner '{request.scanner_type}' not available")
        
        # Validate projects
        valid_projects = []
        for project in request.projects:
            project_path = Path(project["path"])
            if project_path.exists():
                valid_projects.append(project)
            else:
                logger.warning(f"Project path not found: {project['path']}")
        
        if not valid_projects:
            raise HTTPException(status_code=400, detail="No valid projects found")
        
        # Start batch scan
        scan_id = f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        if request.parallel:
            background_tasks.add_task(
                run_parallel_batch_scan,
                scan_id,
                valid_projects,
                request.scanner_type,
                request.max_workers
            )
        else:
            background_tasks.add_task(
                run_sequential_batch_scan,
                scan_id,
                valid_projects,
                request.scanner_type
            )
        
        return {
            "scan_id": scan_id,
            "status": "started",
            "projects_count": len(valid_projects),
            "scanner_type": request.scanner_type,
            "parallel": request.parallel
        }
        
    except Exception as e:
        logger.error(f"Error starting batch scan: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

async def run_parallel_batch_scan(scan_id: str, projects: List[Dict], scanner_type: str, max_workers: int):
    """
    Chạy batch scan song song
    """
    try:
        scanner = scanner_registry.get_scanner(scanner_type)
        
        # Use ThreadPoolExecutor for parallel scanning
        import concurrent.futures
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = []
            for project in projects:
                future = executor.submit(
                    scanner.scan_project,
                    project["path"]
                )
                futures.append((project, future))
            
            # Collect results
            results = []
            for project, future in futures:
                try:
                    scan_result = future.result(timeout=600)  # 10 minutes timeout
                    results.append({
                        "project": project,
                        "result": scan_result,
                        "status": "success"
                    })
                except Exception as e:
                    results.append({
                        "project": project,
                        "error": str(e),
                        "status": "failed"
                    })
        
        # Save results (implement your storage logic here)
        logger.info(f"Batch scan {scan_id} completed with {len(results)} results")
        
    except Exception as e:
        logger.error(f"Error in parallel batch scan {scan_id}: {str(e)}")

async def run_sequential_batch_scan(scan_id: str, projects: List[Dict], scanner_type: str):
    """
    Chạy batch scan tuần tự
    """
    try:
        scanner = scanner_registry.get_scanner(scanner_type)
        results = []
        
        for project in projects:
            try:
                scan_result = await asyncio.to_thread(
                    scanner.scan_project,
                    project["path"]
                )
                results.append({
                    "project": project,
                    "result": scan_result,
                    "status": "success"
                })
            except Exception as e:
                results.append({
                    "project": project,
                    "error": str(e),
                    "status": "failed"
                })
        
        # Save results (implement your storage logic here)
        logger.info(f"Sequential batch scan {scan_id} completed with {len(results)} results")
        
    except Exception as e:
        logger.error(f"Error in sequential batch scan {scan_id}: {str(e)}")

@app.get("/api/v1/scan/status/{scan_id}")
async def get_scan_status(scan_id: str):
    """
    Lấy trạng thái của batch scan
    """
    # Implement scan status tracking logic here
    return {
        "scan_id": scan_id,
        "status": "running",  # running, completed, failed
        "progress": "50%",
        "message": "Scan in progress..."
    }

if __name__ == "__main__":
    port = int(os.getenv("SCAN_PORT", 8003))
    logger.info(f"Starting ScanModule on port {port}")
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=True,
        log_level="info"
    )