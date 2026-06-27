# Use an official lightweight Python Alpine image
FROM python:3.12-alpine

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8000

# Set working directory inside the container
WORKDIR /app

# Install runtime dependencies (netcat-openbsd for checking DB connection, curl for health check)
RUN apk add --no-cache \
    netcat-openbsd \
    curl

# Copy requirements file first to leverage Docker cache
COPY requirements.txt .

# Install build dependencies, compile python requirements, and clean up build tools
RUN apk add --no-cache --virtual .build-deps \
    build-base \
    python3-dev \
    musl-dev \
    libffi-dev \
    && pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt \
    && apk del .build-deps

# Copy application files, migrations configuration, and script
COPY app /app/app
COPY alembic /app/alembic
COPY alembic.ini /app/alembic.ini
COPY entrypoint.sh /app/entrypoint.sh

# Make entrypoint.sh executable
RUN chmod +x /app/entrypoint.sh

# Expose port
EXPOSE 8000

# Run entrypoint script
ENTRYPOINT ["/app/entrypoint.sh"]
