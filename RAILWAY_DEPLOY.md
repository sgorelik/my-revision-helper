# Railway Deployment Guide

Quick guide to deploy My Revision Helper to Railway.app

## Prerequisites

1. Railway account (sign up at https://railway.app)
2. GitHub repository connected (or Railway CLI installed)

## Deployment Steps

### Option 1: Deploy via Railway Dashboard (Recommended)

1. **Create New Project**
   - Go to https://railway.app/new
   - Click "Deploy from GitHub repo"
   - Select your `my-revision-helper` repository

2. **Configure Environment Variables**
   - In your Railway project, go to "Variables" tab
   - Add the following required variables:
     ```
     OPENAI_API_KEY=sk-your-key-here
     ```
   - Optional variables:
     ```
     OPENAI_MODEL=gpt-4o-mini
     AI_CONTEXT=You are a helpful and encouraging tutor...
     ALLOWED_ORIGINS=*
     ```

3. **Deploy**
   - Railway will automatically detect the project
   - It will run the build script (`build.sh`)
   - The app will start automatically

4. **Get Your URL**
   - Railway will provide a public URL like: `https://your-app.railway.app`
   - The app will be available at this URL

### Option 2: Deploy via Railway CLI

1. **Install Railway CLI**
   ```bash
   npm i -g @railway/cli
   ```

2. **Login**
   ```bash
   railway login
   ```

3. **Initialize Project**
   ```bash
   railway init
   ```

4. **Set Environment Variables**
   ```bash
   railway variables set OPENAI_API_KEY=sk-your-key-here
   railway variables set OPENAI_MODEL=gpt-4o-mini
   ```

5. **Deploy**
   ```bash
   railway up
   ```

## Build Process

Railway will:
1. Detect Python and Node.js (via Nixpacks)
2. Run `build.sh` which:
   - Installs frontend dependencies (`npm install`)
   - Builds the frontend (`npm run build`)
   - Installs Python dependencies (`pip install -r requirements.txt`)
3. Start the server using the `Procfile` command

## Configuration Files

- **`Procfile`**: Defines the start command
- **`railway.json`**: Railway-specific configuration
- **`build.sh`**: Build script for frontend + backend
- **`runtime.txt`**: Python version (3.12)
- **`.railwayignore`**: Files to exclude from deployment

## Troubleshooting

### Build Fails

- Check Railway logs for errors
- Ensure `frontend/package.json` exists
- Verify `requirements.txt` is correct
- Check that Node.js and Python are detected

### App Doesn't Start

- Check that `PORT` environment variable is set (Railway sets this automatically)
- Verify the start command in `Procfile`
- Check logs for Python errors

### Frontend Not Loading

- Ensure `frontend/dist` directory exists after build
- Check that static file serving is configured in `api.py`
- Verify the build completed successfully

### CORS Errors

- Add your Railway domain to `ALLOWED_ORIGINS`
- Or set `ALLOWED_ORIGINS=*` for development (not recommended for production)

## Environment Variables Reference

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OPENAI_API_KEY` | Yes | - | OpenAI API key for AI features |
| `OPENAI_MODEL` | No | `gpt-4o-mini` | OpenAI model to use |
| `AI_CONTEXT` | No | (default tutor context) | General AI instructions |
| `ALLOWED_ORIGINS` | No | `localhost:5173,localhost:3000` | CORS allowed origins |
| `PORT` | Auto | - | Server port (set by Railway) |
| `RAILWAY_PUBLIC_DOMAIN` | Auto | - | Railway domain (set by Railway) |

## Post-Deployment

1. Test the health endpoint: `https://your-app.railway.app/api/health`
2. Test the frontend: `https://your-app.railway.app`
3. Create a revision and test the full workflow
4. Monitor logs in Railway dashboard

## Custom Domain (Optional)

1. In Railway project, go to "Settings" → "Domains"
2. Add your custom domain
3. Update DNS records as instructed
4. Update `ALLOWED_ORIGINS` to include your custom domain

