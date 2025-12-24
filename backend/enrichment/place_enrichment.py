"""
Place enrichment functions for sync (place_details) and async (Tavily + LLM) operations.
"""

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import os

from langchain_openai import ChatOpenAI
from langchain_tavily import TavilySearch
from pydantic import BaseModel, Field

try:
    from tavily import TavilyClient
    TAVILY_CLIENT_AVAILABLE = True
except ImportError:
    TAVILY_CLIENT_AVAILABLE = False
    TavilyClient = None

from backend.enrichment.types import Config
from backend.enrichment.google_places import place_details, process_photos

logger = logging.getLogger(__name__)


# =============================================================================
# Data models for derived attributes
# =============================================================================

class DerivedAttribute(BaseModel):
    """Single derived attribute with value, confidence, sources, and evidence."""
    value: Any
    confidence: float = Field(ge=0.0, le=1.0)
    sources: List[str] = Field(default_factory=list)
    evidence: List[str] = Field(default_factory=list)


class DerivedAttributes(BaseModel):
    """All derived attributes matching schema."""
    has_wifi: DerivedAttribute
    has_outlets: DerivedAttribute
    is_laptop_friendly: DerivedAttribute
    noise_level: DerivedAttribute
    seating_availability: DerivedAttribute
    seating_comfort: DerivedAttribute
    notable_positives: DerivedAttribute
    common_complaints: DerivedAttribute


# =============================================================================
# Sync Enrichment: Place Details
# =============================================================================

