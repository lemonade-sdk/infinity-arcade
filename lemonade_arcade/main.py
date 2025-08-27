#!/usr/bin/env python3
"""
Lemonade Arcade - Main FastAPI application
"""

import json
import logging
import os
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Dict, Optional

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import (
    JSONResponse,
    StreamingResponse,
    RedirectResponse,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import lemonade_arcade.lemonade_client as lc

lemonade_handle = lc.LemonadeClient()


# Pygame will be imported on-demand to avoid early DLL loading issues
# pylint: disable=invalid-name
pygame = None

if os.environ.get("LEMONADE_ARCADE_MODEL"):
    REQUIRED_MODEL = os.environ.get("LEMONADE_ARCADE_MODEL")
else:
    REQUIRED_MODEL = "Qwen3-Coder-30B-A3B-Instruct-GGUF"

# Set up logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("lemonade_arcade.main")

# Suppress noisy httpcore debug messages
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)


def get_resource_path(relative_path):
    """Get absolute path to resource, works for dev and for PyInstaller"""
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        # pylint: disable=protected-access,no-member
        base_path = sys._MEIPASS
        # In PyInstaller bundle, resources are under lemonade_arcade/
        if relative_path in ["static", "templates", "builtin_games"]:
            return os.path.join(base_path, "lemonade_arcade", relative_path)
        else:
            return os.path.join(base_path, relative_path)
    except Exception:
        # Use the directory of this file as the base path for development
        base_path = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(base_path, relative_path)


app = FastAPI(title="Lemonade Arcade", version="0.1.0")

# Set up static files and templates
STATIC_DIR = get_resource_path("static")
TEMPLATES_DIR = get_resource_path("templates")

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


class ArcadeGames:
    """
    Keep track of the state of saved and running games.
    """

    def __init__(self):

        # Global state
        self.games_dir = Path.home() / ".lemonade-arcade" / "games"
        self.running_games: Dict[str, subprocess.Popen] = {}
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
        self.BUILTIN_GAMES = {
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
        for game_id, game_data in self.BUILTIN_GAMES.items():
            if game_id not in self.game_metadata:
                self.game_metadata[game_id] = game_data.copy()

    def save_metadata(self):
        """Save game metadata to disk."""
        try:
            with open(self.metadata_file, "w", encoding="utf-8") as f:
                json.dump(self.game_metadata, f, indent=2)
        except Exception as e:
            print(f"Error saving metadata: {e}")

    def launch_game(self, game_id: str):
        """Launch a game in a separate process."""
        logger.debug(f"Attempting to launch game {game_id}")

        # Check if it's a built-in game
        if game_id in self.BUILTIN_GAMES:
            # For built-in games, use the file from the builtin_games directory
            builtin_games_dir = get_resource_path("builtin_games")
            game_file = Path(builtin_games_dir) / self.BUILTIN_GAMES[game_id]["file"]
            logger.debug(f"Looking for built-in game file at: {game_file}")
        else:
            # For user-generated games, use the standard games directory
            game_file = self.games_dir / f"{game_id}.py"
            logger.debug(f"Looking for user game file at: {game_file}")

        if not game_file.exists():
            logger.error(f"Game file not found: {game_file}")
            raise FileNotFoundError(f"Game file not found: {game_file}")

        # Launch the game
        try:
            # In PyInstaller environment, use the same executable with the game file as argument
            # This ensures the game runs with the same DLL configuration
            if getattr(sys, "frozen", False):
                # We're in PyInstaller - use the same executable that has the SDL2 DLLs
                cmd = [sys.executable, str(game_file)]
                logger.debug(f"PyInstaller mode - Launching: {' '.join(cmd)}")
            else:
                # Development mode - use regular Python
                cmd = [sys.executable, str(game_file)]
                logger.debug(f"Development mode - Launching: {' '.join(cmd)}")

            # pylint: disable=consider-using-with
            process = subprocess.Popen(cmd)
            self.running_games[game_id] = process
            logger.debug(f"Game {game_id} launched successfully with PID {process.pid}")
            return True
        except Exception as e:
            logger.error(f"Error launching game {game_id}: {e}")
            return False

    def stop_game(self, game_id: str):
        """Stop a running game."""
        if game_id in self.running_games:
            try:
                process = self.running_games[game_id]
                process.terminate()
                # Wait a bit for graceful termination
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
            except Exception as e:
                print(f"Error stopping game {game_id}: {e}")
            finally:
                del self.running_games[game_id]

    def cleanup_finished_games(self):
        """Clean up finished game processes."""
        finished = []
        for game_id, process in self.running_games.items():
            if process.poll() is not None:  # Process has finished
                finished.append(game_id)

        for game_id in finished:
            del self.running_games[game_id]


arcade_games = ArcadeGames()


async def generate_game_title(prompt: str) -> str:
    """Generate a short title for the game based on the prompt."""
    logger.debug(f"Generating title for prompt: {prompt[:50]}...")

    try:
        # pylint: disable=line-too-long
        title_prompt = f"""Generate a short game title (2-3 words maximum) for this game concept: "{prompt}"

Requirements:
- EXACTLY 2-3 words only
- Should be catchy and describe the game
- No punctuation except spaces
- Examples: "Snake Game", "Space Shooter", "Puzzle Master", "Racing Fun"

Return ONLY the title, nothing else."""

        messages = [
            {
                "role": "system",
                "content": "You are a game title generator. Return only the title, nothing else.",
            },
            {"role": "user", "content": title_prompt},
        ]

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{lemonade_handle.url}/api/v1/chat/completions",
                json={
                    "model": REQUIRED_MODEL,
                    "messages": messages,
                    "stream": False,
                    "max_tokens": 20,
                    "temperature": 0.3,
                },
                headers={"Content-Type": "application/json"},
            )

            if response.status_code == 200:
                data = response.json()
                if "choices" in data and len(data["choices"]) > 0:
                    title = data["choices"][0]["message"]["content"].strip()
                    # Clean up the title - remove quotes and extra text
                    title = title.strip("\"'").split("\n")[0].strip()
                    # Limit to 3 words max
                    words = title.split()[:3]
                    final_title = " ".join(words)
                    logger.debug(f"Generated title: {final_title}")
                    return final_title
    except Exception as e:
        logger.warning(f"Failed to generate title: {e}")

    # Fallback to extracting from prompt
    title_words = prompt.split()[:3]
    fallback_title = " ".join(title_words).title()
    logger.debug(f"Using fallback title: {fallback_title}")
    return fallback_title


