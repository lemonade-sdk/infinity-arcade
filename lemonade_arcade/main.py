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
from lemonade_arcade.game_launcher import GameLauncher
from lemonade_arcade.game_orchestrator import GameOrchestrator
from lemonade_arcade.llm_service import LLMService

# Minimum required version of lemonade-server
LEMONADE_MINIMUM_VERSION = "8.1.10"


# Pygame will be imported on-demand to avoid early DLL loading issues
# pylint: disable=invalid-name
pygame = None

# Logger will be configured by CLI or set to INFO if run directly
logger = logging.getLogger("lemonade_arcade.main")


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


class ArcadeApp:
    """Encapsulates app state, services, and route registration."""

    def __init__(self) -> None:
        # Initialize basic components first
        self.lemonade_handle = lc.LemonadeClient(
            minimum_version=LEMONADE_MINIMUM_VERSION
        )
        self.arcade_games = ArcadeGames()
        self.game_launcher = GameLauncher()

        # Model will be determined asynchronously
        self.required_model = None
        self.required_model_size = None
        self.llm_service = None
        self.orchestrator = None

        # FastAPI app and resources
        self.app = FastAPI(title="Lemonade Arcade", version="0.1.0")
        self.static_dir = get_resource_path("static")
        self.templates_dir = get_resource_path("templates")
        self.templates = Jinja2Templates(directory=str(self.templates_dir))

        self.app.mount(
            "/static", NoCacheStaticFiles(directory=str(self.static_dir)), name="static"
        )

        # Register endpoints
        self._register_routes()

    async def initialize_model_and_services(self) -> None:
        """Initialize model selection and dependent services asynchronously."""
        # Determine required model
        if os.environ.get("LEMONADE_ARCADE_MODEL"):
            self.required_model = os.environ.get("LEMONADE_ARCADE_MODEL")
            self.required_model_size = None  # Unknown size for custom models
            logger.info(f"Using model from environment variable: {self.required_model}")
        else:
            # Use hardware-based selection with caching in the arcade directory
            cache_dir = str(self.arcade_games.games_dir.parent)  # ~/.lemonade-arcade
            self.required_model, self.required_model_size = (
                await self.lemonade_handle.select_model_for_hardware(
                    cache_dir=cache_dir
                )
            )
            logger.info(
                f"Selected model based on hardware: {self.required_model} ({self.required_model_size} GB)"
            )

        # Initialize services that depend on the model
        self.llm_service = LLMService(self.lemonade_handle, self.required_model)
        self.orchestrator = GameOrchestrator(
            self.arcade_games, self.game_launcher, self.llm_service
        )

    @staticmethod
    def generate_game_id() -> str:
        return str(uuid.uuid4())[:8]

    @staticmethod
    def generate_next_version_title(original_title: str) -> str:
        version_match = re.search(r" v(\d+)$", original_title)
        if version_match:
            current_version = int(version_match.group(1))
            next_version = current_version + 1
            base_title = original_title[: version_match.start()]
            return f"{base_title} v{next_version}"
        else:
            return f"{original_title} v2"

    def _register_routes(self) -> None:
        @self.app.get("/")
        async def root(request: Request):
            return self.templates.TemplateResponse("index.html", {"request": request})

        @self.app.get("/favicon.ico")
        async def favicon():
            return RedirectResponse(url="/static/favicon.ico")

        @self.app.get("/api/server-status")
        async def server_status():
            online = await self.lemonade_handle.check_lemonade_server_api()
            return JSONResponse({"online": online})

        @self.app.get("/api/selected-model")
        async def selected_model():
            # Initialize model selection if not done yet
            if self.required_model is None:
                await self.initialize_model_and_services()

            response = {"model_name": self.required_model}
            if self.required_model_size is not None:
                response["size_gb"] = self.required_model_size
                response["size_display"] = f"{self.required_model_size} GB"
            return JSONResponse(response)

        @self.app.get("/api/games")
        async def get_games():
            self.game_launcher.cleanup_finished_games()
            return JSONResponse(self.arcade_games.game_metadata)

        @self.app.get("/api/installation-status")
        async def installation_status():
            logger.info("Installation status endpoint called")
            version_info = await self.lemonade_handle.check_lemonade_server_version()
            logger.info(f"Version check result: {version_info}")
            result = {
                "installed": version_info["installed"],
                "version": version_info["version"],
                "compatible": version_info["compatible"],
                "required_version": version_info["required_version"],
            }
            logger.info(f"Returning installation status: {result}")
            return JSONResponse(result)

        @self.app.get("/api/server-running-status")
        async def server_running_status():
            logger.info("=== Server running status endpoint called ===")
            is_running = await self.lemonade_handle.check_lemonade_server_running()
            logger.info(f"Initial running check result: {is_running}")
            if not is_running:
                logger.info("Server not running, attempting to start automatically...")
                start_result = await self.lemonade_handle.start_lemonade_server()
                logger.info(f"Auto-start result: {start_result}")
                if start_result["success"]:
                    import asyncio

                    logger.info("Waiting 2 seconds for server to initialize...")
                    await asyncio.sleep(2)
                    is_running = (
                        await self.lemonade_handle.check_lemonade_server_running()
                    )
                    logger.info(f"Running check after auto-start: {is_running}")
                else:
                    logger.warning(
                        f"Auto-start failed: {start_result.get('error', 'Unknown error')}"
                    )
            result = {"running": is_running}
            logger.info(f"=== Returning server running status: {result} ===")
            return JSONResponse(result)

        @self.app.get("/api/api-connection-status")
        async def api_connection_status():
            logger.info("=== API connection status endpoint called ===")
            api_online = await self.lemonade_handle.check_lemonade_server_api()
            logger.info(f"API online check result: {api_online}")
            result = {"api_online": api_online}
            logger.info(f"=== Returning API connection status: {result} ===")
            return JSONResponse(result)

        @self.app.get("/api/model-installation-status")
        async def model_installation_status():
            logger.info("Model installation status endpoint called")
            model_status = await self.lemonade_handle.check_model_installed(
                self.required_model
            )
            logger.info(f"Model check result: {model_status}")
            result = {
                "model_installed": model_status["installed"],
                "model_name": model_status["model_name"],
            }
            logger.info(f"Returning model installation status: {result}")
            return JSONResponse(result)

        @self.app.get("/api/model-loading-status")
        async def model_loading_status():
            logger.info("Model loading status endpoint called")
            model_loaded_status = await self.lemonade_handle.check_model_loaded(
                self.required_model
            )
            logger.info(f"Model loaded check result: {model_loaded_status}")
            result = {
                "model_loaded": model_loaded_status["loaded"],
                "model_name": model_loaded_status["model_name"],
                "current_model": model_loaded_status["current_model"],
            }
            logger.info(f"Returning model loading status: {result}")
            return JSONResponse(result)

        @self.app.get("/api/installation-environment")
        async def installation_environment():
            logger.info("Installation environment endpoint called")
            is_pyinstaller = self.lemonade_handle.is_pyinstaller_environment()
            sdk_available = (
                await self.lemonade_handle.check_lemonade_sdk_available()
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

        @self.app.post("/api/refresh-environment")
        async def refresh_environment_endpoint():
            logger.info("Refresh environment endpoint called")
            try:
                self.lemonade_handle.refresh_environment()
                self.lemonade_handle.reset_server_state()
                return JSONResponse(
                    {"success": True, "message": "Environment refreshed"}
                )
            except Exception as e:
                logger.error(f"Failed to refresh environment: {e}")
                return JSONResponse(
                    {"success": False, "message": f"Failed to refresh environment: {e}"}
                )

        @self.app.post("/api/install-server")
        async def install_server():
            logger.info("Install server endpoint called")
            result = await self.lemonade_handle.download_and_install_lemonade_server()
            logger.info(f"Install result: {result}")
            return JSONResponse(result)

        @self.app.post("/api/start-server")
        async def start_server():
            logger.info("Start server endpoint called")
            result = await self.lemonade_handle.start_lemonade_server()
            logger.info(f"Start server result: {result}")
            return JSONResponse(result)

        @self.app.post("/api/install-model")
        async def install_model():
            logger.info("Install model endpoint called")
            result = await self.lemonade_handle.install_model(self.required_model)
            logger.info(f"Install model result: {result}")
            return JSONResponse(result)

        @self.app.post("/api/load-model")
        async def load_model():
            logger.info("Load model endpoint called")
            result = await self.lemonade_handle.load_model(self.required_model)
            logger.info(f"Load model result: {result}")
            return JSONResponse(result)

        @self.app.post("/api/create-game")
        async def create_game_endpoint(request: Request):
            logger.debug("Starting game creation endpoint")
            data = await request.json()
            prompt = data.get("prompt", "")
            logger.debug(f"Received request - prompt: '{prompt[:50]}...'")
            if not prompt:
                logger.error("No prompt provided")
                raise HTTPException(status_code=400, detail="Prompt is required")
            game_id = self.generate_game_id()
            logger.debug(f"Generated game ID: {game_id}")

            async def generate():
                try:
                    async for (
                        stream_item
                    ) in self.orchestrator.create_and_launch_game_with_streaming(
                        game_id, prompt
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

        @self.app.post("/api/remix-game")
        async def remix_game_endpoint(request: Request):
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
            if game_id not in self.arcade_games.game_metadata:
                logger.error(f"Game not found: {game_id}")
                raise HTTPException(status_code=404, detail="Game not found")
            if game_id in self.arcade_games.builtin_games:
                logger.error(f"Cannot remix built-in game: {game_id}")
                raise HTTPException(
                    status_code=403, detail="Cannot remix built-in games"
                )
            new_game_id = self.generate_game_id()
            logger.debug(f"Generated new game ID for remix: {new_game_id}")

            async def generate():
                try:
                    original_title = self.arcade_games.game_metadata[game_id].get(
                        "title", "Untitled Game"
                    )
                    new_title = self.generate_next_version_title(original_title)
                    async for (
                        stream_item
                    ) in self.orchestrator.remix_and_launch_game_with_streaming(
                        game_id, new_game_id, remix_prompt, new_title
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

        @self.app.post("/api/launch-game/{game_id}")
        async def launch_game_endpoint(game_id: str):
            self.game_launcher.cleanup_finished_games()
            if self.game_launcher.running_games:
                raise HTTPException(
                    status_code=400, detail="Another game is already running"
                )
            if game_id not in self.arcade_games.game_metadata:
                raise HTTPException(status_code=404, detail="Game not found")
            game_title = self.arcade_games.game_metadata.get(game_id, {}).get(
                "title", game_id
            )

            async def generate():
                try:
                    async for (
                        stream_item
                    ) in self.orchestrator.launch_game_with_auto_fix_streaming(
                        game_id, game_title, max_retries=1
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

        @self.app.get("/api/game-status/{game_id}")
        async def game_status(game_id: str):
            self.game_launcher.cleanup_finished_games()
            running = game_id in self.game_launcher.running_games
            return JSONResponse({"running": running})

        @self.app.delete("/api/delete-game/{game_id}")
        async def delete_game_endpoint(game_id: str):
            if game_id not in self.arcade_games.game_metadata:
                raise HTTPException(status_code=404, detail="Game not found")
            if game_id in self.arcade_games.builtin_games:
                raise HTTPException(
                    status_code=403, detail="Cannot delete built-in games"
                )
            if game_id in self.game_launcher.running_games:
                self.game_launcher.stop_game(game_id)
            game_file = self.arcade_games.games_dir / f"{game_id}.py"
            if game_file.exists():
                game_file.unlink()
            del self.arcade_games.game_metadata[game_id]
            self.arcade_games.save_metadata()
            return JSONResponse({"success": True})

        @self.app.get("/api/game-metadata/{game_id}")
        async def get_game_metadata(game_id: str):
            if game_id not in self.arcade_games.game_metadata:
                raise HTTPException(status_code=404, detail="Game not found")
            metadata = self.arcade_games.game_metadata[game_id].copy()
            if game_id in self.arcade_games.builtin_games:
                metadata.pop("prompt", None)
                metadata["builtin"] = True
            return JSONResponse(metadata)

        @self.app.post("/api/open-game-file/{game_id}")
        async def open_game_file(game_id: str):
            if game_id not in self.arcade_games.game_metadata:
                raise HTTPException(status_code=404, detail="Game not found")
            if game_id in self.arcade_games.builtin_games:
                raise HTTPException(
                    status_code=403, detail="Cannot view source code of built-in games"
                )
            game_file = self.arcade_games.games_dir / f"{game_id}.py"
            if not game_file.exists():
                raise HTTPException(status_code=404, detail="Game file not found")
            try:
                if sys.platform.startswith("win"):
                    subprocess.run(["start", str(game_file)], shell=True, check=True)
                elif sys.platform.startswith("darwin"):
                    subprocess.run(["open", str(game_file)], check=True)
                else:
                    subprocess.run(["xdg-open", str(game_file)], check=True)
                return JSONResponse({"success": True, "message": "File opened"})
            except Exception as e:
                logger.error(f"Failed to open file {game_file}: {e}")
                raise HTTPException(
                    status_code=500, detail=f"Failed to open file: {str(e)}"
                ) from e


arcade_app = ArcadeApp()
app = arcade_app.app


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
    import asyncio

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
        for game_id in list(arcade_app.game_launcher.running_games.keys()):
            arcade_app.game_launcher.stop_game(game_id)


if __name__ == "__main__":
    main()

# Copyright (c) 2025 AMD
