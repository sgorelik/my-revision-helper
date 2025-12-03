#!/bin/bash
# Build script for Railway deployment
set -e

echo "📦 Installing frontend dependencies..."
cd frontend
npm install

echo "🏗️  Building frontend..."
npm run build

echo "📦 Installing Python dependencies..."
cd ..
pip install -r requirements.txt

echo "✅ Build complete!"

