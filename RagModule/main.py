#!/usr/bin/env python3
"""
RagModule - RAG (Retrieval-Augmented Generation) Service
Tập trung vào các chức năng RAG từ FixChain
"""

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os
from dotenv import load_dotenv
from utils.logger import logger

# Load environment variables
load_dotenv()

# Import RAG controllers
from controller.rag_controller import router as rag_router
from controller.rag_bug_controller import router as rag_bug_router

# Create RAG FastAPI application
app = FastAPI(
    title="RagModule - RAG Service",
    description="""
    Hệ thống RAG (Retrieval-Augmented Generation) sử dụng MongoDB và Gemini AI.
    
    ## Tính năng chính:
    
    ### 🔍 RAG System (Core)
    - Vector search với MongoDB
    - AI-powered document retrieval
    - Embedding generation với Gemini
    
    ### 🚀 RAG Bug Management (Advanced)
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

# Include routers
app.include_router(rag_router, prefix="/api/v1/rag", tags=["RAG"])
app.include_router(rag_bug_router, prefix="/api/v1/rag-bugs", tags=["RAG Bugs"])

@app.get("/")
async def root():
    return {
        "message": "RagModule - RAG Service is running!",
        "version": "1.0.0",
        "docs": "/docs"
    }

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "RagModule"}

# All RAG functionality is handled by controllers

if __name__ == "__main__":
    port = int(os.getenv("RAG_PORT", 8003))
    logger.info(f"Starting RagModule on port {port}")
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=True,
        log_level="info"
    )