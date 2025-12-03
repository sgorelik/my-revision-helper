# Railway Deployment Guide

This guide will help you deploy My Revision Helper to Railway in about 10-15 minutes.

## Prerequisites

1. **GitHub account** with your code pushed to a repository
2. **Railway account** - Sign up at https://railway.app (free, uses GitHub OAuth)
3. **OpenAI API key** (for AI features)

## Step-by-Step Deployment

### Step 1: Prepare Your Repository

Make sure your code is pushed to GitHub:

```bash
git add .
git commit -m "Prepare for Railway deployment"
git push origin main
```

### Step 2: Sign Up for Railway

1. Go to https://railway.app
2. Click "Start a New Project"
3. Sign in with GitHub
4. Authorize Railway to access your repositories

### Step 3: Create a New Project

1. Click "New Project"
2. Select "Deploy from GitHub repo"
3. Choose your `my_revision_helper` repository
4. Railway will detect it's a Python project

### Step 4: Configure the Service

Railway should auto-detect your Python app, but verify:

1. **Build Settings:**
   - Build Command: `pip install -r requirements.txt` (auto-detected)
   - Start Command: `uvicorn my_revision_helper.api:app --host 0.0.0.0 --port $PORT` (auto-detected from Procfile)

2. **Environment Variables:**
   Click "Variables" tab and add:
   ```
   OPENAI_API_KEY=sk-your-key-here
   OPENAI_MODEL=gpt-4o-mini
   AI_CONTEXT=You are a helpful and encouraging tutor...
   ```
   
   Optional:
   ```
   ALLOWED_ORIGINS=https://your-app.railway.app
   TEMPORAL_TARGET=localhost:7233
   TEMPORAL_TASK_QUEUE=revision-helper-queue
   ```

### Step 5: Build and Deploy Frontend

**Option A: Serve Frontend from Backend (Recommended for simplicity)**

1. In your local terminal:
   ```bash
   cd frontend
   npm install
   npm run build
   ```
   This creates `frontend/dist/` folder

2. The backend is already configured to serve static files from `frontend/dist/`
   - Make sure `frontend/dist/` is committed to git
   - Or add a build step in Railway

3. **Add build step in Railway:**
   - Go to your service settings
   - Add a build command that builds the frontend:
   ```bash
   cd frontend && npm install && npm run build && cd ..
   ```
   - Then your Python build runs

**Option B: Deploy Frontend Separately (More complex but better performance)**

1. Create a second service in Railway for the frontend
2. Configure it as a static site
3. Point it to `frontend/dist/`
4. Update CORS in backend to allow frontend domain

### Step 6: Generate Public Domain

1. In Railway dashboard, click on your service
2. Go to "Settings" → "Networking"
3. Click "Generate Domain"
4. Railway will give you a URL like: `https://my-revision-helper-production.up.railway.app`

### Step 7: Update Frontend API URL (if using separate frontend)

If you deployed frontend separately:

1. In frontend service, add environment variable:
   ```
   VITE_API_BASE=https://your-backend-url.railway.app/api
   ```

2. Rebuild frontend

### Step 8: Test Your Deployment

1. Visit your Railway domain
2. Try creating a revision
3. Test the question/answer flow
4. Check logs in Railway dashboard if issues

## Troubleshooting

### Build Fails

- Check Railway logs for error messages
- Ensure `requirements.txt` has all dependencies
- Verify Python version in `runtime.txt`

### Frontend Not Loading

- Check if `frontend/dist/` exists and is committed
- Verify static file serving in `api.py`
- Check Railway logs for errors

### CORS Errors

- Add your Railway domain to `ALLOWED_ORIGINS` environment variable
- Or set `ALLOWED_ORIGINS=*` for development (not recommended for production)

### API Not Working

- Check environment variables are set correctly
- Verify `OPENAI_API_KEY` is set if using AI features
- Check Railway logs for errors

### Database (Future)

When you're ready to add PostgreSQL:

1. In Railway dashboard, click "New"
2. Select "Database" → "PostgreSQL"
3. Railway automatically provides connection via `DATABASE_URL`
4. Update your code to use the database instead of in-memory storage

## Environment Variables Reference

| Variable | Required | Description | Default |
|----------|----------|-------------|---------|
| `OPENAI_API_KEY` | Yes (for AI) | Your OpenAI API key | - |
| `OPENAI_MODEL` | No | Model to use | `gpt-4o-mini` |
| `AI_CONTEXT` | No | General AI instructions | Default tutor context |
| `ALLOWED_ORIGINS` | No | Comma-separated CORS origins | `localhost:5173,localhost:3000` |
| `TEMPORAL_TARGET` | No | Temporal server address | `localhost:7233` |
| `TEMPORAL_TASK_QUEUE` | No | Temporal task queue | `revision-helper-queue` |
| `PORT` | Auto | Railway sets this | - |
| `RAILWAY_PUBLIC_DOMAIN` | Auto | Railway sets this | - |

## Cost

**Free Tier:**
- $5 credit per month
- Enough for small apps with low traffic
- Perfect for kids/friends usage

**If you exceed free tier:**
- ~$5-10/month for small-medium usage
- Railway charges per usage (CPU, RAM, bandwidth)

## Next Steps

1. **Add PostgreSQL** when you need persistent storage
2. **Set up custom domain** (optional, requires domain purchase)
3. **Add monitoring** (Railway has built-in logs)
4. **Set up CI/CD** (automatic deployments on git push)

## Updating Your App

Railway automatically deploys when you push to your connected branch:

```bash
git add .
git commit -m "Your changes"
git push origin main
```

Railway will detect the push and redeploy automatically!

## Support

- Railway Docs: https://docs.railway.app
- Railway Discord: https://discord.gg/railway
- Check Railway logs in dashboard for debugging

