---
name: JSON to Supabase Migration
overview: Migrate places_bootstrap.json to Supabase Postgres database with improved concurrency handling using database transactions and row-level locking instead of file-based locks.
todos:
  - id: create_schema
    content: Create Supabase database schema (places table with JSONB columns and indexes)
    status: pending
  - id: setup_db_connection
    content: Set up database connection layer (db_storage.py) with connection pooling
    status: pending
  - id: create_migration_script
    content: Create migration script to load JSON and batch insert into Supabase
    status: pending
    dependencies:
      - create_schema
      - setup_db_connection
  - id: run_migration
    content: Run one-time migration script to transfer all data from JSON to database
    status: pending
    dependencies:
      - create_migration_script
  - id: update_storage_layer
    content: Rename json_storage.py to db_storage.py and update functions to use database with row-level locking
    status: pending
    dependencies:
      - setup_db_connection
  - id: update_service_layer
    content: Rename json_service.py to db_service.py and update places_manager.py to use new database storage
    status: pending
    dependencies:
      - update_storage_layer
  - id: update_imports
    content: Update all imports across codebase to use new file names (db_storage, db_service) and function names, remove path/json_path parameters
    status: pending
    dependencies:
      - update_service_layer
  - id: remove_file_locks
    content: Remove file_lock.py dependencies and replace with database transactions
    status: pending
    dependencies:
      - update_imports
  - id: test_concurrency
    content: Test concurrent read/write operations to verify concurrency improvements
    status: pending
    dependencies:
      - update_imports
  - id: update_requirements
    content: Add database dependencies (supabase or psycopg2/asyncpg) to requirements.txt
    status: pending
    dependencies:
      - setup_db_connection
isProject: false
---

# JSON to Supabase Postgres Migration Plan

## Overview

Migrate the large JSON file (`places_bootstrap.json`, ~68k+ lines) to Supabase Postgres database to eliminate file-based concurrency issues and improve performance. Replace file locks with database transactions and row-level locking.

## Architecture Changes

### Current State

- **Storage**: Single JSON file with file-based locking (`file_lock.py`)
- **Concurrency**: File-level locks cause contention when multiple processes read/write
- **Operations**: Load entire file → modify → save entire file (expensive for large files)

### Target State

- **Storage**: Supabase Postgres with JSONB columns for nested data
- **Concurrency**: Database transactions with row-level locking (`SELECT FOR UPDATE`)
- **Operations**: Direct row updates without loading entire dataset

## Implementation Steps

### 1. Database Schema Design

Create a `places` table in Supabase with:

- `place_id` (TEXT PRIMARY KEY) - Google Places ID
- `nearby_search_flag` (BOOLEAN)
- `places_details_flag` (BOOLEAN)
- `tavily_flag` (BOOLEAN)
- `enriched_flag` (BOOLEAN)
- `place` (JSONB) - Place details object
- `sources` (JSONB) - Sources object (Tavily data, etc.)
- `derived` (JSONB) - LLM-derived attributes
- `created_at` (TIMESTAMP)
- `updated_at` (TIMESTAMP)

**Indexes**:

- `**place_id` (PRIMARY KEY)**: Automatically creates a unique B-tree index
  - **Benefits**: 
    - O(log n) lookups by place_id (all queries will use this)
    - Enforces uniqueness (prevents duplicate place_ids)
    - Fast JOINs and foreign key references
    - Fast UPDATE/DELETE operations when filtering by place_id
    - No explicit index needed - PRIMARY KEY constraint provides this automatically
  - **Drawbacks**: 
    - Minimal: Slight overhead on INSERTs (index maintenance), but negligible
    - Takes small amount of storage, but essential for performance
    - None significant - PRIMARY KEY index is always recommended for lookup keys
- Index on `enriched_flag` for filtering unenriched places (WHERE enriched_flag = false)
- GIN index on `place` JSONB for efficient JSON queries (e.g., filtering by place->>'name')
- Index on `updated_at` for monitoring and cleanup queries

### 2. Supabase Connection Setup

Create `backend/enrichment/db_storage.py`:

- Use `supabase-py` or `psycopg2`/`asyncpg` for direct Postgres connection
- Connection pooling for concurrent operations
- Environment variables for connection: `SUPABASE_URL`, `SUPABASE_KEY` (service role), or `DATABASE_URL`
- Context manager for connection handling

### 3. Migration Script

Create `backend/scripts/migrate_json_to_db.py`:

- Load JSON file in chunks (handle large file)
- Batch insert using `COPY` or batch `INSERT` statements
- Progress tracking and error handling
- Data validation (verify all place_ids migrated)
- Create backup before migration
- Optional: Keep JSON as read-only backup initially

### 4. Database Service Layer

**Rename and replace** `backend/enrichment/json_storage.py` → `backend/enrichment/db_storage.py`:

**New function names (removing "json" references)**:

- `load_place(place_id)` - Load single place by ID
- `load_places(place_ids)` - Load multiple places by IDs
- `load_all_places()` - Load all places (for compatibility, but avoid in production)
- `upsert_place(place)` - Upsert single place with transaction (removes `path` parameter)
- `upsert_place_ids(place_ids)` - Batch upsert with transaction (removes `path` parameter)
- `save_place(place)` - Update existing place (replaces `save_places_json`)
- `reset_enrichment_flag(place_ids, clear_data)` - Batch update flags (removes `json_path` parameter)

