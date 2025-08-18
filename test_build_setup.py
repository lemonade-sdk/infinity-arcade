#!/usr/bin/env python3
"""
Test script to verify the executable build process works
"""

import subprocess
import sys
from pathlib import Path


def test_dependencies():
    """Test that all required dependencies are available."""
    print("Testing dependencies...")

    # Test Python modules
    required_modules = [
        "setuptools",
        "fastapi",
        "uvicorn",
        "pygame",
        "httpx",
        "jinja2",
    ]

    for module in required_modules:
        try:
            __import__(module)
            print(f"  ✓ {module}")
        except ImportError:
            print(f"  ✗ {module} (missing)")
            return False

    return True


def test_build_tools():
    """Test that build tools are available."""
    print("\nTesting build tools...")

    # Test PyInstaller
    try:
        subprocess.run(
            [sys.executable, "-m", "PyInstaller", "--version"],
            check=True,
            capture_output=True,
        )
        print("  ✓ PyInstaller")
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("  ✗ PyInstaller (install with: pip install pyinstaller)")
        return False

    return True


def test_files():
    """Test that all required files exist."""
    print("\nTesting required files...")

    required_files = [
        "setup.py",
        "lemonade_arcade.spec",
        "build_exe.ps1",
        "lemonade_arcade/__init__.py",
        "lemonade_arcade/main.py",
        "lemonade_arcade/cli.py",
    ]

    for file_path in required_files:
        if Path(file_path).exists():
            print(f"  ✓ {file_path}")
        else:
            print(f"  ✗ {file_path} (missing)")
            return False

    return True


def main():
    """Run all tests."""
    print("Lemonade Arcade Executable Build Test")
    print("=" * 38)

    success = True

    success &= test_dependencies()
    success &= test_build_tools()
    success &= test_files()

    print("\n" + "=" * 38)
    if success:
        print("✓ All tests passed! Ready to build executable.")
        print("\nTo build the executable, run:")
        print("  PowerShell: .\\build_exe.ps1")
        print("  Python:     python -m PyInstaller lemonade_arcade.spec")
    else:
        print("✗ Some tests failed. Please fix the issues above.")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())

# Copyright (c) 2025 AMD
