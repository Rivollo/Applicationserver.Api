# Use an official Python runtime
FROM python:3.11-slim

# Set working dir
WORKDIR /app

# Install build deps, copy requirements, install packages
COPY requirements.txt .
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc \
  && pip install --no-cache-dir -r requirements.txt \
  && apt-get purge -y --auto-remove build-essential gcc \
  && rm -rf /var/lib/apt/lists/*

# Verify USD command-line tools are available after installation
RUN python -c "import pxr; print('USD Python bindings available')" || echo "USD Python bindings not available"
RUN which usdzip || echo "usdzip command not found - will use manual fallback"

# Copy application code
COPY . .

# Expose port expected by Azure ($PORT environment variable is set by App Service)
ENV PORT=8080
EXPOSE ${PORT}

# If your app is main.py with `app = FastAPI()` use main:app
# Use Gunicorn with Uvicorn worker (good for production)
# Use shell form so $PORT (set by Azure) is respected, defaulting to 8080 locally
CMD ["sh", "-c", "gunicorn -w 4 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:${PORT:-8080} app.main:app"]
