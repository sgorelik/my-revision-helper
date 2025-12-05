# Fix: Login Button Not Showing on Railway

## The Problem

The login button only appears if Auth0 environment variables are set. **Vite environment variables are build-time**, meaning they must be set **before** the frontend is built.

## Solution: Set Auth0 Variables and Rebuild

### Step 1: Get Your Auth0 Values

If you haven't set up Auth0 yet, follow `AUTH0_SETUP.md`. You need:
- **Domain**: e.g., `dev-abc123.us.auth0.com`
- **Client ID**: From your Auth0 application
- **Audience**: e.g., `https://my-revision-helper-api`

### Step 2: Set Environment Variables in Railway

1. Go to Railway dashboard → Your **application service** (not PostgreSQL)
2. Click **"Variables"** tab
3. Add these **three** variables:

```
VITE_AUTH0_DOMAIN=your-tenant.auth0.com
VITE_AUTH0_CLIENT_ID=your-client-id
VITE_AUTH0_AUDIENCE=https://my-revision-helper-api
```

**Also add backend variables:**
```
AUTH0_DOMAIN=your-tenant.auth0.com
AUTH0_AUDIENCE=https://my-revision-helper-api
```

### Step 3: Rebuild Frontend

Since Vite variables are build-time, you need to trigger a rebuild:

**Option A: Redeploy (Recommended)**
1. In Railway dashboard → Your service
2. Click **"Deployments"** tab
3. Click **"Redeploy"** on the latest deployment
4. This will rebuild the frontend with the new variables

**Option B: Push a commit**
```bash
git commit --allow-empty -m "Trigger rebuild for Auth0 variables"
git push
```

Railway will automatically rebuild and deploy.

### Step 4: Verify It Works

After redeploy:
1. Visit your Railway app
2. You should see a yellow banner at the top saying "Session-only mode"
3. There should be a "Sign In" button
4. Clicking it should redirect to Auth0 login

## Why This Happens

- **Vite variables** (`VITE_*`) are embedded into the JavaScript bundle at **build time**
- If they're not set during `npm run build`, they won't be in the final bundle
- Setting them after build won't help - you need to rebuild

## Quick Checklist

- [ ] Auth0 application created
- [ ] Auth0 API created
- [ ] Auth0 URLs updated with Railway domain
- [ ] `VITE_AUTH0_DOMAIN` set in Railway
- [ ] `VITE_AUTH0_CLIENT_ID` set in Railway
- [ ] `VITE_AUTH0_AUDIENCE` set in Railway
- [ ] `AUTH0_DOMAIN` set in Railway (backend)
- [ ] `AUTH0_AUDIENCE` set in Railway (backend)
- [ ] App redeployed after setting variables
- [ ] Login button appears on Railway app

## Troubleshooting

**Still no login button?**
1. Check browser console for errors
2. Verify variables are set: Railway → Variables tab
3. Check build logs: Railway → Deployments → Latest → Build logs
4. Look for `VITE_AUTH0_DOMAIN` in build logs (should be set)

**Login button appears but doesn't work?**
1. Check Auth0 dashboard → Application settings
2. Verify callback URLs include your Railway domain
3. Check browser console for Auth0 errors
4. Verify `AUTH0_DOMAIN` and `AUTH0_AUDIENCE` are set in Railway

