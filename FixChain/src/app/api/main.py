from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.app.api.routers import bug_catalog, knowledge, fix_cases

app = FastAPI(
    title="FixChain - Bug Catalog, Knowledge Base & Fix Cases",
    version="2.0.0",
    description="Hệ thống quản lý bug + RAG Scanner/Fixer trên MongoDB & Gemini",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Prefix mới, tên dễ hiểu
app.include_router(bug_catalog, prefix="/api/v1/bug-catalog", tags=["Bug Catalog"])
app.include_router(knowledge,   prefix="/api/v1/knowledge",    tags=["Knowledge Base"])
app.include_router(fix_cases,   prefix="/api/v1/fix-cases",    tags=["Fix Cases"])

@app.get("/")
def root():
    return {
        "message": "Welcome to FixChain",
        "services": {
            "bug_catalog": "/api/v1/bug-catalog",
            "knowledge_base": "/api/v1/knowledge",
            "fix_cases": "/api/v1/fix-cases",
        },
        "docs": "/docs",
        "health": "/health",
    }

@app.get("/health")
def health():
    return {"status": "healthy"}
