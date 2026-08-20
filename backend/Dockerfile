# Use an official Python slim runtime
FROM python:3.11-slim

# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy only requirements first to leverage Docker layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire backend source code
COPY . .

# Make entrypoint script executable
RUN chmod +x /app/entrypoint.sh

# Expose port (default 8000, Render sets $PORT dynamically)
EXPOSE 8000

# Run both Celery and FastAPI in the single free container
ENTRYPOINT ["/app/entrypoint.sh"]
