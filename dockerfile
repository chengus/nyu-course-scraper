# Dev-style single container running FastAPI dev + React dev server
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

RUN apt-get update \
	&& apt-get install -y --no-install-recommends nodejs npm \
	&& rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen

# Frontend dependencies
COPY frontend/package*.json ./frontend/
RUN cd frontend && npm install

# App source
COPY . .

EXPOSE 8000 3000

CMD ["sh", "-c", "uv run fastapi run backend/app.py --host 0.0.0.0 --port 8000 & cd frontend && npm start"]