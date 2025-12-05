# Auth0 Setup Guide

## Quick Setup Steps

### 1. Create Auth0 Account
1. Go to https://auth0.com and sign up (free tier available)
2. Complete the setup wizard

### 2. Create Application
1. In Auth0 Dashboard → **Applications** → **Create Application**
2. Name: `My Revision Helper` (or any name)
3. **Select "Single Page Application"** (NOT Regular Web Application)
4. Click **Create**

### 3. Configure Application Settings
In your application settings, add:

**Allowed Callback URLs:**
```
http://localhost:5173,http://localhost:3000,https://your-railway-domain.railway.app
```

**Allowed Logout URLs:**
```
http://localhost:5173,http://localhost:3000,https://your-railway-domain.railway.app
```

**Allowed Web Origins:**
```
http://localhost:5173,http://localhost:3000,https://your-railway-domain.railway.app
```

**Allowed Origins (CORS):**
```
http://localhost:5173,http://localhost:3000,https://your-railway-domain.railway.app
```

### 4. Create API
1. Dashboard → **Applications** → **APIs** → **Create API**
2. Name: `My Revision Helper API`
3. Identifier: `https://my-revision-helper-api` (or your preferred identifier)
4. Signing Algorithm: **RS256**
5. Click **Create**

### 5. Get Your Values
From Auth0 Dashboard:

- **Domain**: Settings → Domain (e.g., `dev-abc123.us.auth0.com`)
- **Client ID**: Applications → Your App → Settings → Client ID
- **Audience**: APIs → Your API → Settings → Identifier (e.g., `https://my-revision-helper-api`)

### 6. Create Frontend .env File
Create `frontend/.env`:

```env
VITE_AUTH0_DOMAIN=your-tenant.auth0.com
VITE_AUTH0_CLIENT_ID=your-client-id
VITE_AUTH0_AUDIENCE=https://my-revision-helper-api
```

### 7. Create Backend .env File (or Railway variables)
Add to your `.env` or Railway environment variables:

```env
AUTH0_DOMAIN=your-tenant.auth0.com
AUTH0_AUDIENCE=https://my-revision-helper-api
```

### 8. Restart Servers
```bash
# Stop and restart frontend
cd frontend
npm run dev

# Restart backend (if running)
# The backend will pick up new env vars automatically
```

## After Setup

Once configured:
- You'll see a yellow "Sign In" banner at the top for anonymous users
- Clicking "Sign In" will redirect to Auth0 login
- After login, you'll see a green banner with your name
- All your data will be saved and persist across sessions

## Testing Without Auth0

The app works perfectly without Auth0:
- No login banner appears
- All features work in anonymous/session-only mode
- Data is stored but not retrievable after session ends

