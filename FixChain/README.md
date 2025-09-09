.
├─ pyproject.toml / requirements.txt
├─ Dockerfile
├─ docker-compose.yml
├─ .env
├─ README.md
├─ src/
│  └─ app/
│     ├─ api/                           # FastAPI endpoints
│     │  ├─ main.py                     # entry FastAPI: app.api.main:app
│     │  └─ routers/
│     │     ├─ bug_catalog.py           # (was bug_controller.py)
│     │     ├─ knowledge.py             # (was rag_controller.py)
│     │     ├─ fix_cases.py             # (was rag_bug_controller.py)
│     │     └─ __init__.py
│     ├─ services/                      # business logic (framework-agnostic)
│     │  ├─ batch_fix/        
│     │  ├─ analysis_service.py         
│     │  ├─ cli_service.py              
│     │  ├─ logger.py                  # (was utils/logger.py, đã cải tiến)
│     │  ├─ rag_service.py              # client gọi API knowledge/fix-cases
│     │  └─ __init__.py
│     ├─ adapters/                      # kết nối ra ngoài (LLM/GenAI, reranker…)
│     │  ├─ llm/
│     │  │  ├─ google_genai.py          # client google-genai (thay utils/ai_client.py)
│     │  │  └─ __init__.py
│     │  │─ dify_client.py 
│     │  └─ __init__.py
│     ├─ repositories/                  # truy cập hạ tầng dữ liệu
│     │  └─ mongo.py                    # (was modules/mongodb_service.py)
│     ├─ domains/                       # (tuỳ chọn) chuyên biệt Scanner/Fixer
│     │  ├─ scan/
│     │  └─ fix/
│     ├─ prompt/                       
│     └─ __init__.py
├─ scripts/
│  └─ run_demo.py
├─ data/                    
│  └─ mocks/
└─ logs/              
