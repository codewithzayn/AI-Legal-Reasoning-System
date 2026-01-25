"""
Logging Configuration for AI Legal Reasoning System
Provides consistent JSON logging across all modules for production observability
"""

import logging
import os
import sys
from typing import Optional
from pythonjsonlogger import jsonlogger


def setup_logger(
    name: str = "legal_ai",
    level: Optional[str] = None,
) -> logging.Logger:
    """
    Create and configure a logger instance with JSON output.
    
    Args:
        name: Logger name (usually __name__ of calling module)
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
               Defaults to LOG_LEVEL env var or INFO
        
    Returns:
        Configured logger instance
    """
    # Get log level from env or default
    if level is None:
        level = os.getenv("LOG_LEVEL", "INFO").upper()
    
    numeric_level = getattr(logging, level, logging.INFO)
    
    # Create logger
    logger = logging.getLogger(name)
    
    # Only add handler if not already configured
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        
        # JSON formatter for production
        formatter = jsonlogger.JsonFormatter(
            '%(asctime)s %(levelname)s %(name)s %(message)s',
            datefmt="%Y-%m-%dT%H:%M:%S"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    
    logger.setLevel(numeric_level)
    
    return logger


# Create default application logger
logger = setup_logger("legal_ai")