**Function signature changes**:

- Remove `path`/`json_path` parameters (database connection handled internally)
- Remove `use_lock` parameter (database transactions handle concurrency)

**Concurrency improvements**:

- Use `SELECT FOR UPDATE` for row-level locking during updates
- Database transactions ensure atomicity
- Connection pooling handles concurrent requests
- Remove file lock dependencies

### 5. Rename Files and Update Code References

**File renames**:

- `backend/enrichment/json_storage.py` → `backend/enrichment/db_storage.py`
- `backend/api/services/json_service.py` → `backend/api/services/db_service.py`

**Function renames**:

- `load_places_json(path, use_lock)` → `load_all_places()` (no path needed)
- `save_places_json(path, places, use_lock)` → `save_place(place)` or `save_places(places)` (no path needed)
- `upsert_place(path, place)` → `upsert_place(place)` (remove path parameter)
- `upsert_place_ids(path, place_ids)` → `upsert_place_ids(place_ids)` (remove path parameter)
- `reset_enrichment_flag(json_path, place_ids, clear_data)` → `reset_enrichment_flag(place_ids, clear_data)` (remove json_path)

**Files to update with new imports**:

- `backend/enrichment/places_manager.py` - Update imports and function calls (remove path parameters)
- `backend/api/routes/places.py` - Update imports and function calls (remove path parameters)
- `backend/api/services/enrichment_service.py` - Update imports and function calls
- `backend/enrichment/__init__.py` - Update exports with new function names
- `backend/api/services/db_service.py` - Update function signatures (remove json_path parameters)

**Migration strategy**:

- **One-time migration**: After migration script runs, all code uses database
- **Clean naming**: Remove all "json" references from function and file names
- **Remove path parameters**: Database connection handled internally via environment variables
- **No dual-write**: Since you chose one-time migration, we fully switch to database (no JSON fallback code)
- **JSON file as backup only**: Keep `places_bootstrap.json` as a data backup file, but code doesn't read from it

### 6. Remove File Locking

**Files to deprecate/remove**:

- `backend/enrichment/file_lock.py` - No longer needed
- `backend/enrichment/process_lock.py` - Keep for in-memory coordination, but reduce reliance

**Replace with**:

- Database row-level locks (`SELECT FOR UPDATE NOWAIT`)
- Optimistic locking using `updated_at` timestamps
- Transaction isolation levels

### 7. Testing & Validation

- **Data integrity**: Verify all places migrated correctly
- **Concurrency testing**: Test multiple concurrent upserts
- **Performance**: Compare database operations vs file operations
- **Rollback plan**: Keep JSON backup until migration verified

## Key Files to Create/Modify

### New Files

- `backend/enrichment/db_storage.py` - Database storage layer (replaces json_storage.py)
- `backend/scripts/migrate_json_to_db.py` - Migration script
- `backend/enrichment/db_config.py` - Database connection configuration

### Renamed Files

- `backend/enrichment/json_storage.py` → `backend/enrichment/db_storage.py` (delete old file after migration)
- `backend/api/services/json_service.py` → `backend/api/services/db_service.py` (delete old file after migration)

### Modified Files

- `backend/enrichment/db_storage.py` - Database storage functions (new file, replaces json_storage.py)
- `backend/api/services/db_service.py` - Database service functions (new file, replaces json_service.py)
- `backend/enrichment/places_manager.py` - Update imports and function calls (remove path parameters)
- `backend/api/routes/places.py` - Update imports and function calls (remove path parameters)
- `backend/api/services/enrichment_service.py` - Update imports and function calls
- `backend/enrichment/__init__.py` - Update exports with new function names
- `backend/requirements.txt` - Add `supabase` or `psycopg2`/`asyncpg`

**Note**: All "json" references removed from file and function names. The JSON file itself (`places_bootstrap.json`) is kept as a data backup only.

## Concurrency Improvements

### Before (File-based)

```python
with file_lock(path, timeout=10.0):  # Blocks entire file
    places = load_places_json(path)  # Load 68k+ lines
    places[place_id] = updated_place
    save_places_json(path, places)  # Write 68k+ lines
```

### After (Database-based)

```python
with db_transaction():
    place = db.load_place(place_id, for_update=True)  # Row-level lock
    db.upsert_place(updated_place)  # Single row update
```

**Benefits**:

- No file lock contention
- Only lock specific rows being updated
- Concurrent reads don't block writes
- Better performance for large datasets
- ACID guarantees from database

## Environment Variables Needed

```bash
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-service-role-key
# OR
DATABASE_URL=postgresql://user:pass@host:port/dbname
```

## Migration Checklist

- Create Supabase table schema
- Set up database connection
- Create migration script
- Run migration (one-time)
- Verify data integrity
- Rename json_storage.py → db_storage.py and update functions
- Rename json_service.py → db_service.py and update functions
- Update all imports across codebase
- Remove path/json_path parameters from function calls
- Test concurrent operations
- Remove file lock dependencies
- Delete old json_storage.py and json_service.py files
- Update documentation
- Keep JSON file as backup (optional)

