# 🚀 Quick Railway Deployment Checklist

## Pre-Deployment (5 minutes)

- [x] ✅ Build script created (`build.sh`)
- [x] ✅ Railway config updated (`railway.json`)
- [x] ✅ Procfile ready
- [x] ✅ Frontend build path configured in `api.py`

## Deployment Steps (10 minutes)

### 1. Push to GitHub (if not already done)
```bash
git add build.sh railway.json RAILWAY_DEPLOY.md
git commit -m "Add Railway deployment configuration"
git push origin main
```

### 2. Create Railway Project
1. Go to https://railway.app/new
2. Click **"Deploy from GitHub repo"**
3. Select your `my-revision-helper` repository
4. Railway will auto-detect and start building

### 3. Set Environment Variables
In Railway dashboard → Your Project → Variables tab, add:

**Required:**
```
OPENAI_API_KEY=sk-your-actual-key-here
```

**Optional (but recommended):**
```
OPENAI_MODEL=gpt-4o-mini
ALLOWED_ORIGINS=*
```

### 4. Wait for Build
- Railway will:
  - Install Node.js dependencies
  - Build the frontend
  - Install Python dependencies
  - Start the server

### 5. Get Your URL
- Railway provides a URL like: `https://your-app.up.railway.app`
- Click "Settings" → "Generate Domain" if needed
- Copy the public URL

## Testing (5 minutes)

1. **Health Check:**
   ```
   https://your-app.up.railway.app/api/health
   ```
   Should return: `{"status": "ok"}`

2. **Frontend:**
   ```
   https://your-app.up.railway.app
   ```
   Should show the revision helper UI

3. **Create a Revision:**
   - Fill out the form
   - Test file upload (optional)
   - Verify questions are generated

## Troubleshooting

**Build fails?**
- Check Railway logs
- Ensure `frontend/package.json` exists
- Verify Node.js is detected (Railway auto-detects)

**App doesn't start?**
- Check logs for Python errors
- Verify `PORT` is set (Railway sets this automatically)
- Check Procfile command

**Frontend not loading?**
- Check that `frontend/dist` was built
- Verify static file serving in logs
- Check Railway build logs for frontend build errors

**CORS errors?**
- Set `ALLOWED_ORIGINS=*` in Railway variables
- Or add your Railway domain to `ALLOWED_ORIGINS`

## Quick Commands

**View logs:**
```bash
railway logs
```

**Set variable:**
```bash
railway variables set OPENAI_API_KEY=sk-xxx
```

**Redeploy:**
```bash
railway up
```

## Files Created

- ✅ `build.sh` - Build script for Railway
- ✅ `railway.json` - Railway configuration
- ✅ `RAILWAY_DEPLOY.md` - Detailed deployment guide
- ✅ `DEPLOY_CHECKLIST.md` - This checklist

## Next Steps After Deployment

1. Test all features (create revision, answer questions, view summary)
2. Share the URL with your kids/friends
3. Monitor usage in Railway dashboard
4. Consider adding a custom domain (optional)

---

**Time estimate:** ~20 minutes total
**Cost:** Free tier available (with usage limits)

