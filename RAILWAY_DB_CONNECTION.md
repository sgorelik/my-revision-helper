# Connecting PostgreSQL Database on Railway

## ✅ Good News: It's Already Connected!

When you add a PostgreSQL service in Railway, Railway **automatically**:
1. Creates the database
2. Sets the `DATABASE_URL` environment variable
3. Links it to your application service

Your code is already configured to use it automatically!

## How to Verify It's Connected

### Step 1: Check Railway Dashboard

1. Go to your Railway project dashboard
2. Click on your **PostgreSQL service**
3. Go to the **"Variables"** tab
4. You should see `DATABASE_URL` listed (it's automatically set)

### Step 2: Verify It's Linked to Your App

1. Go to your **main application service** (not the database)
2. Go to **"Variables"** tab
3. You should see `DATABASE_URL` there too (Railway shares it automatically)

If you don't see it:
- Make sure both services are in the same Railway project
- Railway automatically shares variables between services in the same project

### Step 3: Check Application Logs

After your app redeploys (or if it's already running), check the logs:

1. Go to your **application service** in Railway
2. Click **"Deployments"** → Click on the latest deployment
3. Look for these log messages:

**✅ Success messages:**
```
INFO:my_revision_helper.database:Database connection configured
INFO:my_revision_helper.database:Database tables initialized
```

**❌ If database not connected:**
```
INFO:my_revision_helper.database:DATABASE_URL not set - database features disabled
```

### Step 4: Test It Works

1. Visit your Railway app: `https://your-app.up.railway.app`
2. Create a revision (fill out the form and submit)
3. Check the logs - you should see database operations
4. The revision should be persisted to the database

## If It's Not Working

### Problem: DATABASE_URL not visible in app service

**Solution:**
1. In Railway dashboard, go to your **PostgreSQL service**
2. Click **"Settings"** tab
3. Make sure it's in the same project as your app
4. Railway should automatically share the variable

If still not working:
- Manually add `DATABASE_URL` to your app service:
  1. Go to app service → **Variables**
  2. Click **"+ New Variable"**
  3. Name: `DATABASE_URL`
  4. Value: Copy from PostgreSQL service → Variables tab
  5. Click **"Add"**

### Problem: Database connection errors in logs

**Check:**
- Is PostgreSQL service running? (should show "Active" in Railway)
- Are both services in the same project?
- Check Railway logs for specific error messages

**Common fixes:**
- Restart your application service
- Verify PostgreSQL service is active
- Check that `DATABASE_URL` format is correct (should start with `postgresql://`)

## What Happens Automatically

When your app starts:

1. ✅ Reads `DATABASE_URL` from environment (set by Railway)
2. ✅ Connects to PostgreSQL database
3. ✅ Creates all tables automatically (`init_db()` is called on startup)
4. ✅ All data operations use the database instead of in-memory storage

## Tables Created Automatically

Your app will create these tables on first startup:
- `users` - Authenticated users
- `revisions` - Revision definitions
- `revision_runs` - Test runs/sessions
- `run_questions` - Questions for each run
- `run_answers` - Student answers and results

## Quick Checklist

- [ ] PostgreSQL service added to Railway
- [ ] PostgreSQL service shows "Active" status
- [ ] `DATABASE_URL` visible in app service variables (or shared automatically)
- [ ] App redeployed after adding database
- [ ] Logs show "Database connection configured"
- [ ] Logs show "Database tables initialized"
- [ ] Test: Create a revision and verify it persists

## Next Steps

Once connected:
1. ✅ All data will persist to PostgreSQL
2. ✅ Authenticated users' data will persist across sessions
3. ✅ Anonymous users' data will be stored (but session-only access)
4. ✅ You can query the database via Railway's PostgreSQL dashboard

---

**That's it!** Railway handles the connection automatically. Just make sure both services are in the same project and your app will use the database on the next deployment.

