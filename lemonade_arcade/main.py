#!/usr/bin/env python3
"""
Lemonade Arcade - Main FastAPI application
"""

import asyncio
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# Set up logging
logger = logging.getLogger("lemonade_arcade.main")


app = FastAPI(title="Lemonade Arcade", version="0.1.0")

# Set up static files and templates
STATIC_DIR = Path(__file__).parent / "static"
TEMPLATES_DIR = Path(__file__).parent / "templates"

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Global state
LEMONADE_SERVER_URL = "http://localhost:8000"
GAMES_DIR = Path.home() / ".lemonade-arcade" / "games"
RUNNING_GAMES: Dict[str, subprocess.Popen] = {}
GAME_METADATA: Dict[str, Dict] = {}

# Ensure games directory exists
GAMES_DIR.mkdir(parents=True, exist_ok=True)

# Load existing game metadata
METADATA_FILE = GAMES_DIR / "metadata.json"
if METADATA_FILE.exists():
    try:
        with open(METADATA_FILE, "r") as f:
            GAME_METADATA = json.load(f)
        # Clean up old metadata format - remove descriptions
        updated = False
        for game_id, game_data in GAME_METADATA.items():
            if "description" in game_data:
                del game_data["description"]
                updated = True
        # Save if we made changes
        if updated:
            with open(METADATA_FILE, "w") as f:
                json.dump(GAME_METADATA, f, indent=2)
    except Exception:
        GAME_METADATA = {}


def save_metadata():
    """Save game metadata to disk."""
    try:
        with open(METADATA_FILE, "w") as f:
            json.dump(GAME_METADATA, f, indent=2)
    except Exception as e:
        print(f"Error saving metadata: {e}")


async def check_lemonade_server():
    """Check if Lemonade Server is running."""
    logger.debug(f"Checking Lemonade Server at {LEMONADE_SERVER_URL}")
    try:
        # Use a longer timeout and retry logic for more robust checking
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{LEMONADE_SERVER_URL}/api/v1/models")
            logger.debug(f"Server check response status: {response.status_code}")
            return response.status_code == 200
    except httpx.TimeoutException:
        logger.debug("Server check timed out - server might be busy")
        # Try a simpler health check endpoint if available
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(
                    f"{LEMONADE_SERVER_URL}/health", follow_redirects=True
                )
                logger.debug(f"Health check response status: {response.status_code}")
                return response.status_code == 200
        except Exception as e:
            logger.debug(f"Health check also failed: {e}")
            return False
    except Exception as e:
        logger.debug(f"Server check failed: {e}")
        return False


async def get_available_models():
    """Get list of available models from Lemonade Server."""
    logger.debug("Getting available models from Lemonade Server")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{LEMONADE_SERVER_URL}/api/v1/models")
            if response.status_code == 200:
                data = response.json()
                models = [model["id"] for model in data.get("data", [])]
                logger.debug(f"Found {len(models)} available models: {models}")
                return models
            else:
                logger.warning(f"Failed to get models, status: {response.status_code}")
    except Exception as e:
        logger.debug(f"Error getting models: {e}")
    return []


