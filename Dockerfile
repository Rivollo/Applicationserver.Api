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

# Copy application code
COPY . .

# Expose port expected by Azure ($PORT environment variable is set by App Service)
ENV PORT=8080
EXPOSE ${PORT}

# If your app is main.py with `app = FastAPI()` use main:app
# Use Gunicorn with Uvicorn worker (good for production)
CMD ["gunicorn", "-w", "4", "-k", "uvicorn.workers.UvicornWorker", "-b", "0.0.0.0:8080", "main:app"]
