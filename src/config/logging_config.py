"""
Logging Configuration for AI Legal Reasoning System
Provides consistent logging across all modules
"""

import logging
import os
import sys
from typing import Optional


def setup_logger(
    name: str = "legal_ai",
    level: Optional[str] = None,
    log_format: Optional[str] = None
) -> logging.Logger:
    """
    Create and configure a logger instance.
    
    Args:
        name: Logger name (usually __name__ of calling module)
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
               Defaults to LOG_LEVEL env var or INFO
        log_format: Custom log format string
        
    Returns:
        Configured logger instance
    """
    # Get log level from env or default
    if level is None:
        level = os.getenv("LOG_LEVEL", "INFO").upper()
    
    numeric_level = getattr(logging, level, logging.INFO)
    
    # Default format
    if log_format is None:
        log_format = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    
    # Create logger
    logger = logging.getLogger(name)
    
    # Only add handler if not already configured
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(log_format, datefmt="%Y-%m-%d %H:%M:%S"))
        logger.addHandler(handler)
    
    logger.setLevel(numeric_level)
    
    return logger


# Create default application logger
logger = setup_logger("legal_ai")
