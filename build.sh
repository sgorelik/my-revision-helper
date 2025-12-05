#!/bin/bash
# Build script for Railway deployment
set -e

echo "📦 Building frontend..."

# Debug: Check if Vite env vars are available
echo "Checking Vite environment variables..."
echo "VITE_AUTH0_DOMAIN: ${VITE_AUTH0_DOMAIN:-NOT SET}"
echo "VITE_AUTH0_CLIENT_ID: ${VITE_AUTH0_CLIENT_ID:-NOT SET}"
echo "VITE_AUTH0_AUDIENCE: ${VITE_AUTH0_AUDIENCE:-NOT SET}"

cd frontend
npm install

# Export Vite variables so they're available during build
export VITE_AUTH0_DOMAIN="${VITE_AUTH0_DOMAIN}"
export VITE_AUTH0_CLIENT_ID="${VITE_AUTH0_CLIENT_ID}"
export VITE_AUTH0_AUDIENCE="${VITE_AUTH0_AUDIENCE}"

npm run build
cd ..

echo "✅ Build complete!"

