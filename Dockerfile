# Dev-style single container running FastAPI dev + React dev server
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

# Install Node.js and npm
RUN apt-get update \
    && apt-get install -y --no-install-recommends nodejs npm \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
# We keep these build steps to cache dependencies in the image layers
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen

# Frontend dependencies
# We run install here to cache node_modules in the image...
COPY frontend/package*.json ./frontend/
RUN cd frontend && npm install

# Copy App source
COPY . .

EXPOSE 8000 3000

# Build the frontend
RUN cd frontend && npm run build

# Only run FastAPI (It will serve the frontend files)
CMD ["sh", "-c", "uv run fastapi run backend/app.py --host 0.0.0.0 --port ${PORT:-8000}"]