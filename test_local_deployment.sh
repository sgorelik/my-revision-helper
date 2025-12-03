#!/bin/bash
# Test script to verify local deployment setup

echo "🧪 Testing Local Deployment Setup"
echo ""

# Check if frontend is built
if [ ! -d "frontend/dist" ]; then
    echo "❌ Frontend not built. Building now..."
    cd frontend && npm run build && cd ..
fi

echo "✅ Frontend build exists"
echo ""

# Test Python imports
echo "Testing Python imports..."
python3 -c "from my_revision_helper.api import app; print('✅ API imports successfully')" || exit 1

# Test that static files exist
if [ ! -f "frontend/dist/index.html" ]; then
    echo "❌ frontend/dist/index.html not found"
    exit 1
fi
echo "✅ Frontend static files exist"
echo ""

# Test that API routes are defined
python3 << EOF
from my_revision_helper.api import app
routes = [r.path for r in app.routes]
api_routes = [r for r in routes if r.startswith('/api/')]
print(f"✅ Found {len(api_routes)} API routes")
EOF

echo ""
echo "✅ All local deployment checks passed!"
echo ""
echo "To test the full setup:"
echo "1. Start the server: uvicorn my_revision_helper.api:app --host 0.0.0.0 --port 8000"
echo "2. Visit: http://localhost:8000"
echo "3. The frontend should load and API calls should work"

