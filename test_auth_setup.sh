#!/bin/bash
# Quick test script to verify Auth0 setup

echo "=== Frontend Auth0 Configuration ==="
cd frontend
if [ -f .env ]; then
    echo "✓ .env file exists"
    if grep -q "VITE_AUTH0_DOMAIN" .env && ! grep -q "your-tenant" .env; then
        echo "✓ VITE_AUTH0_DOMAIN is configured"
    else
        echo "⚠ VITE_AUTH0_DOMAIN needs to be set"
    fi
    if grep -q "VITE_AUTH0_CLIENT_ID" .env && ! grep -q "your-client-id" .env; then
        echo "✓ VITE_AUTH0_CLIENT_ID is configured"
    else
        echo "⚠ VITE_AUTH0_CLIENT_ID needs to be set"
    fi
    if grep -q "VITE_AUTH0_AUDIENCE" .env && ! grep -q "my-revision-helper-api" .env; then
        echo "✓ VITE_AUTH0_AUDIENCE is configured"
    else
        echo "⚠ VITE_AUTH0_AUDIENCE needs to be set"
    fi
else
    echo "✗ .env file not found"
fi

echo ""
echo "=== Backend Auth0 Configuration ==="
cd ..
if [ -f .env ]; then
    echo "✓ .env file exists"
    if grep -q "AUTH0_DOMAIN" .env && ! grep -q "your-tenant" .env; then
        echo "✓ AUTH0_DOMAIN is configured"
    else
        echo "⚠ AUTH0_DOMAIN needs to be set"
    fi
    if grep -q "AUTH0_AUDIENCE" .env && ! grep -q "my-revision-helper-api" .env; then
        echo "✓ AUTH0_AUDIENCE is configured"
    else
        echo "⚠ AUTH0_AUDIENCE needs to be set"
    fi
else
    echo "ℹ No .env file in root (using environment variables or defaults)"
fi

echo ""
echo "=== Next Steps ==="
echo "1. Restart frontend server: cd frontend && npm run dev"
echo "2. Open http://localhost:5173"
echo "3. You should see a yellow 'Sign In' banner at the top"
echo "4. Click 'Sign In' to test authentication"

