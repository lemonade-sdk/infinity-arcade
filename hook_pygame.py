import os
import sys


# Runtime hook for pygame DLL loading in PyInstaller
def setup_pygame_environment():
    """Set up environment for pygame DLL loading in PyInstaller bundle."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        # We're in a PyInstaller bundle
        bundle_dir = sys._MEIPASS

        # Add the bundle directory to DLL search paths
        if hasattr(os, "add_dll_directory"):
            try:
                os.add_dll_directory(bundle_dir)
            except (OSError, FileNotFoundError):
                pass

        # Set environment variables that help with SDL2 loading and prevent SDL3
        os.environ["SDL_VIDEODRIVER"] = "windib"
        os.environ["SDL_AUDIODRIVER"] = "directsound"
        
        # Explicitly prefer SDL2 over SDL3
        os.environ["SDL_DYNAMIC_API"] = os.path.join(bundle_dir, "SDL2.dll")

        # Add bundle to PATH for DLL resolution (put it first to prioritize our DLLs)
        current_path = os.environ.get("PATH", "")
        if bundle_dir not in current_path:
            os.environ["PATH"] = bundle_dir + os.pathsep + current_path


# Run the setup immediately when this hook is imported
setup_pygame_environment()
