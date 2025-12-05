#!/bin/bash
# Script to set Railway environment variables from .env.railway file

set -e

echo "🚀 Setting up Railway environment variables..."

# Check if Railway CLI is installed
if ! command -v railway &> /dev/null; then
    echo "❌ Railway CLI not found. Installing..."
    npm install -g @railway/cli
    echo "✅ Railway CLI installed"
else
    echo "✅ Railway CLI found"
fi

# Check if logged in
if ! railway whoami &> /dev/null; then
    echo "🔐 Please log in to Railway..."
    railway login
else
    echo "✅ Already logged in to Railway"
    railway whoami
fi

# Check if project is linked
if [ ! -f .railway/project.json ]; then
    echo "🔗 Linking to Railway project..."
    railway link
else
    echo "✅ Project already linked"
fi

# Check if .env.railway exists
if [ ! -f .env.railway ]; then
    echo "❌ .env.railway file not found!"
    echo "Please create .env.railway with your Auth0 values"
    exit 1
fi

# Set variables from file
echo "📝 Setting variables from .env.railway..."

# Read .env.railway and set each variable
while IFS='=' read -r key value; do
  # Skip comments and empty lines
  [[ $key =~ ^#.*$ ]] && continue
  [[ -z "$key" ]] && continue
  
  # Remove quotes from value if present
  value=$(echo "$value" | sed "s/^[\"']\(.*\)[\"']$/\1/")
  
  if [ -n "$key" ] && [ -n "$value" ]; then
    echo "Setting $key..."
    railway variables --set "$key=$value"
  fi
done < .env.railway

echo ""
echo "✅ Variables set successfully!"
echo ""
echo "Next steps:"
echo "1. Verify variables in Railway dashboard"
echo "2. Redeploy your app to rebuild frontend with new variables"
echo "3. Check that login button appears after redeploy"

