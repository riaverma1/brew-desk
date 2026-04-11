"""
In-memory process locks to prevent duplicate enrichment operations.
"""
import threading
import time
import logging
from contextlib import contextmanager
from typing import Dict, Set
from collections import defaultdict

logger = logging.getLogger(__name__)

# Global locks for place processing
_place_locks: Dict[str, threading.Lock] = {}
_locks_lock = threading.Lock()  # Lock for managing place_locks dict
_processing_places: Set[str] = set()  # Track places currently being processed
_processing_lock = threading.Lock()  # Lock for processing_places set
_error_counts: Dict[str, int] = defaultdict(int)  # Track error counts per place
_max_errors = 3  # Max errors before stopping processing for a place


def get_place_lock(place_id: str) -> threading.Lock:
    """Get or create a lock for a specific place_id."""
    with _locks_lock:
        if place_id not in _place_locks:
            _place_locks[place_id] = threading.Lock()
        return _place_locks[place_id]


def is_processing(place_id: str) -> bool:
    """Check if a place is currently being processed."""
    with _processing_lock:
        return place_id in _processing_places


def set_processing(place_id: str, processing: bool):
    """Set processing status for a place."""
    with _processing_lock:
        if processing:
            _processing_places.add(place_id)
        else:
            _processing_places.discard(place_id)


def record_error(place_id: str):
    """Record an error for a place. Returns True if should stop processing."""
    with _processing_lock:
        _error_counts[place_id] += 1
        if _error_counts[place_id] >= _max_errors:
            logger.error(f"Place {place_id} has exceeded max errors ({_max_errors}), stopping processing")
            return True
        return False


def clear_errors(place_id: str):
    """Clear error count for a place (on successful processing)."""
    with _processing_lock:
        _error_counts[place_id] = 0


@contextmanager
def place_processing_lock(place_id: str, operation: str = "enrichment"):
    """
    Context manager for acquiring a lock on a place during processing.
    
    Args:
        place_id: Place ID to lock
        operation: Description of operation (for logging)
    """
    lock = get_place_lock(place_id)
    
    # Check if already processing
    if is_processing(place_id):
        logger.warning(f"Place {place_id} is already being processed, skipping {operation}")
        raise AlreadyProcessingError(f"Place {place_id} is already being processed")
    
    # Check error count
    if record_error(place_id):
        raise TooManyErrorsError(f"Place {place_id} has too many errors, stopping processing")
    
    acquired = False
    try:
        acquired = lock.acquire(blocking=False)
        if not acquired:
            logger.warning(f"Could not acquire lock for {place_id}, already processing")
            raise AlreadyProcessingError(f"Could not acquire lock for {place_id}")
        
        set_processing(place_id, True)
        logger.debug(f"Acquired lock for {place_id} ({operation})")
        
        try:
            yield
            clear_errors(place_id)  # Clear errors on success
        except Exception as e:
            record_error(place_id)
            raise
    finally:
        if acquired:
            lock.release()
            set_processing(place_id, False)
            logger.debug(f"Released lock for {place_id} ({operation})")


class AlreadyProcessingError(Exception):
    """Raised when a place is already being processed."""
    pass


class TooManyErrorsError(Exception):
    """Raised when a place has too many errors."""
    pass

