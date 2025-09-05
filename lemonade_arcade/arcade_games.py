import logging
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict


from lemonade_arcade.utils import get_resource_path

logger = logging.getLogger("lemonade_arcade.main")


class ArcadeGames:
    """
    Game storage and metadata manager.

    This class is intentionally free of LLM logic and process execution logic.
    It only knows where games live on disk, how to persist metadata, and which
    games are built-in.
    """

    def __init__(self):

        # Global state
        self.games_dir = Path.home() / ".lemonade-arcade" / "games"
        self.game_metadata: Dict[str, Dict] = {}

        # Ensure games directory exists
        self.games_dir.mkdir(parents=True, exist_ok=True)

        # Load existing game metadata
        self.metadata_file = self.games_dir / "metadata.json"
        if self.metadata_file.exists():
            try:
                with open(self.metadata_file, "r", encoding="utf-8") as metadata_file:
                    self.game_metadata = json.load(metadata_file)
            except Exception:
                self.game_metadata = {}

        # Built-in games configuration
        self.builtin_games = {
            "builtin_snake": {
                "title": "Dynamic Snake",
                "created": 0,  # Special marker for built-in games
                "prompt": "Snake but the food moves around",
                "builtin": True,
                "file": "snake_moving_food.py",
            },
            "builtin_invaders": {
                "title": "Rainbow Space Invaders",
                "created": 0,  # Special marker for built-in games
                "prompt": "Space invaders with rainbow colors",
                "builtin": True,
                "file": "rainbow_space_invaders.py",
            },
        }

        # Add built-in games to metadata if not already present
        for game_id, game_data in self.builtin_games.items():
            if game_id not in self.game_metadata:
                self.game_metadata[game_id] = game_data.copy()

    def save_metadata(self):
        """Save game metadata to disk."""
        try:
            with open(self.metadata_file, "w", encoding="utf-8") as f:
                json.dump(self.game_metadata, f, indent=2)
        except Exception as e:
            print(f"Error saving metadata: {e}")

    # Storage helpers
    def save_game_file(self, game_id: str, code: str) -> Path:
        game_file = self.games_dir / f"{game_id}.py"
        with open(game_file, "w", encoding="utf-8") as f:
            f.write(code)
        return game_file

    def read_game_file(self, game_id: str) -> str:
        game_file = self.games_dir / f"{game_id}.py"
        with open(game_file, "r", encoding="utf-8") as f:
            return f.read()
