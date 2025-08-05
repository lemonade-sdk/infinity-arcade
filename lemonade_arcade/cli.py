"""
Command-line interface for Lemonade Arcade
"""

import argparse
import logging
import sys


def main():
    """Main entry point for the lemonade-arcade command."""
    parser = argparse.ArgumentParser(
        description="Lemonade Arcade - AI-powered game creation"
    )
    parser.add_argument(
        "--log-level",
        choices=["debug", "info", "warning", "error"],
        default="info",
        help="Set the logging level (default: info)",
    )

    args = parser.parse_args()

    # Configure logging
    log_level = getattr(logging, args.log_level.upper())

    # Set root logger to WARNING to suppress third-party debug logs
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        stream=sys.stdout,
    )

    # Set our specific logger to the requested level
    logger = logging.getLogger("lemonade_arcade.main")
    logger.setLevel(log_level)

    # Also set uvicorn to INFO level to reduce noise
    uvicorn_logger = logging.getLogger("uvicorn.access")
    if log_level == logging.DEBUG:
        uvicorn_logger.setLevel(
            logging.WARNING
        )  # Suppress uvicorn access logs in debug mode

    # Suppress httpx and httpcore debug logs
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    from .main import main as run_app

    run_app()


if __name__ == "__main__":
    main()
