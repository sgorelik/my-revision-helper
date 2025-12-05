#!/bin/bash
# Setup script for local PostgreSQL database

set -e

echo "=========================================="
echo "Local PostgreSQL Database Setup"
echo "=========================================="
echo ""

# Check if PostgreSQL is installed
if command -v psql &> /dev/null; then
    echo "✓ PostgreSQL client found"
    PSQL_CMD=psql
elif docker ps &> /dev/null; then
    echo "✓ Docker found - will use Docker for PostgreSQL"
    USE_DOCKER=true
else
    echo "✗ Neither PostgreSQL nor Docker found"
    echo ""
    echo "Please install one of:"
    echo "  1. PostgreSQL: brew install postgresql@14"
    echo "  2. Docker: https://www.docker.com/products/docker-desktop"
    exit 1
fi

# Database configuration
DB_NAME="revision_helper"
DB_USER="postgres"
DB_PASSWORD="revision_helper_dev"
DB_PORT="5432"

if [ "$USE_DOCKER" = true ]; then
    echo ""
    echo "Setting up PostgreSQL with Docker..."
    
    # Check if container already exists
    if docker ps -a --format '{{.Names}}' | grep -q "^postgres-revision-helper$"; then
        echo "⚠ Container 'postgres-revision-helper' already exists"
        read -p "Remove and recreate? (y/n) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            docker stop postgres-revision-helper 2>/dev/null || true
            docker rm postgres-revision-helper 2>/dev/null || true
        else
            echo "Using existing container..."
            docker start postgres-revision-helper 2>/dev/null || true
            exit 0
        fi
    fi
    
    # Start PostgreSQL container
    docker run --name postgres-revision-helper \
        -e POSTGRES_PASSWORD=$DB_PASSWORD \
        -e POSTGRES_DB=$DB_NAME \
        -e POSTGRES_USER=$DB_USER \
        -p $DB_PORT:5432 \
        -d postgres:14
    
    echo "✓ PostgreSQL container started"
    echo "  Container: postgres-revision-helper"
    echo "  Port: $DB_PORT"
    echo "  Database: $DB_NAME"
    echo "  User: $DB_USER"
    echo "  Password: $DB_PASSWORD"
    
    # Wait for PostgreSQL to be ready
    echo ""
    echo "Waiting for PostgreSQL to be ready..."
    sleep 3
    for i in {1..30}; do
        if docker exec postgres-revision-helper pg_isready -U $DB_USER &> /dev/null; then
            echo "✓ PostgreSQL is ready!"
            break
        fi
        if [ $i -eq 30 ]; then
            echo "✗ PostgreSQL failed to start"
            exit 1
        fi
        sleep 1
    done
    
else
    echo ""
    echo "Setting up PostgreSQL (local installation)..."
    
    # Check if PostgreSQL is running
    if ! pg_isready &> /dev/null; then
        echo "⚠ PostgreSQL server is not running"
        echo "  Start it with: brew services start postgresql@14"
        echo "  Or: pg_ctl -D /usr/local/var/postgresql@14 start"
        exit 1
    fi
    
    echo "✓ PostgreSQL server is running"
    
    # Create database if it doesn't exist
    if psql -lqt | cut -d \| -f 1 | grep -qw $DB_NAME; then
        echo "⚠ Database '$DB_NAME' already exists"
    else
        createdb $DB_NAME
        echo "✓ Database '$DB_NAME' created"
    fi
fi

# Create .env file with DATABASE_URL
ENV_FILE=".env"
DATABASE_URL="postgresql://${DB_USER}:${DB_PASSWORD}@localhost:${DB_PORT}/${DB_NAME}"

if [ -f "$ENV_FILE" ]; then
    # Check if DATABASE_URL already exists
    if grep -q "^DATABASE_URL=" "$ENV_FILE"; then
        echo ""
        echo "⚠ DATABASE_URL already exists in .env"
        echo "  Current value: $(grep '^DATABASE_URL=' $ENV_FILE)"
        read -p "Update it? (y/n) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            # Update existing DATABASE_URL
            if [[ "$OSTYPE" == "darwin"* ]]; then
                sed -i '' "s|^DATABASE_URL=.*|DATABASE_URL=$DATABASE_URL|" "$ENV_FILE"
            else
                sed -i "s|^DATABASE_URL=.*|DATABASE_URL=$DATABASE_URL|" "$ENV_FILE"
            fi
            echo "✓ Updated DATABASE_URL in .env"
        fi
    else
        echo "" >> "$ENV_FILE"
        echo "# Database" >> "$ENV_FILE"
        echo "DATABASE_URL=$DATABASE_URL" >> "$ENV_FILE"
        echo "✓ Added DATABASE_URL to .env"
    fi
else
    echo "DATABASE_URL=$DATABASE_URL" > "$ENV_FILE"
    echo "✓ Created .env file with DATABASE_URL"
fi

echo ""
echo "=========================================="
echo "Setup Complete!"
echo "=========================================="
echo ""
echo "Database URL: $DATABASE_URL"
echo ""
echo "Next steps:"
echo "1. Restart your backend server"
echo "2. Run: python test_database.py"
echo "3. Tables will be created automatically on server startup"
echo ""
if [ "$USE_DOCKER" = true ]; then
    echo "Docker commands:"
    echo "  Stop: docker stop postgres-revision-helper"
    echo "  Start: docker start postgres-revision-helper"
    echo "  Remove: docker rm -f postgres-revision-helper"
fi

