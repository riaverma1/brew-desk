"""
Database connection configuration for Supabase Postgres.
"""
import os
import logging
from typing import Optional
from contextlib import contextmanager

logger = logging.getLogger(__name__)

# Try to use psycopg2 (direct Postgres) or supabase-py
try:
    import psycopg2
    from psycopg2 import pool
    from psycopg2.extras import RealDictCursor
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False
    logger.warning("psycopg2 not available, will try supabase-py")

try:
    from supabase import create_client
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False
    logger.warning("supabase-py not available, will try psycopg2")


def get_database_url() -> Optional[str]:
    """Get database connection URL from environment variables."""
    # Try DATABASE_URL first (direct Postgres connection)
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        # Check if it's a Supabase API URL (starts with https://) instead of postgresql://
        if database_url.startswith("https://"):
            # It's a Supabase API URL, need to convert to PostgreSQL connection string
            # Extract project ref from URL: https://project-ref.supabase.co
            project_ref = database_url.replace("https://", "").replace(".supabase.co", "").rstrip("/")
            db_password = os.getenv("SUPABASE_DB_PASSWORD")
            if not db_password:
                raise ValueError(
                    "DATABASE_URL is set to Supabase API URL, but SUPABASE_DB_PASSWORD is not set. "
                    "Please set SUPABASE_DB_PASSWORD to your database password, or set DATABASE_URL "
                    "to a PostgreSQL connection string: postgresql://postgres:[password]@db.[project-ref].supabase.co:5432/postgres"
                )
            return f"postgresql://postgres:{db_password}@db.{project_ref}.supabase.co:5432/postgres"
        # It's already a PostgreSQL connection string
        return database_url
    
    # Try Supabase connection string format using SUPABASE_URL
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_KEY")  # Service role key
    
    if supabase_url and supabase_key:
        # Extract database connection details from Supabase URL
        # Supabase URL format: https://project-ref.supabase.co
        # We need to construct: postgresql://postgres:[password]@db.project-ref.supabase.co:5432/postgres
        # But we need the password from SUPABASE_DB_PASSWORD or use the service role key
        db_password = os.getenv("SUPABASE_DB_PASSWORD")
        if db_password:
            # Extract project ref from URL
            project_ref = supabase_url.replace("https://", "").replace(".supabase.co", "").rstrip("/")
            return f"postgresql://postgres:{db_password}@db.{project_ref}.supabase.co:5432/postgres"
    
    return None


# Connection pool for psycopg2
_connection_pool: Optional[pool.ThreadedConnectionPool] = None


def get_connection_pool() -> pool.ThreadedConnectionPool:
    """Get or create connection pool."""
    global _connection_pool
    
    if _connection_pool is None:
        database_url = get_database_url()
        if not database_url:
            raise ValueError(
                "Database connection not configured. Set DATABASE_URL or "
                "SUPABASE_URL + SUPABASE_DB_PASSWORD environment variables"
            )
        
        # Create connection pool (min 1, max 10 connections)
        _connection_pool = pool.ThreadedConnectionPool(
            minconn=1,
            maxconn=10,
            dsn=database_url
        )
        logger.info("Created database connection pool")
    
    return _connection_pool


@contextmanager
def get_db_connection():
    """Get database connection from pool (context manager)."""
    if not PSYCOPG2_AVAILABLE:
        raise ImportError("psycopg2 is required. Install with: pip install psycopg2-binary")
    
    pool = get_connection_pool()
    conn = pool.getconn()
    try:
        yield conn
    finally:
        pool.putconn(conn)


def get_supabase_client():
    """Get Supabase client if available."""
    if not SUPABASE_AVAILABLE:
        return None
    
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_KEY")
    
    if not supabase_url or not supabase_key:
        return None
    
    return create_client(supabase_url, supabase_key)


def close_connection_pool():
    """Close connection pool (call on shutdown)."""
    global _connection_pool
    if _connection_pool:
        _connection_pool.closeall()
        _connection_pool = None
        logger.info("Closed database connection pool")

