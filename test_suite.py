#!/usr/bin/env python3
"""
Comprehensive test suite for Lemonade Arcade
"""

import asyncio
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# Test configuration
TEST_PORT = 8081  # Use different port to avoid conflicts
TEST_TIMEOUT = 30  # seconds


def test_package_structure():
    """Test that all required files exist."""
    print("Testing package structure...")

    required_files = [
        "lemonade_arcade/__init__.py",
        "lemonade_arcade/main.py",
        "lemonade_arcade/cli.py",
        "setup.py",
        "requirements.txt",
        "README.md",
        "DEVELOPMENT.md",
    ]

    missing_files = []
    for file_path in required_files:
        if not Path(file_path).exists():
            missing_files.append(file_path)

    if missing_files:
        print(f"✗ Missing files: {missing_files}")
        return False

    print("✓ All required files present")
    return True


def test_imports():
    """Test that all modules can be imported."""
    print("Testing imports...")

    try:
        import lemonade_arcade

        print("✓ lemonade_arcade package imported")
    except ImportError as e:
        print(f"✗ Failed to import lemonade_arcade: {e}")
        return False

    try:
        from lemonade_arcade import main

        print("✓ main module imported")
    except ImportError as e:
        print(f"✗ Failed to import main: {e}")
        return False

    try:
        from lemonade_arcade.cli import main as cli_main

        print("✓ CLI module imported")
    except ImportError as e:
        print(f"✗ Failed to import CLI: {e}")
        return False

    return True


def test_demo_games():
    """Test that demo games can be created and work."""
    print("Testing demo game creation...")

    try:
        # Import after ensuring the package is available
        sys.path.insert(0, str(Path.cwd()))
        from create_demo_games import create_demo_games

        # Create demo games
        snake_id, pong_id = create_demo_games()
        print(f"✓ Demo games created: {snake_id}, {pong_id}")

        # Check that files were created
        from lemonade_arcade.main import GAMES_DIR, GAME_METADATA

        snake_file = GAMES_DIR / f"{snake_id}.py"
        pong_file = GAMES_DIR / f"{pong_id}.py"

        if not snake_file.exists():
            print(f"✗ Snake game file not created: {snake_file}")
            return False

        if not pong_file.exists():
            print(f"✗ Pong game file not created: {pong_file}")
            return False

        print("✓ Demo game files created successfully")

        # Test that the games can be parsed as valid Python
        with open(snake_file, "r", encoding="utf-8") as f:
            snake_code = f.read()

        with open(pong_file, "r", encoding="utf-8") as f:
            pong_code = f.read()

        # Try to compile the code
        try:
            compile(snake_code, str(snake_file), "exec")
            print("✓ Snake game code compiles successfully")
        except SyntaxError as e:
            print(f"✗ Snake game has syntax error: {e}")
            return False

        try:
            compile(pong_code, str(pong_file), "exec")
            print("✓ Pong game code compiles successfully")
        except SyntaxError as e:
            print(f"✗ Pong game has syntax error: {e}")
            return False

        return True

    except Exception as e:
        print(f"✗ Demo game creation failed: {e}")
        return False


async def test_server_startup():
    """Test that the FastAPI server can start up."""
    print("Testing server startup...")

    try:
        # Import the FastAPI app
        from lemonade_arcade.main import app

        # Test that the app object exists and has the expected routes
        routes = [route.path for route in app.routes]
        expected_routes = ["/", "/api/server-status", "/api/models", "/api/games"]

        for expected_route in expected_routes:
            if expected_route not in routes:
                print(f"✗ Missing route: {expected_route}")
                return False

        print("✓ FastAPI app created with expected routes")

        # Try to import uvicorn to make sure we can run the server
        import uvicorn

        print("✓ Uvicorn available for serving")

        return True

    except Exception as e:
        print(f"✗ Server startup test failed: {e}")
        return False


def test_game_management():
    """Test game management functions."""
    print("Testing game management...")

    try:
        from lemonade_arcade.main import (
            generate_game_id,
            extract_python_code,
            GAMES_DIR,
            GAME_METADATA,
            save_metadata,
        )

        # Test ID generation
        game_id1 = generate_game_id()
        game_id2 = generate_game_id()

        if len(game_id1) != 8 or len(game_id2) != 8:
            print("✗ Game IDs should be 8 characters long")
            return False

        if game_id1 == game_id2:
            print("✗ Game IDs should be unique")
            return False

        print("✓ Game ID generation works")

        # Test code extraction
        test_code = """Here's a simple game:
```python
import pygame
pygame.init()
# Game code here
```
That's the game!"""

        extracted = extract_python_code(test_code)
        if not extracted or "pygame" not in extracted:
            print("✗ Code extraction failed")
            return False

        print("✓ Code extraction works")

        # Test metadata saving
        original_metadata = dict(GAME_METADATA)
        test_id = "test123"
        GAME_METADATA[test_id] = {
            "title": "Test Game",
            "description": "A test game",
            "created": time.time(),
        }

        save_metadata()
        print("✓ Metadata saving works")

        # Restore original metadata
        GAME_METADATA.clear()
        GAME_METADATA.update(original_metadata)
        save_metadata()

        return True

    except Exception as e:
        print(f"✗ Game management test failed: {e}")
        return False


async def run_all_tests():
    """Run all tests and report results."""
    print("Lemonade Arcade Test Suite")
    print("=" * 50)

    tests = [
        ("Package Structure", test_package_structure),
        ("Imports", test_imports),
        ("Demo Games", test_demo_games),
        ("Server Startup", test_server_startup),
        ("Game Management", test_game_management),
    ]

    results = []

    for test_name, test_func in tests:
        print(f"\n{test_name}:")
        print("-" * len(test_name))

        if asyncio.iscoroutinefunction(test_func):
            result = await test_func()
        else:
            result = test_func()

        results.append((test_name, result))

    print("\n" + "=" * 50)
    print("Test Results:")

    passed = 0
    total = len(results)

    for test_name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"  {test_name}: {status}")
        if result:
            passed += 1

    print(f"\nSummary: {passed}/{total} tests passed")

    if passed == total:
        print("\n🎉 All tests passed! Lemonade Arcade is ready to use.")
        print("\nTo start the application:")
        print("  lemonade-arcade")
        print("\nOr on Windows:")
        print("  start_arcade.bat")
    else:
        print(f"\n❌ {total - passed} tests failed. Please check the issues above.")

    return passed == total


if __name__ == "__main__":
    asyncio.run(run_all_tests())
