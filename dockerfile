# --- Stage 1: Build React ---
FROM node:20-slim AS builder
WORKDIR /backend
COPY frontend/package*.json ./frontend/
RUN cd frontend && npm install
COPY frontend/ ./frontend/
RUN cd frontend && npm run build

# --- Stage 2: Run FastAPI ---
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim
WORKDIR /backend

# Copy python files
COPY . .
# Copy the BUILT frontend from the builder stage
COPY --from=builder /app/frontend/dist ./frontend/dist

# Install dependencies
RUN uv sync --frozen

# Start the server
CMD ["uv", "run", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]