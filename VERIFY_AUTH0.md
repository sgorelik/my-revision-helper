# How to Find Your Correct Auth0 Domain

## Method 1: From Auth0 Dashboard URL
1. Log into https://manage.auth0.com
2. Look at the URL in your browser - it will be something like:
   - `https://manage.auth0.com/dashboard/us/[your-tenant-name]/`
3. Your domain is: `[your-tenant-name].us.auth0.com`

## Method 2: From Settings
1. In Auth0 Dashboard → **Settings** (left sidebar)
2. Scroll to **Domain** section
3. Copy the domain shown (e.g., `dev-xxxxx.us.auth0.com`)

## Method 3: Check Your Application
1. Go to **Applications** → Your Application
2. The domain might be shown in the application details

## Common Domain Formats
- **US Region**: `dev-xxxxx.us.auth0.com` or `xxxxx.us.auth0.com`
- **Default**: `xxxxx.auth0.com`
- **EU Region**: `xxxxx.eu.auth0.com`
- **Australia**: `xxxxx.au.auth0.com`

## After Finding Your Domain

Update `frontend/.env`:
```env
VITE_AUTH0_DOMAIN=your-actual-domain.auth0.com
```

Then restart the frontend server.

## Test Your Domain

You can test if your domain is correct by visiting:
```
https://[your-domain]/.well-known/openid-configuration
```

It should return JSON, not a 404 error.

