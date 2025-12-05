# Quick Fix: Variables Set But Login Button Not Showing

## The Problem

Variables are set in Railway, but the login button still doesn't appear. This means the variables **weren't available during the build**.

## Solution: Force a Rebuild

Vite variables are embedded at **build time**. Even if variables are set now, if the frontend was built before they were set, they won't be in the bundle.

### Step 1: Verify Variables Are Set

Railway dashboard → Your service → Variables tab:
- ✅ `VITE_AUTH0_DOMAIN` = `dev-18tuj8a0ii2bduui.us.auth0.com`
- ✅ `VITE_AUTH0_CLIENT_ID` = `9r7GxA3NX6wU8t7OBClbIchUFV6J7ess`
- ✅ `VITE_AUTH0_AUDIENCE` = `https://dev-18tuj8a0ii2bduui.us.auth0.com/api/v2/`

### Step 2: Trigger a Fresh Build

**Option A: Empty Commit (Easiest)**
```bash
git commit --allow-empty -m "Trigger rebuild with Auth0 variables"
git push
```

**Option B: Railway Dashboard**
1. Railway dashboard → Your service
2. Deployments tab
3. Click "Redeploy" on latest deployment

### Step 3: Check Build Logs

After rebuild, check Railway build logs for:
```
Checking Vite environment variables...
VITE_AUTH0_DOMAIN: dev-18tuj8a0ii2bduui.us.auth0.com
VITE_AUTH0_CLIENT_ID: 9r7GxA3NX6wU8t7OBClbIchUFV6J7ess
VITE_AUTH0_AUDIENCE: https://dev-18tuj8a0ii2bduui.us.auth0.com/api/v2/
```

If you see "NOT SET", Railway isn't passing variables to the build.

### Step 4: Verify in Browser

After rebuild:
1. Visit your Railway app
2. Open DevTools (F12) → Console
3. Run: `console.log(import.meta.env.VITE_AUTH0_DOMAIN)`
4. Should show: `dev-18tuj8a0ii2bduui.us.auth0.com` (not `undefined`)

## If Still Not Working

### Check Railway Build Configuration

Railway should automatically pass environment variables to the build. If not:

1. **Verify build command**: Railway should run `build.sh`
2. **Check service settings**: Variables should be in the **same service** that runs the build
3. **Try explicit export**: The updated `build.sh` now exports variables explicitly

### Alternative: Check Built Files

The variables should be embedded in the built JavaScript:
- Railway → Deployments → Latest → View build output
- Check `frontend/dist/assets/*.js` files
- Search for `VITE_AUTH0_DOMAIN` - should find your domain value

## Quick Test

Run this in your Railway app's browser console:
```javascript
// Should show your domain
console.log('Domain:', import.meta.env.VITE_AUTH0_DOMAIN)
console.log('Client ID:', import.meta.env.VITE_AUTH0_CLIENT_ID)
console.log('Audience:', import.meta.env.VITE_AUTH0_AUDIENCE)

// Should show true if Auth0 is configured
console.log('Auth0 configured:', !!import.meta.env.VITE_AUTH0_DOMAIN)
```

If all show `undefined`, the variables weren't in the build.

