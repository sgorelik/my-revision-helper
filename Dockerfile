# Multi-stage build for Railway
# Stage 1: Build frontend
FROM node:18-alpine AS frontend-builder

# Accept build arguments for Vite environment variables
# Railway will pass these as build args if set
ARG VITE_AUTH0_DOMAIN
ARG VITE_AUTH0_CLIENT_ID
ARG VITE_AUTH0_AUDIENCE

# Debug: Log what we received
RUN echo "Building frontend with Vite variables:" && \
    echo "VITE_AUTH0_DOMAIN: ${VITE_AUTH0_DOMAIN:-NOT SET}" && \
    echo "VITE_AUTH0_CLIENT_ID: ${VITE_AUTH0_CLIENT_ID:-NOT SET}" && \
    echo "VITE_AUTH0_AUDIENCE: ${VITE_AUTH0_AUDIENCE:-NOT SET}"

WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ .

# Set environment variables for Vite build
ENV VITE_AUTH0_DOMAIN=${VITE_AUTH0_DOMAIN}
ENV VITE_AUTH0_CLIENT_ID=${VITE_AUTH0_CLIENT_ID}
ENV VITE_AUTH0_AUDIENCE=${VITE_AUTH0_AUDIENCE}

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
EXPOSE 8000

# Start the server (use shell form to expand $PORT)
# Railway will set PORT as an environment variable at runtime
CMD ["sh", "-c", "uvicorn my_revision_helper.api:app --host 0.0.0.0 --port ${PORT:-8000}"]