def enrich_place_details_sync(cfg: Config, place_id: str, existing_place: Dict, nearby_result: Optional[Dict] = None) -> Dict:
    """
    Sync enrichment: Fetch place details and populate binary attributes.
    
    Args:
        cfg: Config object
        place_id: Place ID to enrich
        existing_place: Existing place entry from JSON
        nearby_result: Optional nearby_search result to extract binary attributes from
        
    Returns:
        Updated place dictionary
    """
    from backend.enrichment.process_lock import place_processing_lock, AlreadyProcessingError, TooManyErrorsError
    
    logger.debug(f"[enrich_place_details_sync] Starting enrichment for: {place_id}")
    
    places_details_flag = existing_place.get("places_details_flag", False)
    logger.debug(f"[enrich_place_details_sync] places_details_flag: {places_details_flag}")
    
    if places_details_flag:
        logger.info(f"[enrich_place_details_sync] Place {place_id} already has details, skipping")
        return existing_place
    
    # Use process lock to prevent duplicate processing
    try:
        with place_processing_lock(place_id, "place_details_sync"):
            # Double-check flag after acquiring lock (another process might have enriched it)
            if existing_place.get("places_details_flag", False):
                logger.info(f"[enrich_place_details_sync] Place {place_id} already enriched by another process, skipping")
                return existing_place
            
            logger.info(f"[enrich_place_details_sync] Fetching place details for {place_id}")
            
            # Fetch place details with binary attributes
            try:
                details = place_details(cfg, place_id)
                logger.debug(f"[enrich_place_details_sync] Successfully fetched details for {place_id}")
            except Exception as e:
                logger.error(f"[enrich_place_details_sync] Error fetching details for {place_id}: {e}")
                raise
    except AlreadyProcessingError:
        logger.warning(f"[enrich_place_details_sync] Place {place_id} is already being processed, skipping")
        return existing_place
    except TooManyErrorsError as e:
        logger.error(f"[enrich_place_details_sync] {e}, skipping")
        return existing_place
    
    # Extract binary attributes from nearby_search result (preferred) or place_details (fallback)
    # These fields come from nearby_search, not place_details
    print(f"\nDEBUG: [enrich_place_details_sync] {'='*60}")
    print(f"DEBUG: [enrich_place_details_sync] Extracting binary attributes for {place_id}")
    print(f"DEBUG: [enrich_place_details_sync] {'='*60}")
    
    if nearby_result:
        logger.debug(f"[enrich_place_details_sync] Extracting binary attributes from nearby_search result")
        print(f"DEBUG: [enrich_place_details_sync] ✓ Using nearby_search result")
        print(f"DEBUG: [enrich_place_details_sync] Nearby result keys: {list(nearby_result.keys())}")
        
        # Check each binary attribute individually
        print(f"\nDEBUG: [enrich_place_details_sync] Checking binary attributes in nearby_search:")
        binary_attrs = {}
        attr_checks = [
            ("restroom", nearby_result.get("restroom")),
            ("servesCoffee", nearby_result.get("servesCoffee")),
            ("outdoorSeating", nearby_result.get("outdoorSeating")),
            ("goodForGroups", nearby_result.get("goodForGroups")),
            ("accessibilityOptions", nearby_result.get("accessibilityOptions")),
            ("parkingOptions", nearby_result.get("parkingOptions")),
        ]
        
        for attr_name, raw_value in attr_checks:
            if raw_value is not None:
                binary_attrs[attr_name] = raw_value
                print(f"  ✓ {attr_name}: {raw_value} (type: {type(raw_value).__name__})")
            else:
                binary_attrs[attr_name] = None
                print(f"  ✗ {attr_name}: NOT FOUND")
        
        # Special handling for ServesCoffee
        serves_coffee = _extract_serves_coffee(nearby_result)
        binary_attrs["ServesCoffee"] = serves_coffee
        print(f"  → ServesCoffee (extracted): {serves_coffee}")
        
        logger.debug(f"[enrich_place_details_sync] Binary attrs from nearby_search: {binary_attrs}")
        print(f"\nDEBUG: [enrich_place_details_sync] Final binary_attrs dict: {binary_attrs}")
    else:
        # Fallback: try to get from place_details (may not be available)
        logger.debug(f"[enrich_place_details_sync] No nearby_search result, trying place_details for binary attrs")
        print(f"DEBUG: [enrich_place_details_sync] ✗ No nearby_search result, using place_details as fallback")
        print(f"DEBUG: [enrich_place_details_sync] Details keys: {list(details.keys())}")
        
        binary_attrs = {}
        attr_checks = [
            ("restroom", details.get("restroom")),
            ("servesCoffee", details.get("servesCoffee")),
            ("outdoorSeating", details.get("outdoorSeating")),
            ("goodForGroups", details.get("goodForGroups")),
            ("accessibilityOptions", details.get("accessibilityOptions")),
            ("parkingOptions", details.get("parkingOptions")),
        ]
        
        print(f"\nDEBUG: [enrich_place_details_sync] Checking binary attributes in place_details:")
        for attr_name, raw_value in attr_checks:
            if raw_value is not None:
                binary_attrs[attr_name] = raw_value
                print(f"  ✓ {attr_name}: {raw_value}")
            else:
                binary_attrs[attr_name] = None
                print(f"  ✗ {attr_name}: NOT FOUND")
        
        # Special handling for ServesCoffee
        serves_coffee = _extract_serves_coffee(details)
        binary_attrs["ServesCoffee"] = serves_coffee
        print(f"  → ServesCoffee (extracted): {serves_coffee}")
        
        print(f"\nDEBUG: [enrich_place_details_sync] Final binary_attrs dict: {binary_attrs}")
    
    print(f"DEBUG: [enrich_place_details_sync] {'='*60}\n")
    
    # Extract neighborhood from address or geometry
    neighborhood = _extract_neighborhood(details)
    
    # Process photos (prefer interior, limit to 2-5)
    photos = details.get("photos", [])
    processed_photos = process_photos(photos, cfg.api_key, max_photos=5)
    
    # Build place object (extract from new API format)
    # New API uses: location (with latitude/longitude), displayName (object with text), formattedAddress, etc.
    location_obj = details.get("location", {})
    display_name_obj = details.get("displayName", {})
    display_name_text = display_name_obj.get("text", "") if isinstance(display_name_obj, dict) else str(display_name_obj) if display_name_obj else ""
    
    place_obj = {
        "name": display_name_text,
        "lat": location_obj.get("latitude"),
        "lng": location_obj.get("longitude"),
        "types": details.get("types", []),
        "formatted_address": details.get("formattedAddress", ""),
        "neighborhood": neighborhood,
        "website": details.get("websiteUri"),
        "rating": details.get("rating"),
        "user_ratings_total": details.get("userRatingCount"),
        "price_level": details.get("priceLevel"),
        "business_status": details.get("businessStatus"),
        "opening_hours": details.get("regularOpeningHours"),
        "photos": processed_photos,  # Add processed photos
        **binary_attrs,
    }
    
    # Update existing place
    fetched_at = datetime.now(timezone.utc).isoformat()
    logger.debug(f"[enrich_place_details_sync] Updating place object for {place_id}")
    print(f"DEBUG: [enrich_place_details_sync] Updating place object for {place_id}")
    print(f"DEBUG: [enrich_place_details_sync] Place name: {place_obj.get('name')}")
    print(f"DEBUG: [enrich_place_details_sync] Place location: ({place_obj.get('lat')}, {place_obj.get('lng')})")
    
    existing_place["place"] = place_obj
    existing_place["places_details_flag"] = True
    existing_place["places_details_called_at"] = fetched_at
    existing_place["places_details_called_version"] = "google_places_v0.1"
    
    # Save sources
    if "sources" not in existing_place:
        existing_place["sources"] = {}
    
    reviews_count = len(details.get("reviews", []))
    logger.debug(f"[enrich_place_details_sync] Saving {reviews_count} reviews")
    print(f"DEBUG: [enrich_place_details_sync] Saving {reviews_count} reviews")
    
    existing_place["sources"]["google_details"] = {
        "fetched_at": fetched_at,
        "payload": details,
    }
    
    existing_place["sources"]["google_reviews"] = {
        "fetched_at": fetched_at,
        "reviews": details.get("reviews", []),
    }
    
    logger.info(f"[enrich_place_details_sync] Completed enrichment for {place_id}")
    print(f"DEBUG: [enrich_place_details_sync] ✓ Completed enrichment for {place_id}")
    
    return existing_place


def _extract_serves_coffee(details: Dict) -> Optional[bool]:
    """Extract ServesCoffee from API field or types array."""
    serves_coffee = details.get("servesCoffee")
    if serves_coffee is not None:
        return serves_coffee
    
    # Check types array for coffee-related types
    types = details.get("types", [])
    coffee_types = ["cafe", "coffee_shop", "bakery"]
    if any(t in types for t in coffee_types):
        return True
    
    return None


