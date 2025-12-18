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

# Copy migration scripts
COPY migrate_*.py ./
COPY run_migrations.py ./
COPY ensure_migrations.py ./

# Expose port (Railway sets PORT env var)
ENV PORT=8000
EXPOSE 8000

# Create startup script that runs migrations then starts server
RUN echo '#!/bin/sh\n\
set -e\n\
echo "========================================"\n\
echo "🚀 Starting My Revision Helper"\n\
echo "========================================"\n\
if [ -n "$DATABASE_URL" ]; then\n\
  echo ""\n\
  echo "📊 Database detected - running migrations..."\n\
  echo ""\n\
  echo "Step 1: Ensuring critical columns exist (BLOCKING)..."\n\
  if ! python ensure_migrations.py; then\n\
    echo "❌ CRITICAL: Failed to ensure critical columns exist!"\n\
    echo "   Server will NOT start until this is fixed."\n\
    echo "   Check the error messages above."\n\
    exit 1\n\
  fi\n\
  echo "✅ Critical columns verified"\n\
  echo ""\n\
  echo "Step 2: Running full migration scripts..."\n\
  python run_migrations.py || {\n\
    MIGRATION_EXIT=$?\n\
    echo "⚠️  Full migrations failed with exit code $MIGRATION_EXIT"\n\
    echo "   Critical columns should still be in place from Step 1"\n\
    echo "   Continuing with server startup..."\n\
  }\n\
  echo ""\n\
  echo "Step 3: Final verification (BLOCKING)..."\n\
  if ! python ensure_migrations.py; then\n\
    echo "❌ CRITICAL: Final verification failed!"\n\
    echo "   Server will NOT start until this is fixed."\n\
    exit 1\n\
  fi\n\
  echo "✅ Final verification passed"\n\
else\n\
  echo "⚠️  DATABASE_URL not set - skipping migrations"\n\
fi\n\
echo ""\n\
echo "========================================"\n\
echo "🚀 Starting server..."\n\
echo "========================================"\n\
exec uvicorn my_revision_helper.api:app --host 0.0.0.0 --port ${PORT:-8000}\n\
' > /app/start.sh && chmod +x /app/start.sh

# Start the server (runs migrations first)
CMD ["/app/start.sh"]

