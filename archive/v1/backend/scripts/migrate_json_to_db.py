"""
Migration script to transfer data from places_bootstrap.json to Supabase database.

Usage:
    python -m backend.scripts.migrate_json_to_db [--json-path path/to/places_bootstrap.json]
"""

import json
import os
import sys
import logging
import argparse
from pathlib import Path
from typing import Dict
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import psycopg2
import psycopg2.extras
from backend.enrichment.db_config import get_database_url, get_connection_pool

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def load_json_file(json_path: str) -> Dict:
    """Load JSON file and return dictionary."""
    logger.info(f"Loading JSON file: {json_path}")
    
    if not os.path.exists(json_path):
        raise FileNotFoundError(f"JSON file not found: {json_path}")
    
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    # Ensure it's a dictionary keyed by place_id
    if isinstance(data, list):
        logger.info(f"Converting list format to dict format ({len(data)} items)")
        result = {}
        for place in data:
            place_id = place.get("place_id")
            if place_id:
                result[place_id] = place
        return result
    elif isinstance(data, dict):
        logger.info(f"Loaded {len(data)} places from JSON")
        return data
    else:
        raise ValueError(f"Unexpected data type: {type(data)}")


def migrate_places(json_path: str, batch_size: int = 100) -> None:
    """
    Migrate places from JSON file to database.
    
    Args:
        json_path: Path to JSON file
        batch_size: Number of places to insert per batch
    """
    # Load JSON data
    places = load_json_file(json_path)
    
    if not places:
        logger.warning("No places found in JSON file")
        return
    
    # Get database connection
    database_url = get_database_url()
    if not database_url:
        raise ValueError(
            "Database connection not configured. Set DATABASE_URL or "
            "SUPABASE_URL + SUPABASE_DB_PASSWORD environment variables"
        )
    
    logger.info(f"Connecting to database...")
    conn = psycopg2.connect(database_url)
    
    try:
        with conn.cursor() as cur:
            # Check if table exists
            cur.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'places'
                )
            """)
            table_exists = cur.fetchone()[0]
            
            if not table_exists:
                raise ValueError(
                    "Places table does not exist. "
                    "Please run create_places_schema.sql in your Supabase SQL editor first."
                )
            
            # Get count of existing places
            cur.execute("SELECT COUNT(*) FROM places")
            existing_count = cur.fetchone()[0]
            logger.info(f"Existing places in database: {existing_count}")
            
            # Prepare data for batch insert
            total_places = len(places)
            inserted_count = 0
            updated_count = 0
            error_count = 0
            
            logger.info(f"Starting migration of {total_places} places (batch size: {batch_size})")
            
            # Process in batches
            place_items = list(places.items())
            for i in range(0, total_places, batch_size):
                batch = place_items[i:i + batch_size]
                batch_num = (i // batch_size) + 1
                total_batches = (total_places + batch_size - 1) // batch_size
                
                logger.info(f"Processing batch {batch_num}/{total_batches} ({len(batch)} places)")
                
                try:
                    # Use COPY for faster bulk insert (or INSERT with ON CONFLICT for upsert)
                    for place_id, place_data in batch:
                        try:
                            # Prepare JSONB fields
                            place_jsonb = json.dumps(place_data.get("place", {}))
                            sources_jsonb = json.dumps(place_data.get("sources", {}))
                            derived_jsonb = json.dumps(place_data.get("derived", {}))
                            
                            # Upsert using ON CONFLICT
                            cur.execute("""
                                INSERT INTO places (
                                    place_id, nearby_search_flag, places_details_flag,
                                    tavily_flag, enriched_flag, place, sources, derived
                                ) VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb)
                                ON CONFLICT (place_id) DO UPDATE SET
                                    nearby_search_flag = EXCLUDED.nearby_search_flag,
                                    places_details_flag = EXCLUDED.places_details_flag,
                                    tavily_flag = EXCLUDED.tavily_flag,
                                    enriched_flag = EXCLUDED.enriched_flag,
                                    place = EXCLUDED.place,
                                    sources = EXCLUDED.sources,
                                    derived = EXCLUDED.derived,
                                    updated_at = NOW()
                            """, (
                                place_id,
                                place_data.get("nearby_search_flag", False),
                                place_data.get("places_details_flag", False),
                                place_data.get("tavily_flag", False),
                                place_data.get("enriched_flag", False),
                                place_jsonb,
                                sources_jsonb,
                                derived_jsonb,
                            ))
                            
                            if cur.rowcount > 0:
                                # Check if it was an insert or update
                                cur.execute("SELECT created_at = updated_at FROM places WHERE place_id = %s", (place_id,))
                                is_new = cur.fetchone()[0]
                                if is_new:
                                    inserted_count += 1
                                else:
                                    updated_count += 1
                        
                        except Exception as e:
                            error_count += 1
                            logger.error(f"Error migrating place {place_id}: {e}")
                            continue
                    
                    # Commit batch
                    conn.commit()
                    logger.info(
                        f"Batch {batch_num} completed. "
                        f"Progress: {min(i + batch_size, total_places)}/{total_places}"
                    )
                
                except Exception as e:
                    conn.rollback()
                    logger.error(f"Error in batch {batch_num}: {e}")
                    raise
            
            # Final verification
            cur.execute("SELECT COUNT(*) FROM places")
            final_count = cur.fetchone()[0]
            
            logger.info("=" * 60)
            logger.info("Migration completed!")
            logger.info(f"Total places in JSON: {total_places}")
            logger.info(f"Places inserted: {inserted_count}")
            logger.info(f"Places updated: {updated_count}")
            logger.info(f"Errors: {error_count}")
            logger.info(f"Final count in database: {final_count}")
            logger.info("=" * 60)
            
            if final_count != total_places:
                logger.warning(
                    f"Count mismatch! Expected {total_places} places, "
                    f"but database has {final_count}. Some places may have failed to migrate."
                )
    
    finally:
        conn.close()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Migrate places from JSON to Supabase database")
    parser.add_argument(
        "--json-path",
        type=str,
        default=os.path.join(
            Path(__file__).parent.parent,
            "data",
            "places_bootstrap.json"
        ),
        help="Path to places_bootstrap.json file"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Number of places to process per batch (default: 100)"
    )
    
    args = parser.parse_args()
    
    try:
        migrate_places(args.json_path, args.batch_size)
    except Exception as e:
        logger.error(f"Migration failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()

