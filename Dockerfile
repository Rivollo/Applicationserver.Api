FROM python:3.11-slim

ENV UV_SYSTEM_PYTHON=1 \
	PYTHONUNBUFFERED=1 \
	PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
		curl \
		build-essential \
		gcc \
	&& curl -LsSf https://astral.sh/uv/install.sh | sh -s -- --install-dir /usr/local/bin \
	&& rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock ./

RUN uv sync --frozen --system \
	&& apt-get purge -y --auto-remove curl build-essential gcc \
	&& rm -rf ~/.cache/uv /var/lib/apt/lists/*

COPY . .

# Verify USD command-line tools are available after installation
RUN python -c "import pxr; print('USD Python bindings available')" || echo "USD Python bindings not available"
RUN which usdzip || echo "usdzip command not found - will use manual fallback"

ENV PORT=8080
EXPOSE ${PORT}

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "${PORT:-8080}"]