def extract_python_code(llm_response: str) -> Optional[str]:
    """Extract Python code block from LLM response."""
    logger.debug(f"Extracting Python code from response of length {len(llm_response)}")

    # Look for code blocks with python/py language specifier
    patterns = [
        r"```python\s*\n(.*?)\n```",
        r"```py\s*\n(.*?)\n```",
        r"```\s*\n(.*?)\n```",  # Generic code block
    ]

    for i, pattern in enumerate(patterns):
        logger.debug(f"Trying pattern {i+1}: {pattern}")
        match = re.search(pattern, llm_response, re.DOTALL)
        if match:
            code = match.group(1).strip()
            logger.debug(f"Found code block with pattern {i+1}, length: {len(code)}")
            # Basic validation - should contain pygame
            if "pygame" in code.lower():
                logger.debug("Code contains pygame, validation passed")
                return code
            else:
                logger.warning("Code block found but doesn't contain pygame")

    logger.error("No valid Python code block found in response")
    return None


def generate_game_id():
    """Generate a unique game ID."""
    return str(uuid.uuid4())[:8]


@app.get("/")
async def root(request: Request):
    """Serve the main HTML page."""
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/favicon.ico")
async def favicon():
    """Redirect to favicon in static directory."""
    return RedirectResponse(url="/static/favicon.ico")


@app.get("/api/server-status")
async def server_status():
    """Check if Lemonade Server is online."""
    online = await lemonade_handle.check_lemonade_server_api()
    return JSONResponse({"online": online})


@app.get("/api/games")
async def get_games():
    """Get all saved games."""
    arcade_games.cleanup_finished_games()
    return JSONResponse(arcade_games.game_metadata)