def _clean_tavily_snippet(snippet: str) -> str:
    """
    Clean Tavily snippet to remove noise like phone numbers, hours, addresses, etc.
    Keeps only content relevant to WFH attributes (reviews, descriptions, etc.)
    """
    if not snippet:
        return ""
    
    text = snippet
    
    # Remove full street addresses (but keep city/state for location verification)
    # Pattern: "123 Main St" or "857 9th Ave" - remove street number and name
    # But preserve city, state context later in the snippet
    text = re.sub(r'\d+\s+[A-Za-z0-9\s]+(?:Ave|St|Street|Road|Rd|Blvd|Boulevard|Lane|Ln|Drive|Dr|Court|Ct|Plaza|Pl|Avenue)\b[^,]*,', '', text, flags=re.IGNORECASE)
    
    # Remove navigation/action links (Website, Call, Map, Review, About, Directions, etc.)
    text = re.sub(r'\b(Website|Call|Map|Review|About|Directions|Share|Save|Follow)\b[.\s]*', '', text, flags=re.IGNORECASE)
    
    # Remove placeholder/empty content messages
    text = re.sub(r'There is no content for .*? yet', '', text, flags=re.IGNORECASE)
    text = re.sub(r'Be one of the first to write a review', '', text, flags=re.IGNORECASE)
    text = re.sub(r'No reviews? yet', '', text, flags=re.IGNORECASE)
    
    # Remove phone numbers (various formats)
    text = re.sub(r'\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}', '', text)
    text = re.sub(r'\+\d{1,3}[-.\s]?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}', '', text)
    
    # Remove business hours patterns (handle "Closed7:00" attached format)
    text = re.sub(r'Closed\s*\d{1,2}:\d{2}', '', text, flags=re.IGNORECASE)  # Remove "Closed7:00" or "Closed 7:00"
    text = re.sub(r'\d{1,2}:\d{2}\s*(AM|PM|am|pm)\s*-\s*\d{1,2}:\d{2}\s*(AM|PM|am|pm)', '', text)
    text = re.sub(r'\|\s*(Mon|Tue|Wed|Thu|Fri|Sat|Sun|Today|Tomorrow)\s*\|?\s*\*?\s*\d{1,2}:\d{2}', '', text, flags=re.IGNORECASE)
    text = re.sub(r'(Mon|Tue|Wed|Thu|Fri|Sat|Sun|Today|Tomorrow)[^|]*\|', '', text, flags=re.IGNORECASE)
    text = re.sub(r'Business hours may be different today', '', text, flags=re.IGNORECASE)
    text = re.sub(r'Next day', '', text, flags=re.IGNORECASE)
    
    # Remove health score references
    text = re.sub(r'Check\s+\w+\s+Health\s+Score', '', text, flags=re.IGNORECASE)
    text = re.sub(r'NY Health Score', '', text, flags=re.IGNORECASE)
    
    # Remove common metadata phrases
    text = re.sub(r'Do you recommend this business\?', '', text, flags=re.IGNORECASE)
    text = re.sub(r'Pickup\s*\.\.\.', '', text, flags=re.IGNORECASE)
    text = re.sub(r'Hours\.', '', text, flags=re.IGNORECASE)
    
    # Remove Terms of Service / Privacy Policy mentions
    text = re.sub(r'We recently updated our Terms of Service.*?Policy\.', '', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'Terms of Service.*?Privacy Policy', '', text, flags=re.IGNORECASE)
    
    # Remove section headers and markdown-style headers
    text = re.sub(r'#{1,6}\s+[^\n]+', '', text)  # Remove ## and ### headers
    text = re.sub(r'##\s+', '', text)  # Remove remaining ##
    text = re.sub(r'###\s+', '', text)  # Remove remaining ###
    
    # Remove common Yelp/restaurant site sections
    text = re.sub(r"Popular Dishes\.[^#]*", '', text, flags=re.IGNORECASE)
    text = re.sub(r"What's the vibe\?.*?(?=##|$)", '', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"People also searched for\.[^#]*", '', text, flags=re.IGNORECASE)
    text = re.sub(r"Location & Hours\.[^#]*", '', text, flags=re.IGNORECASE)
    
    # Remove "Closed now" status indicators (separate from hours pattern)
    text = re.sub(r'Closed\s+now', '', text, flags=re.IGNORECASE)
    
    # Remove standalone ZIP codes (keep city/state but remove ZIP)
    text = re.sub(r'\b\d{5}(-\d{4})?\b', '', text)
    
    # Keep city, state for location verification, but clean up format
    # Convert "City, State ZIP" to "City, State" (ZIP already removed above)
    # We'll keep this as it helps verify the correct location
    
    # Remove multiple consecutive spaces/punctuation
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'[.\s]{3,}', '. ', text)
    
    # Remove leading/trailing punctuation and whitespace
    text = text.strip(' .,;:')
    
    # If the snippet is now too short or empty after cleaning, return empty
    if len(text.strip()) < 10:
        return ""
    
    return text


