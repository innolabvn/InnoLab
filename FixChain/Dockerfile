# Dockerfile for RAG Backend API
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app/src \
    DOCKER_ENV=true

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl git tini \
 && rm -rf /var/lib/apt/lists/*

# Install uv + install Serena CLI
RUN curl -LsSf https://astral.sh/uv/install.sh | sh \
 && /root/.local/bin/uv tool install --force --from git+https://github.com/oraios/serena serena-agent

# Đưa ~/.local/bin vào PATH để gọi được CLI đã cài
ENV PATH="/root/.local/bin:${PATH}"

# (Tuỳ chọn) tạo alias 'serena' -> 'serena-agent' nếu binary là 'serena-agent'
RUN if [ -x "/root/.local/bin/serena" ]; then \
      ln -sf /root/.local/bin/serena /usr/local/bin/serena ; \
    elif [ -x "/root/.local/bin/serena-agent" ]; then \
      ln -sf /root/.local/bin/serena-agent /usr/local/bin/serena ; \
    fi
 
# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

RUN pip install --no-cache-dir "git+https://github.com/oraios/serena@main"

# Copy application code
COPY . .

ENTRYPOINT ["/usr/bin/tini", "--"]

EXPOSE 8000
# Start the FastAPI server
CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]