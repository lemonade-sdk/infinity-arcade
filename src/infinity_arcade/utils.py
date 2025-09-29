import os
import sys


def get_resource_path(relative_path):
    """Get absolute path to resource, works for dev and for PyInstaller"""
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        # pylint: disable=protected-access,no-member
        base_path = sys._MEIPASS
        # In PyInstaller bundle, resources are under infinity_arcade/
        if relative_path in ["static", "templates", "builtin_games"]:
            return os.path.join(base_path, "infinity_arcade", relative_path)
        else:
            return os.path.join(base_path, relative_path)
    except Exception:
        # Use the directory of this file as the base path for development
        base_path = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(base_path, relative_path)