def _derive_open_after_7pm(opening_hours: Optional[Dict]) -> Dict:
    """
    Derive "open_after_7pm" attribute from place's opening hours.
    
    Args:
        opening_hours: regularOpeningHours dict from Google Places API, or None
        
    Returns:
        Dict with value ("yes", "no", "unknown"), confidence, sources, evidence
    """
    if not opening_hours:
        return {
            "value": "unknown",
            "confidence": 0.0,
            "sources": [],
            "evidence": [],
        }
    
    periods = opening_hours.get("periods", [])
    if not periods:
        return {
            "value": "unknown",
            "confidence": 0.0,
            "sources": [],
            "evidence": [],
        }
    
    # Check if any period indicates the place is open after 7PM (19:00)
    # A place is "open after 7PM" if:
    # 1. It closes at 19:00 (7PM) or later on any day
    # 2. It spans midnight (closes next day), which means it's open late
    # 3. It opens after 19:00 (late opening)
    
    open_after_7pm = False
    evidence_parts = []
    
    for period in periods:
        open_info = period.get("open", {})
        close_info = period.get("close", {})
        
        if not open_info or not close_info:
            continue
        
        open_day = open_info.get("day", 0)
        open_hour = open_info.get("hour", 0)
        open_minute = open_info.get("minute", 0)
        
        close_day = close_info.get("day", 0)
        close_hour = close_info.get("hour", 0)
        close_minute = close_info.get("minute", 0)
        
        # Convert to minutes for easier comparison
        open_time = open_hour * 60 + open_minute
        close_time = close_hour * 60 + close_minute
        
        # Case 1: Spans midnight (close_day > open_day, or close_day == (open_day + 1) % 7)
        spans_midnight = (
            close_day > open_day or 
            (close_day == (open_day + 1) % 7) or
            (close_day == 0 and open_day == 6)  # Saturday to Sunday
        )
        
        if spans_midnight:
            open_after_7pm = True
            day_names = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
            open_day_name = day_names[open_day] if 0 <= open_day < 7 else f"Day {open_day}"
            evidence_parts.append(f"Open {open_day_name} until next day ({close_hour:02d}:{close_minute:02d})")
        
        # Case 2: Closes at 7PM (19:00) or later on same day
        elif close_day == open_day and close_time >= 19 * 60:  # 19:00 = 1140 minutes
            open_after_7pm = True
            day_names = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
            day_name = day_names[open_day] if 0 <= open_day < 7 else f"Day {open_day}"
            evidence_parts.append(f"Open until {close_hour:02d}:{close_minute:02d} on {day_name}")
        
        # Case 3: Opens after 7PM (late opening)
        elif open_time >= 19 * 60:  # Opens at 7PM or later
            open_after_7pm = True
            day_names = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
            day_name = day_names[open_day] if 0 <= open_day < 7 else f"Day {open_day}"
            evidence_parts.append(f"Opens at {open_hour:02d}:{open_minute:02d} on {day_name}")
    
    if open_after_7pm:
        return {
            "value": "yes",
            "confidence": 1.0,  # High confidence - comes from authoritative Google data
            "sources": ["google_places_opening_hours"],
            "evidence": evidence_parts[:3],  # Limit to 3 examples
        }
    else:
        # Check if we have complete data (all 7 days covered) vs partial data
        days_covered = set()
        for period in periods:
            if period.get("open") and period.get("close"):
                days_covered.add(period["open"].get("day"))
        
        # If we have data for most days and none are open after 7PM, it's probably "no"
        if len(days_covered) >= 5:  # 5+ days of data
            return {
                "value": "no",
                "confidence": 0.9,  # High confidence if we have most days
                "sources": ["google_places_opening_hours"],
                "evidence": ["No opening hours extend past 7PM"],
            }
        else:
            return {
                "value": "unknown",
                "confidence": 0.3,  # Low confidence if we have incomplete data
                "sources": ["google_places_opening_hours"],
                "evidence": ["Incomplete opening hours data"],
            }


def _extract_neighborhood(details: Dict) -> Optional[str]:
    """Extract neighborhood from address components or geometry."""
    # Try to extract from formattedAddress (new API field name)
    address = details.get("formattedAddress", "") or details.get("formatted_address", "")
    # This is a simple implementation - could be enhanced with address components
    # For now, return None if not easily extractable
    return None


# =============================================================================
# Async Enrichment: Tavily + LLM
# =============================================================================