@app.get("/api/installation-status")
async def installation_status():
    """Check lemonade-server installation status ONLY."""
    logger.info("Installation status endpoint called")
    version_info = await lemonade_handle.check_lemonade_server_version()
    logger.info(f"Version check result: {version_info}")

    result = {
        "installed": version_info["installed"],
        "version": version_info["version"],
        "compatible": version_info["compatible"],
        "required_version": version_info["required_version"],
    }
    logger.info(f"Returning installation status: {result}")
    return JSONResponse(result)


@app.get("/api/server-running-status")
async def server_running_status():
    """Check if lemonade-server is running ONLY, and auto-start if needed."""
    logger.info("=== Server running status endpoint called ===")

    # Check if server is currently running
    is_running = await lemonade_handle.check_lemonade_server_running()
    logger.info(f"Initial running check result: {is_running}")

    # If server is not running, try to start it automatically
    if not is_running:
        logger.info("Server not running, attempting to start automatically...")
        start_result = await lemonade_handle.start_lemonade_server()
        logger.info(f"Auto-start result: {start_result}")

        if start_result["success"]:
            # Give it a moment to start up
            import asyncio

            logger.info("Waiting 2 seconds for server to initialize...")
            await asyncio.sleep(2)

            # Check again
            is_running = await lemonade_handle.check_lemonade_server_running()
            logger.info(f"Running check after auto-start: {is_running}")
        else:
            logger.warning(
                f"Auto-start failed: {start_result.get('error', 'Unknown error')}"
            )

    result = {
        "running": is_running,
    }
    logger.info(f"=== Returning server running status: {result} ===")
    return JSONResponse(result)


@app.get("/api/api-connection-status")
async def api_connection_status():
    """Check API connection status ONLY."""
    logger.info("=== API connection status endpoint called ===")
    api_online = await lemonade_handle.check_lemonade_server_api()
    logger.info(f"API online check result: {api_online}")

    result = {
        "api_online": api_online,
    }
    logger.info(f"=== Returning API connection status: {result} ===")
    return JSONResponse(result)


@app.get("/api/model-installation-status")
async def model_installation_status():
    """Check if required model is installed ONLY."""
    logger.info("Model installation status endpoint called")
    model_status = await lemonade_handle.check_model_installed(REQUIRED_MODEL)
    logger.info(f"Model check result: {model_status}")

    result = {
        "model_installed": model_status["installed"],
        "model_name": model_status["model_name"],
    }
    logger.info(f"Returning model installation status: {result}")
    return JSONResponse(result)


@app.get("/api/model-loading-status")
async def model_loading_status():
    """Check if required model is loaded ONLY."""
    logger.info("Model loading status endpoint called")
    model_loaded_status = await lemonade_handle.check_model_loaded(REQUIRED_MODEL)
    logger.info(f"Model loaded check result: {model_loaded_status}")

    result = {
        "model_loaded": model_loaded_status["loaded"],
        "model_name": model_loaded_status["model_name"],
        "current_model": model_loaded_status["current_model"],
    }
    logger.info(f"Returning model loading status: {result}")
    return JSONResponse(result)


@app.get("/api/installation-environment")
async def installation_environment():
    """Check installation environment and available methods."""
    logger.info("Installation environment endpoint called")

    is_pyinstaller = lemonade_handle.is_pyinstaller_environment()
    sdk_available = (
        await lemonade_handle.check_lemonade_sdk_available()
        if not is_pyinstaller
        else False
    )

    result = {
        "is_pyinstaller": is_pyinstaller,
        "sdk_available": sdk_available,
        "platform": sys.platform,
        "preferred_method": "pip" if not is_pyinstaller else "installer",
    }

    logger.info(f"Returning installation environment: {result}")
    return JSONResponse(result)


@app.post("/api/refresh-environment")
async def refresh_environment_endpoint():
    """Refresh environment variables after installation."""
    logger.info("Refresh environment endpoint called")
    try:
        lemonade_handle.refresh_environment()
        # Also reset server state so it will re-discover commands
        lemonade_handle.reset_server_state()
        return JSONResponse({"success": True, "message": "Environment refreshed"})
    except Exception as e:
        logger.error(f"Failed to refresh environment: {e}")
        return JSONResponse(
            {"success": False, "message": f"Failed to refresh environment: {e}"}
        )


