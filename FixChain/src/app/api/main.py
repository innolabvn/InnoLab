from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.app.api.routers import knowledge, fixer_rag, scanner_rag

app = FastAPI(title="FixChain API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Prefix mới, tên dễ hiểu
app.include_router(knowledge,   prefix="/api/v1/knowledge",    tags=["Knowledge Base"])
app.include_router(fixer_rag,   prefix="/api/v1/fixer-rag",    tags=["Fixer RAG"])
app.include_router(scanner_rag,  prefix="/api/v1/scanner-rag",  tags=["Scanner RAG"])

@app.get("/")
def root():
    return {
        "message": "Welcome to FixChain",
        "services": {
            "Knowledge Base": "/api/v1/knowledge",
            "Fixer RAG": "/api/v1/fixer-rag",
            "Scanner RAG": "/api/v1/scanner-rag",
        },
        "docs": "/docs",
    }