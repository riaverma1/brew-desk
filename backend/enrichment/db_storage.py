"""
Database storage layer for places data.

Replaces json_storage.py with database-backed storage using Supabase Postgres.
Uses row-level locking and transactions for concurrency control.
"""

import json
import logging
from typing import Dict, List, Optional
from contextlib import contextmanager

import psycopg2
import psycopg2.extras

from backend.enrichment.db_config import get_db_connection

logger = logging.getLogger(__name__)


@contextmanager
def db_transaction():
    """Context manager for database transactions."""
    with get_db_connection() as conn:
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Transaction failed, rolling back: {e}")
            raise


def load_place(place_id: str) -> Optional[Dict]:
    """
    Load a single place by place_id.
    
    Args:
        place_id: Place ID to load
        
    Returns:
        Place dictionary or None if not found
    """
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM places WHERE place_id = %s",
                    (place_id,)
                )
                row = cur.fetchone()
                if row:
                    return dict(row)
                return None
    except Exception as e:
        logger.error(f"Error loading place {place_id}: {e}")
        raise


def load_places(place_ids: List[str]) -> Dict[str, Dict]:
    """
    Load multiple places by place_ids.
    
    Args:
        place_ids: List of place IDs to load
        
    Returns:
        Dictionary keyed by place_id with place data
    """
    if not place_ids:
        return {}
    
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                # Use parameterized query with ANY for list
                cur.execute(
                    "SELECT * FROM places WHERE place_id = ANY(%s)",
                    (place_ids,)
                )
                rows = cur.fetchall()
                result = {}
                for row in rows:
                    place_dict = dict(row)
                    place_id = place_dict.get("place_id")
                    if place_id:
                        result[place_id] = place_dict
                return result
    except Exception as e:
        logger.error(f"Error loading places: {e}")
        raise


def load_all_places() -> Dict[str, Dict]:
    """
    Load all places from database.
    
    Note: This loads all places into memory. Use with caution for large datasets.
    Prefer load_places() for specific place_ids.
    
    Returns:
        Dictionary keyed by place_id with all place data
    """
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT * FROM places")
                rows = cur.fetchall()
                result = {}
                for row in rows:
                    place_dict = dict(row)
                    place_id = place_dict.get("place_id")
                    if place_id:
                        result[place_id] = place_dict
                logger.info(f"Loaded {len(result)} places from database")
                return result
    except Exception as e:
        logger.error(f"Error loading all places: {e}")
        raise


def upsert_place(place: Dict) -> None:
    """
    Upsert a single place (insert if new, update if exists).
    
    Uses database transaction with row-level locking for concurrency control.
    
    Args:
        place: Place dictionary (must have "place_id" key)
    """
    
    place_id = place.get("place_id")
    if not place_id:
        raise ValueError("place must have 'place_id' key")
    
    logger.debug(f"[upsert_place] Upserting place: {place_id}")
    
    try:
        with db_transaction() as conn:
            with conn.cursor() as cur:
                # Use SELECT FOR UPDATE to lock row if it exists
                cur.execute(
                    "SELECT place_id FROM places WHERE place_id = %s FOR UPDATE",
                    (place_id,)
                )
                exists = cur.fetchone() is not None
                
                # Prepare data for upsert
                nearby_search_flag = place.get("nearby_search_flag", False)
                places_details_flag = place.get("places_details_flag", False)
                tavily_flag = place.get("tavily_flag", False)
                enriched_flag = place.get("enriched_flag", False)
                place_jsonb = json.dumps(place.get("place", {}))
                sources_jsonb = json.dumps(place.get("sources", {}))
                derived_jsonb = json.dumps(place.get("derived", {}))
                
                if exists:
                    # Update existing place
                    cur.execute(
                        """
                        UPDATE places 
                        SET nearby_search_flag = %s,
                            places_details_flag = %s,
                            tavily_flag = %s,
                            enriched_flag = %s,
                            place = %s::jsonb,
                            sources = %s::jsonb,
                            derived = %s::jsonb
                        WHERE place_id = %s
                        """,
                        (
                            nearby_search_flag,
                            places_details_flag,
                            tavily_flag,
                            enriched_flag,
                            place_jsonb,
                            sources_jsonb,
                            derived_jsonb,
                            place_id,
                        )
                    )
                    logger.debug(f"[upsert_place] Updated existing place: {place_id}")
                else:
                    # Insert new place
                    cur.execute(
                        """
                        INSERT INTO places (
                            place_id, nearby_search_flag, places_details_flag,
                            tavily_flag, enriched_flag, place, sources, derived
                        ) VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb)
                        """,
                        (
                            place_id,
                            nearby_search_flag,
                            places_details_flag,
                            tavily_flag,
                            enriched_flag,
                            place_jsonb,
                            sources_jsonb,
                            derived_jsonb,
                        )
                    )
                    logger.debug(f"[upsert_place] Inserted new place: {place_id}")
    except Exception as e:
        logger.error(f"[upsert_place] Failed to upsert {place_id}: {e}")
        raise