async def generate_game_title(prompt: str, model: str) -> str:
    """Generate a short title for the game based on the prompt."""
    logger.debug(f"Generating title for prompt: {prompt[:50]}...")

    try:
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
                f"{LEMONADE_SERVER_URL}/api/v1/chat/completions",
                json={
                    "model": model,
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


def launch_game(game_id: str):
    """Launch a game in a separate process."""
    logger.debug(f"Attempting to launch game {game_id}")

    game_file = GAMES_DIR / f"{game_id}.py"
    logger.debug(f"Looking for game file at: {game_file}")

    if not game_file.exists():
        logger.error(f"Game file not found: {game_file}")
        raise FileNotFoundError(f"Game file not found: {game_file}")

    # Launch the game
    try:
        logger.debug(f"Launching Python process: {sys.executable} {game_file}")
        process = subprocess.Popen([sys.executable, str(game_file)])
        RUNNING_GAMES[game_id] = process
        logger.debug(f"Game {game_id} launched successfully with PID {process.pid}")
        return True
    except Exception as e:
        logger.error(f"Error launching game {game_id}: {e}")
        return False


def stop_game(game_id: str):
    """Stop a running game."""
    if game_id in RUNNING_GAMES:
        try:
            process = RUNNING_GAMES[game_id]
            process.terminate()
            # Wait a bit for graceful termination
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
        except Exception as e:
            print(f"Error stopping game {game_id}: {e}")
        finally:
            del RUNNING_GAMES[game_id]


def cleanup_finished_games():
    """Clean up finished game processes."""
    finished = []
    for game_id, process in RUNNING_GAMES.items():
        if process.poll() is not None:  # Process has finished
            finished.append(game_id)

    for game_id in finished:
        del RUNNING_GAMES[game_id]


@app.get("/")
async def root(request: Request):
    """Serve the main HTML page."""
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/api/server-status")
async def server_status():
    """Check if Lemonade Server is online."""
    online = await check_lemonade_server()
    return JSONResponse({"online": online})


@app.get("/api/models")
async def get_models():
    """Get available models from Lemonade Server."""
    models = await get_available_models()
    return JSONResponse(models)


@app.get("/api/games")
async def get_games():
    """Get all saved games."""
    cleanup_finished_games()
    return JSONResponse(GAME_METADATA)


@app.post("/api/create-game")
async def create_game_endpoint(request: Request):
    """Create a new game using LLM."""
    logger.debug("Starting game creation endpoint")

    data = await request.json()
    prompt = data.get("prompt", "")
    model = data.get("model", "")

    logger.debug(f"Received request - prompt: '{prompt[:50]}...', model: '{model}'")

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
                f"Starting request to {LEMONADE_SERVER_URL}/api/v1/chat/completions"
            )
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream(
                    "POST",
                    f"{LEMONADE_SERVER_URL}/api/v1/chat/completions",
                    json={
                        "model": model,
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
            game_file = GAMES_DIR / f"{game_id}.py"
            logger.debug(f"Saving game to: {game_file}")
            with open(game_file, "w", encoding="utf-8") as f:
                f.write(python_code)
            logger.debug("Game file saved successfully")

            # Generate a proper title for the game
            yield f"data: {json.dumps({'type': 'status', 'message': 'Creating title...'})}\n\n"
            logger.debug("Generating game title")

            game_title = await generate_game_title(prompt, model)

            # Save metadata
            GAME_METADATA[game_id] = {
                "title": game_title,
                "created": time.time(),
                "prompt": prompt,
            }
            save_metadata()
            logger.debug(f"Saved metadata for game: {game_title}")

            yield f"data: {json.dumps({'type': 'status', 'message': 'Launching game...'})}\n\n"
            logger.debug("Starting game launch")

            # Launch the game
            if launch_game(game_id):
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
    cleanup_finished_games()

    if RUNNING_GAMES:
        raise HTTPException(status_code=400, detail="Another game is already running")

    if game_id not in GAME_METADATA:
        raise HTTPException(status_code=404, detail="Game not found")

    success = launch_game(game_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to launch game")

    return JSONResponse({"success": True})


@app.get("/api/game-status/{game_id}")
async def game_status(game_id: str):
    """Check if a game is currently running."""
    cleanup_finished_games()
    running = game_id in RUNNING_GAMES
    return JSONResponse({"running": running})


@app.delete("/api/delete-game/{game_id}")
async def delete_game_endpoint(game_id: str):
    """Delete a game."""
    if game_id not in GAME_METADATA:
        raise HTTPException(status_code=404, detail="Game not found")

    # Stop the game if it's running
    if game_id in RUNNING_GAMES:
        stop_game(game_id)

    # Delete the file
    game_file = GAMES_DIR / f"{game_id}.py"
    if game_file.exists():
        game_file.unlink()

    # Remove from metadata
    del GAME_METADATA[game_id]
    save_metadata()

    return JSONResponse({"success": True})


@app.get("/api/game-metadata/{game_id}")
async def get_game_metadata(game_id: str):
    """Get metadata for a specific game."""
    if game_id not in GAME_METADATA:
        raise HTTPException(status_code=404, detail="Game not found")

    return JSONResponse(GAME_METADATA[game_id])


@app.post("/api/open-game-file/{game_id}")
async def open_game_file(game_id: str):
    """Open the Python file for a game in the default editor."""
    if game_id not in GAME_METADATA:
        raise HTTPException(status_code=404, detail="Game not found")

    game_file = GAMES_DIR / f"{game_id}.py"
    if not game_file.exists():
        raise HTTPException(status_code=404, detail="Game file not found")

    try:
        import subprocess
        import sys

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
        raise HTTPException(status_code=500, detail=f"Failed to open file: {str(e)}")


def main():
    """Main entry point for the application."""
    import webbrowser
    import threading

    port = 8080

    # Start the server in a separate thread
    def run_server():
        uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")

    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()

    # Wait a moment then open browser
    time.sleep(2)
    webbrowser.open(f"http://127.0.0.1:{port}")

    try:
        # Keep the main thread alive
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down Lemonade Arcade...")
        # Clean up any running games
        for game_id in list(RUNNING_GAMES.keys()):
            stop_game(game_id)


if __name__ == "__main__":
    main()
