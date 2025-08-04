"""
Command-line interface for Lemonade Arcade
"""


def main():
    """Main entry point for the lemonade-arcade command."""
    from .main import main as run_app

    run_app()


if __name__ == "__main__":
    main()
