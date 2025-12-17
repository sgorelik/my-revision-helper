#!/bin/bash
# Setup script to install git hooks

echo "🔧 Setting up git hooks..."

# Create pre-push hook
cat > .git/hooks/pre-push << 'HOOK_EOF'
#!/bin/bash
# Pre-push hook to run frontend build and tests before pushing

set -e  # Exit on any error

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$PROJECT_ROOT"

echo "🔨 Running pre-push checks..."
echo ""

# Step 1: Frontend build
echo "📦 Step 1/3: Building frontend..."
cd frontend || exit 1

# Check if node_modules exists, if not, suggest installing
if [ ! -d "node_modules" ]; then
    echo "⚠️  node_modules not found. Running npm install..."
    npm install || exit 1
fi

# Run the build
npm run build

if [ $? -ne 0 ]; then
    echo "❌ Frontend build failed! Push aborted."
    echo "💡 Fix the build errors and try again."
    exit 1
fi

echo "✅ Frontend build successful!"
echo ""

# Step 2: Unit tests
cd "$PROJECT_ROOT"
echo "🧪 Step 2/3: Running unit tests..."
python -m pytest -m unit -v

if [ $? -ne 0 ]; then
    echo "❌ Unit tests failed! Push aborted."
    echo "💡 Fix the failing tests and try again."
    exit 1
fi

echo "✅ All unit tests passed!"
echo ""

# Step 3: Fast integration tests
echo "🔗 Step 3/3: Running fast integration tests..."
python -m pytest -m "integration and not slow" -v

if [ $? -ne 0 ]; then
    echo "❌ Integration tests failed! Push aborted."
    echo "💡 Fix the failing tests and try again."
    exit 1
fi

echo "✅ All fast integration tests passed!"
echo ""
echo "🎉 All pre-push checks passed! Proceeding with push..."
exit 0
HOOK_EOF

# Make it executable
chmod +x .git/hooks/pre-push

echo "✅ Pre-push hook installed successfully!"
echo ""
echo "The hook will now run the following checks before every push:"
echo "  1. Frontend build (npm run build)"
echo "  2. All unit tests (pytest -m unit)"
echo "  3. Fast integration tests (pytest -m 'integration and not slow')"
echo ""
echo "If any check fails, the push will be aborted."

