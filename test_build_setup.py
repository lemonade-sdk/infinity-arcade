#!/usr/bin/env python3
"""
Test script to verify the MSIX build process works
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
        "PIL",
    ]

    for module in required_modules:
        try:
            if module == "PIL":
                # PIL is imported as PIL but package is pillow
                from PIL import Image
            else:
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

    # Test Windows SDK (makeappx.exe)
    makeappx_paths = [
        r"C:\Program Files (x86)\Windows Kits\10\bin\10.0.22621.0\x64\makeappx.exe",
        r"C:\Program Files (x86)\Windows Kits\10\bin\10.0.19041.0\x64\makeappx.exe",
    ]

    found_makeappx = False
    for path in makeappx_paths:
        if Path(path).exists():
            print(f"  ✓ makeappx.exe ({path})")
            found_makeappx = True
            break

    if not found_makeappx:
        print("  ✗ makeappx.exe (install Windows 10 SDK)")
        return False

    return True


def test_files():
    """Test that all required files exist."""
    print("\nTesting required files...")

    required_files = [
        "setup.py",
        "lemonade_arcade.spec",
        "build_msix.py",
        "build_msix.ps1",
        "msix/Package.appxmanifest",
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
    print("Lemonade Arcade MSIX Build Test")
    print("=" * 35)

    success = True

    success &= test_dependencies()
    success &= test_build_tools()
    success &= test_files()

    print("\n" + "=" * 35)
    if success:
        print("✓ All tests passed! Ready to build MSIX installer.")
        print("\nTo build the installer, run:")
        print("  PowerShell: .\\build_msix.ps1")
        print("  Python:     python build_msix.py")
    else:
        print("✗ Some tests failed. Please fix the issues above.")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
