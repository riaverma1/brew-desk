"""
File locking utilities for atomic JSON operations.
"""
import os
import sys
import time
import logging
from contextlib import contextmanager
from pathlib import Path

logger = logging.getLogger(__name__)

# Platform-specific locking
if sys.platform == "win32":
    import msvcrt
    
    @contextmanager
    def file_lock(file_path: str, timeout: float = 10.0):
        """
        Windows file lock using msvcrt.
        
        Args:
            file_path: Path to file to lock
            timeout: Maximum time to wait for lock (seconds)
        """
        lock_file_path = str(Path(file_path).with_suffix('.lock'))
        start_time = time.time()
        
        while True:
            try:
                # Try to open lock file in exclusive mode
                lock_fd = os.open(lock_file_path, os.O_CREAT | os.O_EXCL | os.O_RDWR)
                try:
                    yield lock_fd
                finally:
                    os.close(lock_fd)
                    try:
                        os.remove(lock_file_path)
                    except:
                        pass
                break
            except OSError:
                if time.time() - start_time > timeout:
                    raise TimeoutError(f"Could not acquire lock for {file_path} after {timeout}s")
                time.sleep(0.1)
else:
    import fcntl
    
    @contextmanager
    def file_lock(file_path: str, timeout: float = 10.0):
        """
        Unix file lock using fcntl.
        
        Args:
            file_path: Path to file to lock
            timeout: Maximum time to wait for lock (seconds)
        """
        lock_file_path = str(Path(file_path).with_suffix('.lock'))
        start_time = time.time()
        
        while True:
            try:
                lock_fd = open(lock_file_path, 'w')
                try:
                    # Try to acquire exclusive lock (non-blocking)
                    fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    try:
                        yield lock_fd.fileno()
                    finally:
                        fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)
                        lock_fd.close()
                        try:
                            os.remove(lock_file_path)
                        except:
                            pass
                    break
                except IOError:
                    lock_fd.close()
                    if time.time() - start_time > timeout:
                        raise TimeoutError(f"Could not acquire lock for {file_path} after {timeout}s")
                    time.sleep(0.1)
            except Exception as e:
                if time.time() - start_time > timeout:
                    raise TimeoutError(f"Could not acquire lock for {file_path} after {timeout}s: {e}")
                time.sleep(0.1)

