# Railway Docker Build Arguments Fix

## The Problem

Railway uses Dockerfile for builds, but Docker build-time variables (like Vite's `VITE_*` variables) need to be passed as **build arguments** (`ARG`), not just environment variables.

Railway automatically passes environment variables as build arguments if they're prefixed correctly, but we need to ensure they're available during the Docker build.

## Solution

The Dockerfile has been updated to accept `ARG` for Vite variables. Railway should automatically pass environment variables as build arguments, but we need to verify the configuration.

## Steps to Fix

### Option 1: Railway Automatic (Should Work)

Railway should automatically pass environment variables as Docker build arguments. After setting variables:

1. **Set variables in Railway** (already done):
   - `VITE_AUTH0_DOMAIN`
   - `VITE_AUTH0_CLIENT_ID`
   - `VITE_AUTH0_AUDIENCE`

2. **Redeploy** - Railway should pass them automatically

3. **Check build logs** for:
   ```
   Building frontend with Vite variables:
   VITE_AUTH0_DOMAIN: dev-18tuj8a0ii2bduui.us.auth0.com
   VITE_AUTH0_CLIENT_ID: 9r7GxA3NX6wU8t7OBClbIchUFV6J7ess
   ```

### Option 2: Manual Build Args (If Option 1 Doesn't Work)

If Railway doesn't automatically pass them, you may need to configure build arguments in Railway dashboard:

1. Railway dashboard → Your service → Settings
2. Look for "Build Arguments" or "Docker Build Args"
3. Add:
   ```
   VITE_AUTH0_DOMAIN=dev-18tuj8a0ii2bduui.us.authway.app
   VITE_AUTH0_CLIENT_ID=9r7GxA3NX6wU8t7OBClbIchUFV6J7ess
   VITE_AUTH0_AUDIENCE=https://dev-18tuj8a0ii2bduui.us.auth0.com/api/v2/
   ```

### Option 3: Use railway.json (Alternative)

Railway might support build arguments in `railway.json`, but this would require committing secrets (not recommended).

## Current Dockerfile Configuration

The Dockerfile now:
1. Accepts `ARG` for Vite variables
2. Logs them during build (for debugging)
3. Sets them as `ENV` for the build process

## Verification

After redeploy, check:
1. **Build logs**: Should show Vite variables (not "NOT SET")
2. **Browser console**: Should show "Auth0 Domain configured: true" (not false)
3. **Login button**: Should appear if variables are set

## If Still Not Working

Railway might not automatically pass environment variables as Docker build arguments. In that case:
1. Check Railway documentation for Docker build args
2. Consider switching to Nixpacks builder (which handles env vars differently)
3. Or use a build script approach instead of Dockerfile