def enrich_place_web_async(cfg: Config, place: Dict, existing_place: Dict) -> Dict:
    """
    Async enrichment: Run Tavily search and derive attributes using LLM.
    
    Args:
        cfg: Config object
        place: Place dictionary with name, address, etc.
        existing_place: Existing place entry from JSON
        
    Returns:
        Updated place dictionary
    """
    from backend.enrichment.process_lock import place_processing_lock, AlreadyProcessingError, TooManyErrorsError
    
    place_id = existing_place.get("place_id")
    
    if existing_place.get("enriched_flag", False):
        logger.info(f"Place {place_id} already enriched, skipping")
        return existing_place
    
    # Use process lock to prevent duplicate processing
    try:
        with place_processing_lock(place_id, "web_async_enrichment"):
            # Double-check flag after acquiring lock (another process might have enriched it)
            if existing_place.get("enriched_flag", False):
                logger.info(f"Place {place_id} already enriched by another process, skipping")
                return existing_place
            
            logger.info(f"Starting async enrichment for {place_id}")
            
            # Step 1: Run Tavily web search (only if not already done)
            # Check if Tavily data already exists to avoid duplicate API calls
            existing_tavily = existing_place.get("sources", {}).get("tavily")
            has_existing_tavily = existing_tavily and existing_tavily.get("results") and len(existing_tavily.get("results", [])) > 0
            
            if has_existing_tavily:
                logger.info(f"Place {place_id} already has Tavily data ({len(existing_tavily.get('results', []))} results), reusing it to avoid API call")
                tavily_data = {
                    "query": existing_tavily.get("query", ""),
                    "queries": existing_tavily.get("queries", [existing_tavily.get("query", "")]),
                    "results": existing_tavily.get("results", []),
                    "excerpts": existing_tavily.get("excerpts", []),
                }
            else:
                logger.info(f"Place {place_id} does not have Tavily data, running Tavily search")
                # Run Tavily search - this may return empty results if API fails
                tavily_data = _run_tavily_search(place)
                
                # Check if we got successful results (non-empty)
                has_new_results = bool(tavily_data.get("results") and len(tavily_data.get("results", [])) > 0)
                
                if not has_new_results:
                    # API call failed or returned empty results
                    if has_existing_tavily:
                        # We have existing data - preserve it, don't overwrite with empty
                        logger.warning(f"Place {place_id} Tavily search failed/returned empty, preserving existing Tavily data ({len(existing_tavily.get('results', []))} results)")
                        tavily_data = {
                            "query": existing_tavily.get("query", ""),
                            "queries": existing_tavily.get("queries", [existing_tavily.get("query", "")]),
                            "results": existing_tavily.get("results", []),
                            "excerpts": existing_tavily.get("excerpts", []),
                        }
                    else:
                        # No existing data and API failed - this is first time, save empty (but don't set tavily_flag)
                        logger.warning(f"Place {place_id} Tavily search failed/returned empty, no existing data to preserve")
            
            # Save Tavily content to sources ONLY if we have successful results
            # Never overwrite existing data with empty/null results
            fetched_at = datetime.now(timezone.utc).isoformat()
            if "sources" not in existing_place:
                existing_place["sources"] = {}
            
            has_tavily_results = bool(tavily_data.get("results") and len(tavily_data.get("results", [])) > 0)
            
            if has_tavily_results:
                # We have successful results - overwrite existing data (or create new)
                existing_place["sources"]["tavily"] = {
                    "fetched_at": fetched_at,
                    "query": tavily_data["query"],  # Primary query
                    "queries": tavily_data.get("queries", [tavily_data["query"]]),  # All queries used
                    "results": tavily_data["results"],
                    "excerpts": tavily_data.get("excerpts", []),
                }
                logger.info(f"Place {place_id} successfully updated Tavily data with {len(tavily_data.get('results', []))} results")
            elif has_existing_tavily:
                # API failed but we have existing data - preserve it, just update timestamp
                logger.info(f"Place {place_id} preserving existing Tavily data after failed search attempt")
                existing_place["sources"]["tavily"]["last_attempt_at"] = fetched_at
            else:
                # No results and no existing data - save empty structure (first time, API failed)
                # This allows us to track that we tried but don't set tavily_flag
                existing_place["sources"]["tavily"] = {
                    "fetched_at": fetched_at,
                    "query": tavily_data.get("query", ""),
                    "queries": tavily_data.get("queries", []),
                    "results": [],
                    "excerpts": [],
                    "failed": True,  # Mark as failed so we know it's not just empty
                }
                logger.warning(f"Place {place_id} Tavily search failed, saved empty structure (no existing data to preserve)")
            
            # Set tavily_flag based on whether we have Tavily results in the saved data
            # Check the actual saved data, not just tavily_data (which might be preserved existing data)
            saved_tavily = existing_place.get("sources", {}).get("tavily", {})
            has_tavily_results = bool(saved_tavily.get("results") and len(saved_tavily.get("results", [])) > 0)
            existing_place["tavily_flag"] = has_tavily_results
            if has_tavily_results:
                logger.info(f"Place {place_id} has Tavily data ({len(saved_tavily.get('results', []))} results), tavily_flag set to True")
            else:
                logger.info(f"Place {place_id} has no Tavily data, tavily_flag set to False")
            
            # Step 2: Derive attributes using LLM (combines Google reviews + Tavily)
            # Use the saved Tavily data (which may be preserved existing data if API failed)
            google_reviews = existing_place.get("sources", {}).get("google_reviews", {}).get("reviews", [])
            saved_tavily = existing_place.get("sources", {}).get("tavily", {})
            tavily_results = saved_tavily.get("results", [])
            tavily_excerpts = saved_tavily.get("excerpts", [])
            
            derived_attrs = derive_attributes_from_evidence(
                place=place,
                google_reviews=google_reviews,
                tavily_results=tavily_results,
                tavily_excerpts=tavily_excerpts,
            )
            
            # Add "open_after_7pm" attribute derived from place details (not from evidence)
            opening_hours = place.get("opening_hours")
            open_after_7pm = _derive_open_after_7pm(opening_hours)
            derived_attrs["open_after_7pm"] = open_after_7pm
            
            # Update existing place
            existing_place["derived"] = derived_attrs
            
            # enriched_flag should only be True if derived attributes were created AND Tavily data exists
            # This ensures we only mark as "enriched" when we have Tavily evidence
            if has_tavily_results:
                existing_place["enriched_flag"] = True
                existing_place["enriched_at"] = fetched_at
                existing_place["enriched_version"] = "signals_v0.1"
                logger.info(f"Place {place_id} enriched with Tavily data, enriched_flag set to True")
            else:
                existing_place["enriched_flag"] = False
                logger.warning(f"Place {place_id} derived attributes created but no Tavily data, enriched_flag set to False")
            
            # Ensure place_id is set (it should already be there, but make sure)
            if "place_id" not in existing_place and place_id:
                existing_place["place_id"] = place_id
            
            logger.info(f"Async enrichment completed for {place_id}, enriched_flag set to True")
            return existing_place
    except AlreadyProcessingError:
        logger.warning(f"Place {place_id} is already being processed, skipping")
        return existing_place
    except TooManyErrorsError as e:
        logger.error(f"{e}, skipping")
        return existing_place


