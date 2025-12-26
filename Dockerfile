# Production Dockerfile for RadioThermostat CT50 Server (Stage 2)
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    net-tools \
    iputils-ping \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY src/ ./src/
COPY config/ ./config/

# Create logs directory
RUN mkdir -p logs

# Create non-root user
RUN useradd -m -u 1000 thermostat && chown -R thermostat:thermostat /app
USER thermostat

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/api/system/health || exit 1

# Expose API port
EXPOSE 8000

# Set environment
ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1

# Run the server
CMD ["python", "src/main.py"]
