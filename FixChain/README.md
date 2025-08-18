# FixChain2

A bug management and RAG (Retrieval-Augmented Generation) system with MongoDB and Gemini AI integration.

## Project Structure

```
FixChain2/
├── controller/          # API controllers
│   ├── __init__.py
│   ├── bug_controller.py    # Bug import and management API
│   └── rag_controller.py    # RAG MongoDB API
├── service/             # Business logic services
│   ├── __init__.py
│   └── mongodb_service.py   # MongoDB connection and operations
├── lib/                 # Utilities and sample data
│   ├── __init__.py
│   ├── example_requests.py  # Example API requests
│   ├── sample_payloads.json # Sample JSON payloads
│   └── sample_bugs.csv     # Sample bug data for import
├── main.py             # Main entry point
└── requirements.txt    # Python dependencies
```

## Services

### Bug Import API (Port 8001)
- Import bugs from JSON or CSV
- Search bugs with filters
- AI-powered bug analysis
- Bug statistics

### RAG MongoDB API (Port 8000)
- Document storage and retrieval
- AI-powered question answering
- Vector embeddings with Gemini

### RAG Bug Management API (Port 8002)
- Import bugs as RAG documents with embeddings
- Search bugs using vector similarity
- AI-powered bug fix suggestions
- Fix bug status and track solutions
- Enhanced bug analysis with context

## Getting Started

### Option 1: Docker (Recommended)

1. Set up environment variables in `.env`:
   ```
   GEMINI_API_KEY=your_gemini_api_key
   MONGODB_URI=mongodb://mongodb:27017/rag_db
   SONARQ_PATH=./SonarQ
   ```

2. Start with Docker Compose:
   ```bash
   docker-compose up -d
   ```

3. Access services:
   - RAG API: http://localhost:8000/docs
   - MongoDB Express: http://localhost:8081

### Option 2: Local Development

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Set up environment variables in `.env`:
   ```
   GEMINI_API_KEY=your_gemini_api_key
   MONGODB_URI=your_mongodb_connection_string
   SONARQ_PATH=./SonarQ  # Path to SonarQube scripts
   ```

3. Start services individually:
   ```bash
   # Bug Import API
   python -m controller.bug_controller
   
   # RAG API
   python -m controller.rag_controller
   
   # RAG Bug Management API
   python -m controller.rag_bug_controller
   ```

4. Access API documentation:
   - Bug API: http://localhost:8001/docs
   - RAG API: http://localhost:8000/docs
   - RAG Bug API: http://localhost:8002/docs

## Testing

No automated tests are included at the moment.

## Sample Data

- `lib/sample_bugs.csv` - Sample bug data for CSV import
- `lib/sample_rag_bugs.json` - Sample bug data for RAG import
- `lib/sample_payloads.json` - Sample API request payloads
- `lib/example_requests.py` - Example API usage scripts