def _generate_tavily_queries(place: Dict) -> List[str]:
    """
    Use LLM to generate optimized Tavily search queries for a place.
    Returns 2-3 query variations that are likely to find WFH-relevant information.
    """
    name = place.get("name", "Unknown")
    address = place.get("formatted_address") or place.get("address", "")
    neighborhood = place.get("neighborhood", "")
    
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.7)
    
    prompt = f"""Generate 2-3 optimized web search queries for finding information about whether "{name}" 
at {neighborhood or address} is good for remote work (working from a laptop).

Focus on finding:
- WiFi quality and availability
- Power outlet availability
- Laptop-friendly environment
- Seating comfort and availability
- Noise levels
- Reviews mentioning working from this location

Generate queries that are likely to find:
- Yelp reviews
- Reddit discussions
- Blog posts
- Review sites
- Social media mentions

Return ONLY a JSON array of query strings, no other text. Example:
["Is {name} good for working laptop wifi", "{name} {address} laptop friendly wifi outlets", "{name} coffee shop remote work review"]

Place name: {name}
Address: {neighborhood or address}
"""
    
    try:
        response = llm.invoke(prompt)
        content = response.content if hasattr(response, 'content') else str(response)
        
        # Parse JSON array
        import json
        queries = json.loads(content.strip())
        if isinstance(queries, list) and all(isinstance(q, str) for q in queries):
            return queries[:3]  # Limit to 3 queries
    except Exception as e:
        logger.warning(f"Failed to generate queries with LLM: {e}, using fallback")
    
    # Fallback to template-based queries
    base_location = neighborhood or address
    return [
        f"Is {name} in {base_location} good for working laptop wifi outlets",
        f"{name} {base_location} laptop friendly wifi review",
        f"{name} coffee shop remote work laptop"
    ]


def _run_tavily_search(place: Dict) -> Dict:
    """
    Run Tavily search for a place using the Tavily Python client directly.
    Uses LLM to generate optimized queries, then runs multiple searches and combines results.
    This matches the API playground behavior but with smarter query generation.
    
    Returns:
        Dictionary with query, results, and excerpts
    """
    name = place.get("name", "Unknown")
    address = place.get("formatted_address") or place.get("address", "")
    
    # Generate optimized queries using LLM
    queries = _generate_tavily_queries(place)
    primary_query = queries[0] if queries else f"Is {name} good for working laptop wifi outlets"
    
    logger.info(f"Generated {len(queries)} Tavily queries for {name}: {queries}")
    
    all_results = []
    seen_urls = set()
    
    try:
        tavily_api_key = os.getenv("TAVILY_API_KEY")
        if not tavily_api_key:
            logger.error("TAVILY_API_KEY environment variable not set")
            return {
                "query": primary_query,
                "queries": queries,
                "results": [],
                "excerpts": [],
            }
        
        # Use Tavily client directly if available (matches API playground)
        # Otherwise fall back to LangChain wrapper
        if TAVILY_CLIENT_AVAILABLE:
            client = TavilyClient(api_key=tavily_api_key)
            
            # Run each query and combine results (deduplicate by URL)
            for query in queries:
                try:
                    response = client.search(
                        query=query,
                        max_results=5,  # Fewer per query since we're running multiple
                        search_depth="basic",
                        include_answer=False,
                        include_raw_content=False,
                    )
                    
                    results_list = response.get("results", [])
                    for item in results_list:
                        if isinstance(item, dict):
                            url = item.get("url", "")
                            if url and url not in seen_urls:
                                seen_urls.add(url)
                                content = item.get("content", "")
                                # Clean the snippet to remove noise
                                cleaned_content = _clean_tavily_snippet(content)
                                all_results.append({
                                    "url": url,
                                    "title": item.get("title", ""),
                                    "snippet": cleaned_content[:500] if cleaned_content else "",
                                    "score": item.get("score", 0.0),
                                })
                except Exception as e:
                    logger.warning(f"Tavily search failed for query '{query}': {e}")
            
            tavily_results = all_results[:8]  # Limit total results
        else:
            # Fallback to LangChain wrapper - use primary query only
            logger.warning("Tavily client not available, using LangChain wrapper (may have issues)")
            tavily_search = TavilySearch(
                max_results=8,
                topic="general",
                include_answer=False,
                include_raw_content=False,
                search_depth="basic",
            )
            
            # Run search - LangChain wrapper returns list directly
            results = tavily_search.invoke(primary_query)
            
            # Handle different return formats from LangChain
            if isinstance(results, list):
                results_list = results
            elif isinstance(results, dict):
                results_list = results.get("results", [])
            else:
                results_list = []
            
            tavily_results = []
            for item in results_list:
                if isinstance(item, dict):
                    content = item.get("content", "")
                    # Clean the snippet to remove noise
                    cleaned_content = _clean_tavily_snippet(content)
                    tavily_results.append({
                        "url": item.get("url", ""),
                        "title": item.get("title", ""),
                        "snippet": cleaned_content[:500] if cleaned_content else "",
                        "score": item.get("score", 0.0),
                    })
        
        logger.info(f"Tavily search for {name} returned {len(tavily_results)} unique results from {len(queries)} queries")
        if not tavily_results:
            logger.warning(
                f"Tavily search returned empty results for all queries: {queries}"
            )
        
        # For excerpts, we'd need to call Tavily Extract API separately
        # For now, use snippets as excerpts
        excerpts = [
            {
                "url": r["url"],
                "text": r["snippet"],
            }
            for r in tavily_results
        ]
        
        return {
            "query": primary_query,  # Store primary query for reference
            "queries": queries,  # Store all queries used
            "results": tavily_results,
            "excerpts": excerpts,
        }
    except Exception as e:
        logger.error(f"Tavily search failed: {e}", exc_info=True)
        return {
            "query": primary_query,
            "queries": queries if 'queries' in locals() else [primary_query],
            "results": [],
            "excerpts": [],
        }


