#!/usr/bin/env python3
"""
Run all database migrations in order.

This script runs all migration scripts to ensure the database schema is up to date.
Migrations are run in order and are idempotent (safe to run multiple times).
"""

import os
import sys
import subprocess
from pathlib import Path

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Check if DATABASE_URL is set
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("⚠️  DATABASE_URL not set - skipping migrations")
    print("   This is normal if running without a database.")
    sys.exit(0)

# Get the directory where this script is located
SCRIPT_DIR = Path(__file__).parent

# Define migrations in order
MIGRATIONS = [
    "migrate_add_multiple_choice.py",
    "migrate_add_question_flags.py",
    "migrate_add_prep_checks.py",
    "migrate_add_prep_check_versioning.py",
]

def run_migration(migration_file: str) -> bool:
    """Run a single migration script."""
    migration_path = SCRIPT_DIR / migration_file
    
    if not migration_path.exists():
        print(f"⚠️  Migration file not found: {migration_file}")
        return False
    
    print(f"\n{'='*70}")
    print(f"Running: {migration_file}")
    print(f"{'='*70}")
    
    try:
        result = subprocess.run(
            [sys.executable, str(migration_path)],
            cwd=SCRIPT_DIR,
            check=True,
            capture_output=False,
            text=True
        )
        print(f"✅ {migration_file} completed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ {migration_file} failed with exit code {e.returncode}")
        return False
    except Exception as e:
        print(f"❌ Error running {migration_file}: {e}")
        return False

def main():
    """Run all migrations in order."""
    print("="*70)
    print("Database Migration Runner")
    print("="*70)
    print(f"Database: {DATABASE_URL.split('@')[-1] if '@' in DATABASE_URL else 'configured'}")
    print()
    
    failed_migrations = []
    
    for migration in MIGRATIONS:
        if not run_migration(migration):
            failed_migrations.append(migration)
    
    print("\n" + "="*70)
    if failed_migrations:
        print(f"❌ Migration completed with {len(failed_migrations)} failure(s):")
        for migration in failed_migrations:
            print(f"   - {migration}")
        print("\n⚠️  Some migrations failed. Check the output above for details.")
        sys.exit(1)
    else:
        print("✅ All migrations completed successfully!")
        print("="*70)
        sys.exit(0)

if __name__ == "__main__":
    main()