@app.post("/api/install-server")
async def install_server():
    """Download and install lemonade-server."""
    logger.info("Install server endpoint called")
    result = await lemonade_handle.download_and_install_lemonade_server()
    logger.info(f"Install result: {result}")
    return JSONResponse(result)


@app.post("/api/start-server")
async def start_server():
    """Start lemonade-server if installed."""
    logger.info("Start server endpoint called")
    result = await lemonade_handle.start_lemonade_server()
    logger.info(f"Start server result: {result}")
    return JSONResponse(result)


@app.post("/api/install-model")
async def install_model():
    """Install the required model."""
    logger.info("Install model endpoint called")
    result = await lemonade_handle.install_model(REQUIRED_MODEL)
    logger.info(f"Install model result: {result}")
    return JSONResponse(result)


@app.post("/api/load-model")
async def load_model():
    """Load the required model."""
    logger.info("Load model endpoint called")
    result = await lemonade_handle.load_model(REQUIRED_MODEL)
    logger.info(f"Load model result: {result}")
    return JSONResponse(result)


@app.post("/api/create-game")
async def create_game_endpoint(request: Request):
    """Create a new game using LLM."""
    logger.debug("Starting game creation endpoint")

    data = await request.json()
    prompt = data.get("prompt", "")

    logger.debug(f"Received request - prompt: '{prompt[:50]}...'")

    if not prompt:
        logger.error("No prompt provided")
        raise HTTPException(status_code=400, detail="Prompt is required")

    # Generate a unique game ID
    game_id = generate_game_id()
    logger.debug(f"Generated game ID: {game_id}")

    async def generate():
        try:
            logger.debug("Starting generate() function")
            # Send status update
            yield f"data: {json.dumps({'type': 'status', 'message': 'Connecting to LLM...'})}\n\n"
            logger.debug("Sent 'Connecting to LLM...' status")

            # Prepare the system prompt for game generation
            # pylint: disable=line-too-long
            system_prompt = """You are an expert Python game developer. Generate a complete, working Python game using pygame based on the user's description.

Rules:
1. Use ONLY the pygame library - no external images, sounds, or files
2. Create everything (graphics, colors, shapes) using pygame's built-in drawing functions
3. Make the game fully playable and fun
4. Include proper game mechanics (win/lose conditions, scoring if appropriate)
5. Use proper pygame event handling and game loop
6. Add comments explaining key parts of the code
7. Make sure the game window closes properly when the user clicks the X button
8. Use reasonable colors and make the game visually appealing with pygame primitives

Generate ONLY the Python code in a single code block. Do not include any explanations outside the code block."""

            # Create chat messages
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Create a game: {prompt}"},
            ]

            logger.debug(
                f"Prepared messages for LLM, system prompt length: {len(system_prompt)}"
            )

            # Stream response from Lemonade Server
            logger.debug(
                f"Starting request to {lemonade_handle.url}/api/v1/chat/completions"
            )
            async with httpx.AsyncClient(timeout=600.0) as client:
                async with client.stream(
                    "POST",
                    f"{lemonade_handle.url}/api/v1/chat/completions",
                    json={
                        "model": REQUIRED_MODEL,
                        "messages": messages,
                        "stream": True,
                        "max_tokens": 4000,
                        "temperature": 0.7,
                    },
                    headers={"Content-Type": "application/json"},
                ) as response:

                    logger.debug(
                        f"Received response with status code: {response.status_code}"
                    )

                    if response.status_code != 200:
                        logger.error(
                            f"LLM request failed with status {response.status_code}"
                        )
                        yield f"data: {json.dumps({'type': 'error', 'message': 'Failed to connect to LLM'})}\n\n"
                        return

                    yield f"data: {json.dumps({'type': 'status', 'message': 'Generating code...'})}\n\n"
                    logger.debug("Sent 'Generating code...' status")

                    full_response = ""
                    line_count = 0
                    async for line in response.aiter_lines():
                        line_count += 1
                        logger.debug(f"Processing line {line_count}: {line[:100]}...")

                        if line.startswith("data: "):
                            try:
                                chunk_data = json.loads(line[6:])
                                logger.debug(f"Parsed chunk data: {chunk_data}")

                                if (
                                    "choices" in chunk_data
                                    and len(chunk_data["choices"]) > 0
                                ):
                                    delta = chunk_data["choices"][0].get("delta", {})
                                    if (
                                        "content" in delta
                                        and delta["content"] is not None
                                    ):
                                        content = delta["content"]
                                        full_response += content
                                        logger.debug(
                                            f"Added content to response, total length: {len(full_response)}"
                                        )
                                        yield f"data: {json.dumps({'type': 'content', 'content': content})}\n\n"
                            except json.JSONDecodeError as e:
                                logger.warning(
                                    f"Failed to parse JSON from line: {line} - Error: {e}"
                                )
                                continue

                    logger.debug(
                        f"Finished processing stream, total lines: {line_count}, response length: {len(full_response)}"
                    )

            # Extract Python code
            yield f"data: {json.dumps({'type': 'status', 'message': 'Extracting code...'})}\n\n"
            logger.debug("Starting code extraction")

            python_code = extract_python_code(full_response)
            if not python_code:
                logger.error(
                    f"Could not extract Python code from response. Response length: {len(full_response)}"
                )
                logger.debug(f"Full response: {full_response}")
                yield f"data: {json.dumps({'type': 'error', 'message': 'Could not extract valid Python code from response'})}\n\n"
                return

            logger.debug(
                f"Successfully extracted Python code, length: {len(python_code)}"
            )

            # Save the game
            game_file = arcade_games.games_dir / f"{game_id}.py"
            logger.debug(f"Saving game to: {game_file}")
            with open(game_file, "w", encoding="utf-8") as f:
                f.write(python_code)
            logger.debug("Game file saved successfully")

            # Generate a proper title for the game
            yield f"data: {json.dumps({'type': 'status', 'message': 'Creating title...'})}\n\n"
            logger.debug("Generating game title")

            game_title = await generate_game_title(prompt)

            # Save metadata
            arcade_games.game_metadata[game_id] = {
                "title": game_title,
                "created": time.time(),
                "prompt": prompt,
            }
            arcade_games.save_metadata()
            logger.debug(f"Saved metadata for game: {game_title}")

            yield f"data: {json.dumps({'type': 'status', 'message': 'Launching game...'})}\n\n"
            logger.debug("Starting game launch")

            # Launch the game
            if arcade_games.launch_game(game_id):
                logger.debug(f"Game {game_id} launched successfully")
                yield f"data: {json.dumps({'type': 'complete', 'game_id': game_id, 'message': 'Game created and launched!'})}\n\n"
            else:
                logger.error(f"Failed to launch game {game_id}")
                yield f"data: {json.dumps({'type': 'complete', 'message': 'Game created but failed to launch'})}\n\n"

        except Exception as e:
            logger.exception(f"Error in game creation: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/plain",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Content-Type": "text/plain; charset=utf-8",
        },
    )


