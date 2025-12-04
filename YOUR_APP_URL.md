# Your Live App URL

## 🌐 Production URL
**https://web-production-35acf.up.railway.app/**

## Quick Tests

### 1. Health Check
```
https://web-production-35acf.up.railway.app/api/health
```
Expected: `{"status": "ok"}`

### 2. Frontend
```
https://web-production-35acf.up.railway.app/
```
Expected: Revision Helper UI

### 3. Test Features
- ✅ Create a revision
- ✅ Upload images (if OpenAI key is set)
- ✅ Answer questions
- ✅ View summary

## Important: Set Environment Variables

Make sure you've set in Railway Dashboard → Variables:
- `OPENAI_API_KEY` (required for AI features)
- `OPENAI_MODEL` (optional, defaults to gpt-4o-mini)
- `ALLOWED_ORIGINS` (optional, set to `*` for now)

## Share Your App

Your app is now live! Share this URL:
**https://web-production-35acf.up.railway.app/**

## Monitor

- **View Logs:** Railway Dashboard → Deployments → View Logs
- **Check Status:** Railway Dashboard → Service status

