# Setting Railway Environment Variables from Files

## Option 1: Railway CLI (Recommended)

Railway CLI can set variables from a file or directly.

### Install Railway CLI
```bash
npm i -g @railway/cli
railway login
```

### Set Variables from .env File

**For your app service:**
```bash
# Link to your Railway project
railway link

# Set variables from a .env file
railway variables --file .env

# Or set specific variables
railway variables set VITE_AUTH0_DOMAIN=your-domain
railway variables set VITE_AUTH0_CLIENT_ID=your-client-id
railway variables set VITE_AUTH0_AUDIENCE=your-audience
railway variables set AUTH0_DOMAIN=your-domain
railway variables set AUTH0_AUDIENCE=your-audience
```

### Create a Railway-Specific .env File

Create `.env.railway` (don't commit this to git):
```env
# Frontend (build-time)
VITE_AUTH0_DOMAIN=your-tenant.auth0.com
VITE_AUTH0_CLIENT_ID=your-client-id
VITE_AUTH0_AUDIENCE=https://my-revision-helper-api

# Backend (runtime)
AUTH0_DOMAIN=your-tenant.auth0.com
AUTH0_AUDIENCE=https://my-revision-helper-api

# Already set by Railway automatically:
# DATABASE_URL (from PostgreSQL service)
# PORT (set by Railway)
# RAILWAY_PUBLIC_DOMAIN (set by Railway)
```

Then:
```bash
railway variables --file .env.railway
```

## Option 2: Railway Dashboard (Manual)

1. Go to Railway → Your service → Variables
2. Click "Raw Editor" or "Bulk Edit"
3. Paste your variables in format:
   ```
   VITE_AUTH0_DOMAIN=value
   VITE_AUTH0_CLIENT_ID=value
   ...
   ```

## Option 3: railway.json (Not Recommended for Secrets)

You can add variables to `railway.json`, but **don't commit secrets**:
```json
{
  "$schema": "https://railway.app/railway.schema.json",
  "build": {
    "builder": "NIXPACKS"
  },
  "deploy": {
    "variables": {
      "VITE_AUTH0_DOMAIN": "your-domain",
      "VITE_AUTH0_CLIENT_ID": "your-client-id"
    }
  }
}
```

**Warning:** This file is committed to git, so only use for non-secret values.

## Option 4: Script to Sync .env to Railway

Create a script `sync-railway-vars.sh`:
```bash
#!/bin/bash
# Sync environment variables to Railway

railway link

# Read .env.railway and set each variable
while IFS='=' read -r key value; do
  # Skip comments and empty lines
  [[ $key =~ ^#.*$ ]] && continue
  [[ -z "$key" ]] && continue
  
  # Remove quotes from value if present
  value=$(echo "$value" | sed 's/^"\(.*\)"$/\1/')
  
  echo "Setting $key..."
  railway variables set "$key=$value"
done < .env.railway

echo "✅ Variables synced to Railway"
```

Make it executable:
```bash
chmod +x sync-railway-vars.sh
```

## Recommended Approach

1. **Create `.env.railway`** (add to `.gitignore`)
2. **Use Railway CLI** to sync:
   ```bash
   railway variables --file .env.railway
   ```
3. **Redeploy** after setting variables

## Important Notes

- **Vite variables** (`VITE_*`) must be set **before** frontend build
- **DATABASE_URL** is automatically set by Railway when you add PostgreSQL
- **Never commit** `.env.railway` with real secrets to git
- Railway CLI is the easiest way to bulk-set variables

## Quick Setup

```bash
# 1. Install Railway CLI
npm i -g @railway/cli

# 2. Login
railway login

# 3. Link to your project
railway link

# 4. Set variables from file
railway variables --file .env.railway

# 5. Redeploy (or Railway will auto-deploy on next push)
```

