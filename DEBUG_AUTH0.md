# Debug: Auth0 Login Button Not Showing

## Quick Checks

### 1. Verify Variables Are Set in Railway

Go to Railway dashboard → Your service → **Variables** tab and verify these exist:
- `VITE_AUTH0_DOMAIN`
- `VITE_AUTH0_CLIENT_ID`
- `VITE_AUTH0_AUDIENCE`
- `AUTH0_DOMAIN`
- `AUTH0_AUDIENCE`

### 2. Check Build Logs

After redeploying, check Railway build logs for:
```
Checking Vite environment variables...
VITE_AUTH0_DOMAIN: dev-18tuj8a0ii2bduui.us.auth0.com
VITE_AUTH0_CLIENT_ID: 9r7GxA3NX6wU8t7OBClbIchUFV6J7ess
VITE_AUTH0_AUDIENCE: https://dev-18tuj8a0ii2bduui.us.auth0.com/api/v2/
```

If you see "NOT SET", the variables aren't being passed to the build.

### 3. Check Browser Console

1. Open your Railway app
2. Open browser DevTools (F12)
3. Go to Console tab
4. Look for errors or check:
   ```javascript
   console.log(import.meta.env.VITE_AUTH0_DOMAIN)
   ```
   
   Should show your domain, not `undefined`.

### 4. Verify Built Files

The variables should be embedded in the built JavaScript. Check:
- Railway → Deployments → Latest → View build logs
- Look for the build output
- Variables should be in `frontend/dist/assets/*.js` files

## Common Issues

### Variables Not Set
**Fix:** Run `./set-railway-vars.sh` or set manually in Railway dashboard

### Variables Set But Not in Build
**Fix:** 
1. Ensure variables are set in the **same service** that runs the build
2. Redeploy after setting variables
3. Check build logs to verify variables are available

### Variables in Build But Not in Browser
**Fix:**
1. Clear browser cache
2. Hard refresh (Ctrl+Shift+R or Cmd+Shift+R)
3. Check browser console for errors

## Quick Fix Commands

```bash
# Set variables
./set-railway-vars.sh

# Or manually verify they're set
railway variables

# Trigger rebuild
git commit --allow-empty -m "Trigger rebuild"
git push
```

