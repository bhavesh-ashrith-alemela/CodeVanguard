# Use official Python runtime as a parent image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PORT=8000

# Set work directory
WORKDIR /app

# Install system dependencies
# git is useful for Semgrep, and weasyprint needs cairo, pango, gdk-pixbuf
RUN apt-get update && apt-get install -y --no-install-recommends build-essential git libcairo2 libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf-2.0-0 shared-mime-info && apt-get clean && rm -rf /var/lib/apt/lists/*

# Copy requirements and install python dependencies
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Create a non-root system user and adjust directory permissions
RUN useradd -u 10001 -U -d /app -s /bin/bash vanguard && \
    chown -R vanguard:vanguard /app

# Copy project files
COPY --chown=vanguard:vanguard . /app/

# Switch to non-root user
USER vanguard

# Expose port
EXPOSE 8000

# Run FastAPI app
CMD uvicorn app.main:app --host 0.0.0.0 --port $PORT
