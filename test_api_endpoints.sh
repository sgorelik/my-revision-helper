#!/bin/bash
# Test script for API endpoints

BASE_URL="http://127.0.0.1:8000"

echo "=========================================="
echo "Testing API Endpoints"
echo "=========================================="
echo ""

echo "1. Health Check:"
curl -s "$BASE_URL/api/health" | python3 -m json.tool
echo ""
echo ""

echo "2. User Info (should show authenticated: false):"
curl -s "$BASE_URL/api/user/me" | python3 -m json.tool
echo ""
echo ""

echo "3. Subjects:"
curl -s "$BASE_URL/api/subjects" | python3 -m json.tool
echo ""
echo ""

echo "4. List Revisions (should be empty for anonymous user):"
curl -s "$BASE_URL/api/revisions" | python3 -m json.tool
echo ""
echo ""

echo "=========================================="
echo "All endpoint tests completed"
echo "=========================================="