def derive_attributes_from_evidence(
    place: Dict,
    google_reviews: List[Dict],
    tavily_results: List[Dict],
    tavily_excerpts: List[Dict],
) -> Dict:
    """
    Unified LLM call that takes ALL evidence (Google reviews + Tavily) and derives attributes.
    
    Args:
        place: Place dict with name, address, etc.
        google_reviews: Full array of Google Maps reviews
        tavily_results: Tavily search results (url, title, snippet, score)
        tavily_excerpts: Tavily excerpts (url, text)
        
    Returns:
        Dictionary matching schema's derived section
    """
    name = place.get("name", "Unknown")
    address = place.get("formatted_address") or place.get("address", "")
    
    # Prepare evidence text
    reviews_text = "\n\n".join([
        f"Review {i+1} (Rating: {r.get('rating', 'N/A')}): {r.get('text', '')}"
        for i, r in enumerate(google_reviews[:20])  # Limit to 20 reviews
    ])
    
    tavily_text = "\n\n".join([
        f"Source: {r.get('url', '')}\nTitle: {r.get('title', '')}\nContent: {r.get('snippet', '')}"
        for r in tavily_results[:10]  # Limit to 10 results
    ])
    
    # Build prompt
    prompt = f"""You are analyzing evidence about a place to determine work-from-home (WFH) attributes.

Place: {name}
Address: {address}

GOOGLE MAPS REVIEWS:
{reviews_text if reviews_text else "No reviews available."}

WEB SEARCH RESULTS (Tavily):
{tavily_text if tavily_text else "No web search results available."}

Based on ALL the evidence above (both Google reviews AND web search results), determine the following attributes:

1. has_wifi: "free", "paid", "none", or "unknown" - ONLY use "free"/"paid"/"none" if evidence explicitly mentions WiFi/internet availability. Use "unknown" if no evidence.
2. has_outlets: "many", "few", "none", or "unknown" - ONLY use "many"/"few"/"none" if evidence explicitly mentions outlets, plugs, charging, power sockets. Use "unknown" if no evidence.
3. is_laptop_friendly: "yes", "mixed", or "no" - ONLY if evidence mentions working, studying, laptop use, remote work
4. noise_level: "quiet", "mixed", or "loud" - ONLY if evidence mentions noise, quiet, loud, peaceful, busy, music volume
5. seating_availability: "good", "mixed", or "limited" - ONLY if evidence mentions seating, tables, space availability
6. seating_comfort: "good", "mixed", or "bad" - ONLY if evidence mentions comfort, chairs, seating quality
7. notable_positives: List of positive aspects mentioned (max 5 items)
8. common_complaints: List of complaints or negative aspects mentioned (max 5 items)

CRITICAL RULES:
- Each attribute's evidence MUST directly relate to that attribute. Do NOT use evidence about noise for outlets, or evidence about seating for WiFi, etc.
- If NO evidence exists for an attribute, you MUST set: value to "none"/"unknown", confidence to 0.0, and sources/evidence to empty arrays []
- DO NOT guess or infer values without explicit evidence. If there's no evidence, use "unknown"/"none" with confidence 0.0
- Confidence should scale with number of sources: 1 source = 0.3-0.5, 2-3 sources = 0.5-0.7, 4+ sources = 0.7-0.9
- Confidence should also consider evidence quality: explicit mentions = higher confidence, indirect/implied = lower confidence
- If evidence contradicts or is mixed, use "mixed" value and moderate confidence (0.4-0.6)

For each attribute, provide:
- value: The attribute value (or "unknown" if no relevant evidence)
- confidence: Float 0.0-1.0 based on NUMBER of sources AND quality of evidence (see rules above)
- sources: Array of source identifiers (e.g., ["google_reviews", "tavily_https://example.com"])
- evidence: Array of specific evidence snippets THAT ACTUALLY RELATE TO THIS ATTRIBUTE (e.g., for outlets, only include quotes mentioning outlets/plugs/charging)

Return ONLY valid JSON matching this structure:
{{
  "has_wifi": {{"value": "free", "confidence": 0.7, "sources": ["google_reviews", "tavily_..."], "evidence": ["Review: 'Wi-Fi is available'"]}},
  "has_outlets": {{"value": "few", "confidence": 0.4, "sources": ["tavily_..."], "evidence": ["Review: 'Limited outlets for charging'"]}},
  "is_laptop_friendly": {{"value": "yes", "confidence": 0.6, "sources": [...], "evidence": ["Review: 'Good for working'"]}},
  "noise_level": {{"value": "mixed", "confidence": 0.5, "sources": [...], "evidence": ["Review: 'Can be loud during peak hours'"]}},
  "seating_availability": {{"value": "limited", "confidence": 0.6, "sources": [...], "evidence": ["Review: 'Few tables available'"]}},
  "seating_comfort": {{"value": "good", "confidence": 0.4, "sources": [...], "evidence": ["Review: 'Comfortable chairs'"]}},
  "notable_positives": {{"value": ["Great coffee", "Friendly staff"], "sources": [...], "evidence": ["Review: '...'"]}},
  "common_complaints": {{"value": ["Limited seating"], "sources": [...], "evidence": ["Review: '...'"]}}
}}

IMPORTANT: Each evidence snippet must directly support its attribute. Double-check before including evidence.
"""
    
    try:
        llm = ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0,
        )
        
        response = llm.invoke(prompt)
        content = response.content if hasattr(response, 'content') else str(response)
        
        # Parse JSON response
        # Strip markdown code fences if present
        content = content.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()
        
        parsed = json.loads(content)
        
        # Validate and structure response
        derived = {}
        
        # Define keywords that must appear in evidence for each attribute
        # Includes synonyms and related terms to avoid false negatives
        attribute_keywords = {
            "has_wifi": ["wifi", "wi-fi", "wireless", "internet", "connection", "network", "signal", "online", "connectivity"],
            "has_outlets": ["outlet", "outlets", "plug", "plugs", "socket", "sockets", "charging", "power", "electric", "usb", "charge", "charger"],
            "is_laptop_friendly": ["laptop", "work", "working", "study", "studying", "remote", "wfh", "computer", "desk", "workplace", "workspace"],
            "noise_level": ["noise", "noisy", "quiet", "quietly", "loud", "peaceful", "calm", "busy", "crowded", "music", "sound", "volume", "silent", "hushed"],
            "seating_availability": [
                "seating", "seats", "seat", "table", "tables", "chair", "chairs", "sit", "space", "room", "available", 
                "taken", "occupied", "empty", "full", "vacant", "free", "busy", "crowded", "limited", "plenty", 
                "find a seat", "get a table", "no seats", "no tables", "always full", "usually empty"
            ],
            "seating_comfort": [
                "comfortable", "comfort", "uncomfortable", "cushion", "hard", "soft", "ergonomic", "chair", "seating",
                "cozy", "uncomfortable", "stiff", "supportive", "back support", "cushioned"
            ],
        }
        
        def evidence_matches_attribute(evidence_list, keywords):
            """Check if any evidence contains relevant keywords for the attribute."""
            if not evidence_list:
                return False
            evidence_text = " ".join(evidence_list).lower()
            matches = any(keyword.lower() in evidence_text for keyword in keywords)
            if not matches:
                logger.debug(f"Evidence doesn't match keywords. Evidence: {evidence_text[:100]}, Keywords: {keywords}")
            return matches
        
        for key in ["has_wifi", "has_outlets", "is_laptop_friendly", "noise_level", 
                    "seating_availability", "seating_comfort", "notable_positives", "common_complaints"]:
            if key in parsed:
                attr_data = parsed[key]
                sources = attr_data.get("sources", [])
                evidence = attr_data.get("evidence", [])
                value = attr_data.get("value")
                confidence = float(attr_data.get("confidence", 0.0))
                
                # VALIDATION: Check if evidence actually relates to the attribute
                # For notable_positives and common_complaints, we allow any evidence
                if key not in ["notable_positives", "common_complaints"]:
                    # Check if there's no evidence OR evidence doesn't match the attribute
                    if not sources and not evidence:
                        # No evidence at all
                        logger.info(f"[VALIDATION] {key}: No sources or evidence found, setting to 'unknown'")
                        value = "unknown"
                        confidence = 0.0
                        logger.warning(
                            f"LLM returned {key}='{attr_data.get('value')}' with confidence "
                            f"{attr_data.get('confidence')} but no evidence. Overriding to 'unknown' with confidence 0.0"
                        )
                    else:
                        # Check if evidence matches attribute keywords
                        keywords_for_attr = attribute_keywords.get(key, [])
                        matches = evidence_matches_attribute(evidence, keywords_for_attr)
                        logger.debug(f"[VALIDATION] {key}: Checking evidence. Evidence={evidence}, Keywords={keywords_for_attr}, Matches={matches}")
                        
                        if not matches:
                            # Evidence exists but doesn't relate to this attribute
                            # Save original evidence for logging before clearing
                            original_evidence = evidence[:] if evidence else []
                            original_value = value
                            original_confidence = confidence
                            value = "unknown"
                            confidence = 0.0
                            sources = []
                            evidence = []
                            logger.warning(
                                f"VALIDATION FAILED: {key}='{original_value}' (conf={original_confidence}) has evidence that doesn't match attribute keywords. "
                                f"Evidence: {str(original_evidence)[:200]}. "
                                f"Keywords required: {keywords_for_attr}. "
                                f"Overriding to 'unknown' with confidence 0.0"
                            )
                        else:
                            logger.debug(f"[VALIDATION] {key}: Evidence validated successfully")
                
                derived[key] = {
                    "value": value,
                    "confidence": confidence,
                    "sources": sources,
                    "evidence": evidence,
                }
            else:
                # Default values if missing
                if key in ["notable_positives", "common_complaints"]:
                    derived[key] = {
                        "value": [],
                        "sources": [],
                        "evidence": [],
                    }
                else:
                    derived[key] = {
                        "value": "unknown",
                        "confidence": 0.0,
                        "sources": [],
                        "evidence": [],
                    }
        
        return derived
        
    except Exception as e:
        logger.error(f"LLM attribute derivation failed: {e}")
        # Return default structure on error
        return {
            "has_wifi": {"value": "unknown", "confidence": 0.0, "sources": [], "evidence": []},
            "has_outlets": {"value": "unknown", "confidence": 0.0, "sources": [], "evidence": []},
            "is_laptop_friendly": {"value": "unknown", "confidence": 0.0, "sources": [], "evidence": []},
            "noise_level": {"value": "unknown", "confidence": 0.0, "sources": [], "evidence": []},
            "seating_availability": {"value": "unknown", "confidence": 0.0, "sources": [], "evidence": []},
            "seating_comfort": {"value": "unknown", "confidence": 0.0, "sources": [], "evidence": []},
            "notable_positives": {"value": [], "sources": [], "evidence": []},
            "common_complaints": {"value": [], "sources": [], "evidence": []},
        }

