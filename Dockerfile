# Multi-stage build for Railway
# Stage 1: Build frontend
FROM node:18-alpine AS frontend-builder

WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ .
RUN npm run build

# Stage 2: Python runtime with frontend
FROM python:3.12-slim

WORKDIR /app

# Copy Python requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy frontend build from stage 1
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Copy application code
COPY my_revision_helper ./my_revision_helper

# Expose port (Railway sets PORT env var)
ENV PORT=8000
EXPOSE $PORT

# Start the server (use shell form to expand $PORT)
CMD sh -c "uvicorn my_revision_helper.api:app --host 0.0.0.0 --port ${PORT:-8000}"

