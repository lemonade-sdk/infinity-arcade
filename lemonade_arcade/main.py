#!/usr/bin/env python3
"""
Lemonade Arcade - Main FastAPI application
"""

import asyncio
import json
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
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{LEMONADE_SERVER_URL}/api/v1/models")
            return response.status_code == 200
    except Exception:
        return False


async def get_available_models():
    """Get list of available models from Lemonade Server."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{LEMONADE_SERVER_URL}/api/v1/models")
            if response.status_code == 200:
                data = response.json()
                return [model["id"] for model in data.get("data", [])]
    except Exception:
        pass
    return []


def extract_python_code(llm_response: str) -> Optional[str]:
    """Extract Python code block from LLM response."""
    # Look for code blocks with python/py language specifier
    patterns = [
        r"```python\s*\n(.*?)\n```",
        r"```py\s*\n(.*?)\n```",
        r"```\s*\n(.*?)\n```",  # Generic code block
    ]

    for pattern in patterns:
        match = re.search(pattern, llm_response, re.DOTALL)
        if match:
            code = match.group(1).strip()
            # Basic validation - should contain pygame
            if "pygame" in code.lower():
                return code

    return None


def generate_game_id():
    """Generate a unique game ID."""
    return str(uuid.uuid4())[:8]


def launch_game(game_id: str):
    """Launch a game in a separate process."""
    game_file = GAMES_DIR / f"{game_id}.py"
    if not game_file.exists():
        raise FileNotFoundError(f"Game file not found: {game_file}")

    # Launch the game
    try:
        process = subprocess.Popen([sys.executable, str(game_file)])
        RUNNING_GAMES[game_id] = process
        return True
    except Exception as e:
        print(f"Error launching game {game_id}: {e}")
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
    data = await request.json()
    prompt = data.get("prompt", "")
    model = data.get("model", "")

    if not prompt:
        raise HTTPException(status_code=400, detail="Prompt is required")

    # Generate a unique game ID
    game_id = generate_game_id()

    async def generate():
        try:
            # Send status update
            yield f"data: {json.dumps({'type': 'status', 'message': 'Connecting to LLM...'})}\n\n"

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

            # Stream response from Lemonade Server
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

                    if response.status_code != 200:
                        yield f"data: {json.dumps({'type': 'error', 'message': 'Failed to connect to LLM'})}\n\n"
                        return

                    yield f"data: {json.dumps({'type': 'status', 'message': 'Generating code...'})}\n\n"

                    full_response = ""
                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            try:
                                chunk_data = json.loads(line[6:])
                                if (
                                    "choices" in chunk_data
                                    and len(chunk_data["choices"]) > 0
                                ):
                                    delta = chunk_data["choices"][0].get("delta", {})
                                    if "content" in delta:
                                        content = delta["content"]
                                        full_response += content
                                        yield f"data: {json.dumps({'type': 'content', 'content': content})}\n\n"
                            except json.JSONDecodeError:
                                continue

            # Extract Python code
            yield f"data: {json.dumps({'type': 'status', 'message': 'Extracting code...'})}\n\n"

            python_code = extract_python_code(full_response)
            if not python_code:
                yield f"data: {json.dumps({'type': 'error', 'message': 'Could not extract valid Python code from response'})}\n\n"
                return

            # Save the game
            game_file = GAMES_DIR / f"{game_id}.py"
            with open(game_file, "w", encoding="utf-8") as f:
                f.write(python_code)

            # Extract title from prompt (first few words)
            title_words = prompt.split()[:4]
            game_title = " ".join(title_words).title()
            if len(prompt.split()) > 4:
                game_title += "..."

            # Save metadata
            GAME_METADATA[game_id] = {
                "title": game_title,
                "description": prompt[:100] + ("..." if len(prompt) > 100 else ""),
                "created": time.time(),
            }
            save_metadata()

            yield f"data: {json.dumps({'type': 'status', 'message': 'Launching game...'})}\n\n"

            # Launch the game
            if launch_game(game_id):
                yield f"data: {json.dumps({'type': 'complete', 'game_id': game_id, 'message': 'Game created and launched!'})}\n\n"
            else:
                yield f"data: {json.dumps({'type': 'complete', 'message': 'Game created but failed to launch'})}\n\n"

        except Exception as e:
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