@app.post("/api/launch-game/{game_id}")
async def launch_game_endpoint(game_id: str):
    """Launch a specific game."""
    arcade_games.cleanup_finished_games()

    if arcade_games.running_games:
        raise HTTPException(status_code=400, detail="Another game is already running")

    if game_id not in arcade_games.game_metadata:
        raise HTTPException(status_code=404, detail="Game not found")

    success = arcade_games.launch_game(game_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to launch game")

    return JSONResponse({"success": True})


@app.get("/api/game-status/{game_id}")
async def game_status(game_id: str):
    """Check if a game is currently running."""
    arcade_games.cleanup_finished_games()
    running = game_id in arcade_games.running_games
    return JSONResponse({"running": running})


@app.delete("/api/delete-game/{game_id}")
async def delete_game_endpoint(game_id: str):
    """Delete a game."""
    if game_id not in arcade_games.game_metadata:
        raise HTTPException(status_code=404, detail="Game not found")

    # Prevent deletion of built-in games
    if game_id in arcade_games.BUILTIN_GAMES:
        raise HTTPException(status_code=403, detail="Cannot delete built-in games")

    # Stop the game if it's running
    if game_id in arcade_games.running_games:
        arcade_games.stop_game(game_id)

    # Delete the file
    game_file = arcade_games.games_dir / f"{game_id}.py"
    if game_file.exists():
        game_file.unlink()

    # Remove from metadata
    del arcade_games.game_metadata[game_id]
    arcade_games.save_metadata()

    return JSONResponse({"success": True})


@app.get("/api/game-metadata/{game_id}")
async def get_game_metadata(game_id: str):
    """Get metadata for a specific game."""
    if game_id not in arcade_games.game_metadata:
        raise HTTPException(status_code=404, detail="Game not found")

    metadata = arcade_games.game_metadata[game_id].copy()

    # For built-in games, hide sensitive information
    if game_id in arcade_games.BUILTIN_GAMES:
        # Remove prompt and other sensitive data for built-in games
        metadata.pop("prompt", None)
        metadata["builtin"] = True

    return JSONResponse(metadata)


@app.post("/api/open-game-file/{game_id}")
async def open_game_file(game_id: str):
    """Open the Python file for a game in the default editor."""
    if game_id not in arcade_games.game_metadata:
        raise HTTPException(status_code=404, detail="Game not found")

    # Prevent opening built-in game files
    if game_id in arcade_games.BUILTIN_GAMES:
        raise HTTPException(
            status_code=403, detail="Cannot view source code of built-in games"
        )

    game_file = arcade_games.games_dir / f"{game_id}.py"
    if not game_file.exists():
        raise HTTPException(status_code=404, detail="Game file not found")

    try:
        # Try to open with the default program (works on Windows, macOS, Linux)
        if sys.platform.startswith("win"):
            subprocess.run(["start", str(game_file)], shell=True, check=True)
        elif sys.platform.startswith("darwin"):  # macOS
            subprocess.run(["open", str(game_file)], check=True)
        else:  # Linux and others
            subprocess.run(["xdg-open", str(game_file)], check=True)

        return JSONResponse({"success": True, "message": "File opened"})
    except Exception as e:
        logger.error(f"Failed to open file {game_file}: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to open file: {str(e)}"
        ) from e


def run_game_file(game_file_path):
    """Run a game file directly - used when executable is called with a game file."""
    try:
        print(f"Lemonade Arcade - Running game: {game_file_path}")

        # Import pygame here, right before we need it
        # pylint: disable=global-statement
        global pygame
        if pygame is None:
            try:
                # pylint: disable=redefined-outer-name
                import pygame

                print(f"Pygame {pygame.version.ver} loaded successfully")
            except ImportError as e:
                print(f"Error: Failed to import pygame: {e}")
                sys.exit(1)

        # Read and execute the game file
        with open(game_file_path, "r", encoding="utf-8") as f:
            game_code = f.read()

        # Execute the game code - pygame should now be available
        # pylint: disable=exec-used
        exec(game_code, {"__name__": "__main__", "__file__": game_file_path})

    except Exception as e:
        print(f"Error running game {game_file_path}: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


def main():
    """Main entry point for the application."""
    # Check if we're being called to run a specific game file
    if len(sys.argv) == 2 and sys.argv[1].endswith(".py"):
        # Game mode: run the specified game file
        run_game_file(sys.argv[1])
        return

    # Server mode: start the Lemonade Arcade server
    import webbrowser
    import threading

    # Keep console visible for debugging and control
    print("Starting Lemonade Arcade...")
    print("Press Ctrl+C to quit")

    port = 8080

    # Start the server in a separate thread
    def run_server():
        print(f"Starting Lemonade Arcade server on http://127.0.0.1:{port}")
        try:
            uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
        except Exception as e:
            print(f"Error starting server: {e}")

    print("Launching server thread...")
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()

    # Wait a moment then open browser
    print("Waiting for server to start...")
    time.sleep(3)
    print(f"Opening browser to http://127.0.0.1:{port}")
    webbrowser.open(f"http://127.0.0.1:{port}")

    try:
        # Keep the main thread alive
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down Lemonade Arcade...")
        # Clean up any running games
        for game_id in list(arcade_games.running_games.keys()):
            arcade_games.stop_game(game_id)


if __name__ == "__main__":
    main()

# Copyright (c) 2025 AMD
