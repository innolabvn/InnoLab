#!/usr/bin/env python3
"""
Main entry point for FixChain2 application
Integrated FastAPI with all controllers using APIRouter
"""

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os
from dotenv import load_dotenv
from utils.logger import logger

# Load environment variables from root directory
root_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
load_dotenv(root_env_path)

# Import routers instead of apps
from controller import bug_controller, rag_controller, rag_bug_controller

# Create main FastAPI application
app = FastAPI(
    title="FixChain - Comprehensive Bug Management & RAG System",
    description="""
    Hệ thống quản lý bugs toàn diện với RAG (Retrieval-Augmented Generation) sử dụng MongoDB và Gemini AI.
    
    ## Tính năng chính:
    
    ### Bug Management
    - Import bugs từ JSON/CSV
    - Tìm kiếm và phân tích bugs
    - Thống kê và báo cáo
    
    ### RAG System
    - Vector search với MongoDB
    - AI-powered document retrieval
    - Embedding generation với Gemini
    
    ### RAG Bug Management
    - Import bugs với vector embedding
    - AI-powered bug search và similarity
    - Intelligent fix suggestions
    - Bug status management với AI insights
    
    ## Technology Stack:
    - **AI Model**: Google Gemini 2.0 Flash
    - **Database**: MongoDB với Vector Search
    - **Framework**: FastAPI + Python
    - **Embedding**: text-embedding-004
    """,
    version="2.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers with prefixes
app.include_router(bug_controller.app, prefix="/api/v1/bugs", tags=["Bug Management"])
app.include_router(rag_controller.app, prefix="/api/v1/rag", tags=["RAG System"])
app.include_router(rag_bug_controller.app, prefix="/api/v1/rag-bugs", tags=["RAG Bug Management"])

@app.get("/", tags=["Root"])
async def root():
    """Welcome endpoint với thông tin hệ thống"""
    return {
        "message": "Welcome to FixChain - Comprehensive Bug Management & RAG System",
        "version": "2.0.0",
        "services": {
            "bug_management": "/api/v1/bugs",
            "rag_system": "/api/v1/rag", 
            "rag_bug_management": "/api/v1/rag-bugs"
        },
        "documentation": "/docs",
        "openapi_schema": "/openapi.json",
        "health_check": "/health",
        "ai_model": "gemini-2.0-flash-exp",
        "database": "MongoDB with Vector Search"
    }

@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy"
    }

def main():
    """
    Main function to start the integrated application
    """
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)

if __name__ == "__main__":
    main()