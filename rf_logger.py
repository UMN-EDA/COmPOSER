import logging
import os
import sys

def get_rf_logger(log_dir="logs", log_name="rf_design.log"):
    """
    Create (if needed) and return a shared RF_DESIGN logger.
    Automatically makes directories and writes to both file + console.
    """
    # Ensure directory exists
    os.makedirs(log_dir, exist_ok=True)

    log_path = os.path.join(log_dir, log_name)
    logger = logging.getLogger("RF_DESIGN")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False   # prevent duplicate prints

    # Only add handlers once
    if not logger.handlers:
        # --- File handler ---
        fh = logging.FileHandler(log_path, mode="w", encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter("%(levelname)-8s | %(module)-15s | %(message)s"))
        logger.addHandler(fh)

        # --- Console handler (optional) ---
        ch = logging.StreamHandler(sys.stdout)
        ch.setLevel(logging.INFO)
        ch.setFormatter(logging.Formatter("%(levelname)-8s | %(module)-15s | %(message)s"))
        logger.addHandler(ch)

        # Confirm creation in the file immediately
        logger.debug("Initialized RF_DESIGN logger.")
        fh.flush()

    return logger

def log_section(logger, title):
    bar = "=" * 200
    logger.info(f"\n{bar}\n>>> {title.upper()}\n{bar}")
