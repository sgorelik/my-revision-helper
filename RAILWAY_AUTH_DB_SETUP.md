# Railway.app: Auth0 + Database Persistence Setup

This guide will help you enable authentication and database persistence on your Railway deployment.

## Prerequisites

1. Railway app already deployed and running
2. Your Railway app URL (e.g., `https://your-app.up.railway.app`)
3. Auth0 account (free tier available at https://auth0.com)

---

## Part 1: Set Up PostgreSQL Database on Railway

### Step 1: Add PostgreSQL Service
1. Go to your Railway project dashboard
2. Click **"+ New"** → **"Database"** → **"Add PostgreSQL"**
3. Railway will automatically:
   - Create a PostgreSQL database
   - Set the `DATABASE_URL` environment variable
   - No additional configuration needed!

### Step 2: Verify Database Connection
1. Railway automatically sets `DATABASE_URL` - you don't need to do anything
2. The backend will automatically create tables on startup via `init_db()`
3. Check Railway logs to see if tables were created successfully

**That's it for database!** The persistence layer is already in the code and will activate automatically.

---

## Part 2: Set Up Auth0 Authentication

### Step 1: Create Auth0 Application

1. Go to https://manage.auth0.com
2. **Applications** → **Create Application**
3. Name: `My Revision Helper`
4. **Select "Single Page Application"** (NOT Regular Web Application)
5. Click **Create**

### Step 2: Configure Auth0 Application Settings

In your Auth0 application settings, update these URLs (replace with your Railway domain):

**Allowed Callback URLs:**
```
http://localhost:5173,http://localhost:3000,https://your-app.up.railway.app
```

**Allowed Logout URLs:**
```
http://localhost:5173,http://localhost:3000,https://your-app.up.railway.app
```

**Allowed Web Origins:**
```
http://localhost:5173,http://localhost:3000,https://your-app.up.railway.app
```

**Allowed Origins (CORS):**
```
http://localhost:5173,http://localhost:3000,https://your-app.up.railway.app
```

### Step 3: Create Auth0 API

1. In Auth0 Dashboard → **Applications** → **APIs** → **Create API**
2. Name: `My Revision Helper API`
3. Identifier: `https://my-revision-helper-api` (or your preferred identifier)
4. Signing Algorithm: **RS256**
5. Click **Create**

### Step 4: Get Auth0 Values

From Auth0 Dashboard, copy these values:

- **Domain**: Settings → Domain (e.g., `dev-abc123.us.auth0.com`)
- **Client ID**: Applications → Your App → Settings → Client ID
- **Audience**: APIs → Your API → Settings → Identifier (e.g., `https://my-revision-helper-api`)

### Step 5: Set Railway Environment Variables

In Railway dashboard → Your Project → **Variables** tab, add:

**Backend Variables:**
```
AUTH0_DOMAIN=your-tenant.auth0.com
AUTH0_AUDIENCE=https://my-revision-helper-api
```

**Frontend Variables (Build-time):**
Since Vite environment variables are build-time, you need to rebuild the frontend. Add these to Railway:

```
VITE_AUTH0_DOMAIN=your-tenant.auth0.com
VITE_AUTH0_CLIENT_ID=your-client-id
VITE_AUTH0_AUDIENCE=https://my-revision-helper-api
```

**Note:** Vite variables need to be available during the build process. Railway will need to rebuild the frontend after adding these.

### Step 6: Update Build Process (if needed)

If your Railway build doesn't include frontend build, ensure `build.sh` or your build process:
1. Installs frontend dependencies (`cd frontend && npm install`)
2. Builds the frontend (`npm run build`)
3. The built `frontend/dist/` is served by the backend

### Step 7: Redeploy

After setting environment variables:
1. Railway will automatically redeploy, OR
2. Go to Railway dashboard → **Deployments** → **Redeploy**

---

## Part 3: Verify Everything Works

### Test Database Persistence

1. Visit your Railway app: `https://your-app.up.railway.app`
2. Create a revision (as anonymous user)
3. Check Railway logs - you should see database connection messages
4. Data should be persisted (check via Railway PostgreSQL dashboard if needed)

### Test Authentication

1. Visit your Railway app
2. You should see a yellow "Sign In" banner at the top
3. Click "Sign In" → Should redirect to Auth0 login
4. After login → Should see green banner with your name
5. Create a revision → Should be saved with your user_id

### Check Railway Logs

Look for:
- ✅ `DATABASE_URL is set` - Database connected
- ✅ `Tables created successfully` - Database initialized
- ✅ `Auth0 domain configured` - Auth0 ready
- ✅ No authentication errors

---

## Troubleshooting

### Database Not Working

**Check:**
- Is PostgreSQL service added in Railway?
- Is `DATABASE_URL` set? (Railway sets this automatically)
- Check Railway logs for database connection errors
- Verify tables were created (check logs for "Tables created successfully")

**Fix:**
- Ensure PostgreSQL service is running in Railway
- Check Railway logs for connection errors
- Database should work automatically once PostgreSQL is added

### Auth0 Not Working

**Check:**
- Are all environment variables set in Railway?
- Did you update Auth0 callback URLs with your Railway domain?
- Are frontend variables set? (Vite needs them at build time)
- Check browser console for Auth0 errors

**Fix:**
- Verify all Auth0 URLs in dashboard include your Railway domain
- Ensure `VITE_AUTH0_*` variables are set before frontend build
- Rebuild frontend if variables were added after initial build
- Check Railway logs for backend Auth0 errors

### Frontend Not Showing Auth

**Check:**
- Are `VITE_AUTH0_*` variables set in Railway?
- Was frontend rebuilt after adding variables?
- Check browser console for Auth0 SDK errors

**Fix:**
- Vite variables must be set before build
- Trigger a new Railway deployment after adding `VITE_*` variables
- Verify variables are in Railway → Variables tab

---

## Environment Variables Summary

### Required for Database
```
DATABASE_URL  # Automatically set by Railway when you add PostgreSQL
```

### Required for Auth0 Backend
```
AUTH0_DOMAIN=your-tenant.auth0.com
AUTH0_AUDIENCE=https://my-revision-helper-api
```

### Required for Auth0 Frontend (Build-time)
```
VITE_AUTH0_DOMAIN=your-tenant.auth0.com
VITE_AUTH0_CLIENT_ID=your-client-id
VITE_AUTH0_AUDIENCE=https://my-revision-helper-api
```

### Already Set (if app is working)
```
OPENAI_API_KEY=sk-...
PORT  # Set by Railway
```

---

## Quick Checklist

- [ ] PostgreSQL service added to Railway
- [ ] `DATABASE_URL` is set (automatic)
- [ ] Auth0 application created (Single Page Application)
- [ ] Auth0 API created
- [ ] Auth0 URLs updated with Railway domain
- [ ] Backend Auth0 variables set in Railway (`AUTH0_DOMAIN`, `AUTH0_AUDIENCE`)
- [ ] Frontend Auth0 variables set in Railway (`VITE_AUTH0_*`)
- [ ] Railway redeployed after adding variables
- [ ] Tested database persistence (create revision)
- [ ] Tested authentication (sign in, create revision)

---

## Next Steps

Once both are working:
1. ✅ Users can sign in with Auth0
2. ✅ Data persists across sessions for authenticated users
3. ✅ Anonymous users can still use the app (session-only)
4. ✅ All data is stored in PostgreSQL database

