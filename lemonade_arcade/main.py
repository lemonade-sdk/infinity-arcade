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


import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import (
    JSONResponse,
    StreamingResponse,
    RedirectResponse,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.responses import Response

import lemonade_arcade.lemonade_client as lc
from lemonade_arcade.arcade_games import ArcadeGames
from lemonade_arcade.utils import get_resource_path
from lemonade_arcade.llm import (
    generate_game_title,
    ExtractedCode,
    generate_game_code_with_llm,
)

lemonade_handle = lc.LemonadeClient()
arcade_games = ArcadeGames()


# Pygame will be imported on-demand to avoid early DLL loading issues
# pylint: disable=invalid-name
pygame = None

if os.environ.get("LEMONADE_ARCADE_MODEL"):
    REQUIRED_MODEL = os.environ.get("LEMONADE_ARCADE_MODEL")
else:
    REQUIRED_MODEL = "Qwen3-Coder-30B-A3B-Instruct-GGUF"

# Logger will be configured by CLI or set to INFO if run directly
logger = logging.getLogger("lemonade_arcade.main")


app = FastAPI(title="Lemonade Arcade", version="0.1.0")

# Set up static files and templates
STATIC_DIR = get_resource_path("static")
TEMPLATES_DIR = get_resource_path("templates")


class NoCacheStaticFiles(StaticFiles):
    """Custom StaticFiles class with no-cache headers"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def file_response(self, *args, **kwargs) -> Response:
        response = super().file_response(*args, **kwargs)
        # Add no-cache headers for all static files
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response


app.mount("/static", NoCacheStaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


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


def generate_next_version_title(original_title: str) -> str:
    """Generate the next version number for a remixed game title."""
    # Check if the title already has a version number

    version_match = re.search(r" v(\d+)$", original_title)

    if version_match:
        # Extract current version number and increment
        current_version = int(version_match.group(1))
        next_version = current_version + 1
        # Replace the version number
        base_title = original_title[: version_match.start()]
        return f"{base_title} v{next_version}"
    else:
        # No version number, add v2
        return f"{original_title} v2"


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

            # Use the centralized function to generate game code
            yield f"data: {json.dumps({'type': 'status', 'message': 'Generating code...'})}\n\n"

            python_code = None
            async for result in generate_game_code_with_llm(
                lemonade_handle, REQUIRED_MODEL, "create", prompt
            ):
                if result is None:
                    # Error occurred in the LLM function
                    logger.error("Error in generate_game_code_with_llm")
                    error_data = {"type": "error", "message": "Failed to generate code"}
                    yield f"data: {json.dumps(error_data)}\n\n"
                    return
                elif isinstance(result, ExtractedCode):
                    # This is the final extracted code from extract_python_code
                    python_code = result.code
                    logger.debug(f"Received final code, length: {len(python_code)}")
                    break
                elif isinstance(result, str):
                    # This is a content chunk, stream it to the client
                    content_data = {"type": "content", "content": result}
                    yield f"data: {json.dumps(content_data)}\n\n"

            # Verify we got the code
            if not python_code:
                logger.error(
                    "Could not get Python code from generate_game_code_with_llm"
                )
                error_msg = "Could not extract valid Python code from response"
                error_data = {"type": "error", "message": error_msg}
                yield f"data: {json.dumps(error_data)}\n\n"
                return

            yield f"data: {json.dumps({'type': 'status', 'message': 'Extracting code...'})}\n\n"
            logger.debug("Code extraction completed")

            logger.debug(
                f"Successfully extracted Python code, length: {len(python_code)}"
            )

            game_title = await generate_game_title(
                lemonade_handle, REQUIRED_MODEL, prompt
            )

            # Create and launch the game using ArcadeGames
            # We'll use async generator delegation to stream from create_and_launch_game
            async for stream_item in arcade_games.create_and_launch_game_with_streaming(
                lemonade_handle,
                REQUIRED_MODEL,
                game_id,
                python_code,
                prompt,
                game_title=game_title,
            ):
                yield stream_item

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


@app.post("/api/remix-game")
async def remix_game_endpoint(request: Request):
    """Remix an existing game using LLM."""
    logger.debug("Starting game remix endpoint")

    data = await request.json()
    game_id = data.get("game_id", "")
    remix_prompt = data.get("remix_prompt", "")

    logger.debug(
        f"Received remix request - game_id: '{game_id}', remix_prompt: '{remix_prompt[:50]}...'"
    )

    if not game_id or not remix_prompt:
        logger.error("Game ID and remix prompt are required")
        raise HTTPException(
            status_code=400, detail="Game ID and remix prompt are required"
        )

    # Check if the game exists
    if game_id not in arcade_games.game_metadata:
        logger.error(f"Game not found: {game_id}")
        raise HTTPException(status_code=404, detail="Game not found")

    # Prevent remixing built-in games
    if game_id in arcade_games.builtin_games:
        logger.error(f"Cannot remix built-in game: {game_id}")
        raise HTTPException(status_code=403, detail="Cannot remix built-in games")

    # Generate a unique game ID for the remixed version
    new_game_id = generate_game_id()
    logger.debug(f"Generated new game ID for remix: {new_game_id}")

    async def generate():
        try:
            logger.debug("Starting remix generate() function")
            # Send status update
            yield f"data: {json.dumps({'type': 'status', 'message': 'Connecting to LLM...'})}\n\n"
            logger.debug("Sent 'Connecting to LLM...' status")

            # Read the original game code
            original_game_file = arcade_games.games_dir / f"{game_id}.py"
            if not original_game_file.exists():
                logger.error(f"Original game file not found: {original_game_file}")
                error_data = {
                    "type": "error",
                    "message": "Original game file not found",
                }
                yield f"data: {json.dumps(error_data)}\n\n"
                return

            with open(original_game_file, "r", encoding="utf-8") as f:
                original_code = f.read()

            logger.debug(f"Read original game code, length: {len(original_code)}")

            # Use the centralized function to remix the game code
            yield f"data: {json.dumps({'type': 'status', 'message': 'Remixing code...'})}\n\n"

            remixed_code = None
            async for result in generate_game_code_with_llm(
                lemonade_handle, REQUIRED_MODEL, "remix", original_code, remix_prompt
            ):
                if result is None:
                    # Error occurred in the LLM function
                    logger.error("Error in generate_game_code_with_llm during remix")
                    error_data = {"type": "error", "message": "Failed to remix code"}
                    yield f"data: {json.dumps(error_data)}\n\n"
                    return
                elif isinstance(result, ExtractedCode):
                    # This is the final extracted code from extract_python_code
                    remixed_code = result.code
                    logger.debug(f"Received remixed code, length: {len(remixed_code)}")
                    break
                elif isinstance(result, str):
                    # This is a content chunk, stream it to the client
                    content_data = {"type": "content", "content": result}
                    yield f"data: {json.dumps(content_data)}\n\n"

            # Verify we got the remixed code
            if not remixed_code:
                logger.error(
                    "Could not get remixed Python code from generate_game_code_with_llm"
                )
                error_msg = "Could not extract valid Python code from remix response"
                error_data = {"type": "error", "message": error_msg}
                yield f"data: {json.dumps(error_data)}\n\n"
                return

            # pylint: disable=line-too-long
            yield f"data: {json.dumps({'type': 'status', 'message': 'Extracting remixed code...'})}\n\n"
            logger.debug("Remix code extraction completed")

            logger.debug(
                f"Successfully extracted remixed Python code, length: {len(remixed_code)}"
            )

            # Generate new title with version number
            original_title = arcade_games.game_metadata[game_id].get(
                "title", "Untitled Game"
            )
            new_title = generate_next_version_title(original_title)

            # Create the remix prompt for metadata
            full_remix_prompt = f"Remix of '{original_title}': {remix_prompt}"

            # Create and launch the remixed game using ArcadeGames
            async for stream_item in arcade_games.create_and_launch_game_with_streaming(
                lemonade_handle,
                REQUIRED_MODEL,
                new_game_id,
                remixed_code,
                full_remix_prompt,
                new_title,
                is_remix=True,
            ):
                yield stream_item

        except Exception as e:
            logger.exception(f"Error in game remix: {e}")
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
    """Launch a specific game with streaming support for error fixes."""
    arcade_games.cleanup_finished_games()

    if arcade_games.running_games:
        raise HTTPException(status_code=400, detail="Another game is already running")

    if game_id not in arcade_games.game_metadata:
        raise HTTPException(status_code=404, detail="Game not found")

    # Get game title for better messaging
    game_title = arcade_games.game_metadata.get(game_id, {}).get("title", game_id)

    async def generate():
        try:
            # Stream the launch process with potential error fixing
            async for stream_item in arcade_games.launch_game_with_streaming(
                lemonade_handle, REQUIRED_MODEL, game_id, game_title, max_retries=1
            ):
                yield stream_item

        except Exception as e:
            logger.exception(f"Error in game launch: {e}")
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
    if game_id in arcade_games.builtin_games:
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
    if game_id in arcade_games.builtin_games:
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
    if game_id in arcade_games.builtin_games:
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
    # Configure logging if not already configured (when run directly, not via CLI)
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )
        # Suppress noisy httpcore debug messages
        logging.getLogger("httpcore").setLevel(logging.WARNING)
        logging.getLogger("httpx").setLevel(logging.WARNING)

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
