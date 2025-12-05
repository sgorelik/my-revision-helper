#!/bin/bash
# Quick script to set Railway variables from .env.railway

while IFS='=' read -r key value; do
  # Skip comments and empty lines
  [[ $key =~ ^#.*$ ]] && continue
  [[ -z "$key" ]] && continue
  
  # Remove quotes and trim whitespace
  value=$(echo "$value" | sed "s/^[\"']\(.*\)[\"']$/\1/" | xargs)
  
  if [ -n "$key" ] && [ -n "$value" ]; then
    echo "Setting $key..."
    railway variables --set "$key=$value"
  fi
done < .env.railway

echo "✅ All variables set!"
