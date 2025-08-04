#!/usr/bin/env python3
"""
Test script to verify Lemonade Arcade installation
"""


def test_imports():
    """Test that all required packages can be imported."""
    try:
        import fastapi

        print("✓ FastAPI imported successfully")
    except ImportError as e:
        print(f"✗ FastAPI import failed: {e}")
        return False

    try:
        import uvicorn

        print("✓ Uvicorn imported successfully")
    except ImportError as e:
        print(f"✗ Uvicorn import failed: {e}")
        return False

    try:
        import pygame

        print("✓ Pygame imported successfully")
    except ImportError as e:
        print(f"✗ Pygame import failed: {e}")
        return False

    try:
        import httpx

        print("✓ HTTPX imported successfully")
    except ImportError as e:
        print(f"✗ HTTPX import failed: {e}")
        return False

    try:
        from lemonade_arcade import main

        print("✓ Lemonade Arcade main module imported successfully")
    except ImportError as e:
        print(f"✗ Lemonade Arcade import failed: {e}")
        return False

    return True


def test_entry_point():
    """Test that the entry point works."""
    try:
        from lemonade_arcade.cli import main

        print("✓ Entry point accessible")
        return True
    except ImportError as e:
        print(f"✗ Entry point failed: {e}")
        return False


if __name__ == "__main__":
    print("Testing Lemonade Arcade installation...")
    print("=" * 50)

    imports_ok = test_imports()
    entry_ok = test_entry_point()

    print("=" * 50)
    if imports_ok and entry_ok:
        print("✓ All tests passed! Lemonade Arcade is ready to run.")
        print("\nTo start the application, run: lemonade-arcade")
    else:
        print("✗ Some tests failed. Please check the installation.")
        print("\nTry running: pip install -e .")