def upsert_place_ids(place_ids: List[str]) -> List[str]:
    """
    Upsert multiple place_ids, creating minimal entries for new ones.
    
    Uses database transaction for atomic operation.
    
    Args:
        place_ids: List of place_ids to upsert
        
    Returns:
        List of place_ids that were newly created (not already in database)
    """
    
    logger.info(f"[upsert_place_ids] Starting upsert for {len(place_ids)} place_ids")
    
    if not place_ids:
        return []
    
    try:
        with db_transaction() as conn:
            with conn.cursor() as cur:
                # Check which place_ids already exist
                cur.execute(
                    "SELECT place_id FROM places WHERE place_id = ANY(%s)",
                    (place_ids,)
                )
                existing_place_ids = {row[0] for row in cur.fetchall()}
                
                new_place_ids = []
                for place_id in place_ids:
                    if place_id not in existing_place_ids:
                        # Create minimal entry
                        cur.execute(
                            """
                            INSERT INTO places (
                                place_id, nearby_search_flag, places_details_flag,
                                tavily_flag, enriched_flag, place, sources, derived
                            ) VALUES (%s, FALSE, FALSE, FALSE, FALSE, '{}'::jsonb, '{}'::jsonb, '{}'::jsonb)
                            ON CONFLICT (place_id) DO NOTHING
                            """,
                            (place_id,)
                        )
                        new_place_ids.append(place_id)
                        logger.debug(f"[upsert_place_ids] Created new entry for: {place_id}")
                
                logger.info(
                    f"[upsert_place_ids] Created {len(new_place_ids)} new entries, "
                    f"{len(place_ids) - len(new_place_ids)} already existed"
                )
                return new_place_ids
    except Exception as e:
        logger.error(f"[upsert_place_ids] Failed to upsert place_ids: {e}")
        raise


def save_place(place: Dict) -> None:
    """
    Save/update a single place (alias for upsert_place).
    
    Args:
        place: Place dictionary (must have "place_id" key)
    """
    upsert_place(place)


def reset_enrichment_flag(
    place_ids: Optional[List[str]] = None,
    clear_enrichment_data: bool = False
) -> int:
    """
    Reset enriched_flag to False for specified places (or all places).
    
    Args:
        place_ids: Optional list of place_ids to reset. If None, resets all places.
        clear_enrichment_data: If True, also clears tavily data and derived attributes.
        
    Returns:
        Number of places that were reset
    """
    
    try:
        with db_transaction() as conn:
            with conn.cursor() as cur:
                if place_ids is None:
                    # Reset all places
                    if clear_enrichment_data:
                        cur.execute(
                            """
                            UPDATE places 
                            SET enriched_flag = FALSE,
                                tavily_flag = FALSE,
                                sources = jsonb_set(sources, '{tavily}', '{}'::jsonb),
                                derived = '{}'::jsonb
                            WHERE enriched_flag = TRUE
                            """
                        )
                    else:
                        cur.execute(
                            "UPDATE places SET enriched_flag = FALSE WHERE enriched_flag = TRUE"
                        )
                    reset_count = cur.rowcount
                    logger.info(f"[reset_enrichment_flag] Reset {reset_count} places")
                else:
                    # Reset specific places
                    if clear_enrichment_data:
                        cur.execute(
                            """
                            UPDATE places 
                            SET enriched_flag = FALSE,
                                tavily_flag = FALSE,
                                sources = jsonb_set(sources, '{tavily}', '{}'::jsonb),
                                derived = '{}'::jsonb
                            WHERE place_id = ANY(%s) AND enriched_flag = TRUE
                            """,
                            (place_ids,)
                        )
                    else:
                        cur.execute(
                            """
                            UPDATE places 
                            SET enriched_flag = FALSE 
                            WHERE place_id = ANY(%s) AND enriched_flag = TRUE
                            """,
                            (place_ids,)
                        )
                    reset_count = cur.rowcount
                    logger.info(f"[reset_enrichment_flag] Reset {reset_count} places")
                
                return reset_count
    except Exception as e:
        logger.error(f"[reset_enrichment_flag] Failed to reset enrichment flag: {e}")
        raise

