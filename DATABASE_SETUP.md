# Database Persistence Setup Guide

## Overview

The application is ready for database persistence. All code is in place - you just need to provide a `DATABASE_URL`.

## Option 1: Local PostgreSQL (Development)

### Install PostgreSQL
```bash
# macOS
brew install postgresql@14
brew services start postgresql@14

# Or use Docker
docker run --name postgres-revision-helper \
  -e POSTGRES_PASSWORD=yourpassword \
  -e POSTGRES_DB=revision_helper \
  -p 5432:5432 \
  -d postgres:14
```

### Create Database
```bash
# Connect to PostgreSQL
psql postgres

# Create database
CREATE DATABASE revision_helper;
\q
```

### Set DATABASE_URL
Add to your `.env` file in project root:
```env
DATABASE_URL=postgresql://postgres:yourpassword@localhost:5432/revision_helper
```

## Option 2: Railway PostgreSQL (Production)

1. In Railway dashboard → Your Project → **New** → **Database** → **Add PostgreSQL**
2. Railway automatically sets `DATABASE_URL` environment variable
3. No additional configuration needed!

## Option 3: Other PostgreSQL Providers

Any PostgreSQL provider works. Just set `DATABASE_URL`:
```env
DATABASE_URL=postgresql://user:password@host:port/database
```

## Verify Setup

### Test Database Connection
```bash
python -c "from my_revision_helper.database import DATABASE_URL, engine, init_db; print('DATABASE_URL:', 'SET' if DATABASE_URL else 'NOT SET'); init_db(); print('Tables created successfully!')"
```

### Check Tables Created
If using local PostgreSQL:
```bash
psql -d revision_helper -c "\dt"
```

You should see:
- users
- revisions
- revision_runs
- run_questions
- run_answers

## How It Works

### Automatic Table Creation
- Tables are created automatically on server startup via `init_db()`
- No manual migration needed for initial setup
- Uses SQLAlchemy's `create_all()`

### Data Persistence
- **Authenticated users**: Data stored with `user_id` - persists across sessions
- **Anonymous users**: Data stored with `session_id` - only accessible in current session
- **All data**: Persisted to database when `DATABASE_URL` is set

### Fallback Behavior
- If `DATABASE_URL` is not set: Uses in-memory storage (current behavior)
- If database connection fails: Falls back to in-memory storage
- App continues to work in both cases

## Testing

1. Set `DATABASE_URL` in `.env`
2. Restart backend server
3. Create a revision (authenticated or anonymous)
4. Check database to verify data is stored:
   ```sql
   SELECT * FROM revisions;
   SELECT * FROM users;
   ```

## Next Steps (Optional)

- Add Alembic for database migrations (for schema changes)
- Add database connection pooling configuration
- Add database backup strategy

