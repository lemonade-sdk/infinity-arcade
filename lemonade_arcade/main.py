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
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles


app = FastAPI(title="Lemonade Arcade", version="0.1.0")

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
async def root():
    """Serve the main HTML page."""
    html_content = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Lemonade Arcade</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Courier New', monospace;
            background: linear-gradient(135deg, #0a0a0a 0%, #1a1a2e 50%, #16213e 100%);
            color: #00ff41;
            min-height: 100vh;
            overflow-x: hidden;
        }
        
        .container {
            display: grid;
            grid-template-columns: 1fr 350px;
            grid-template-rows: auto 1fr auto;
            min-height: 100vh;
            gap: 20px;
            padding: 20px;
        }
        
        .header {
            grid-column: 1 / -1;
            text-align: center;
            position: relative;
        }
        
        .title {
            font-size: 3rem;
            font-weight: bold;
            text-shadow: 0 0 20px #00ff41, 0 0 40px #00ff41;
            letter-spacing: 8px;
            margin: 20px 0;
            font-family: monospace;
        }
        
        .server-status {
            position: absolute;
            top: 10px;
            right: 10px;
            display: flex;
            align-items: center;
            gap: 10px;
            background: rgba(0, 0, 0, 0.7);
            padding: 10px 15px;
            border-radius: 25px;
            border: 2px solid #00ff41;
        }
        
        .status-indicator {
            width: 12px;
            height: 12px;
            border-radius: 50%;
            animation: pulse 2s infinite;
        }
        
        .status-online {
            background: #00ff41;
            box-shadow: 0 0 10px #00ff41;
        }
        
        .status-offline {
            background: #ff4444;
            box-shadow: 0 0 10px #ff4444;
        }
        
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
        
        .main-content {
            display: flex;
            flex-direction: column;
            gap: 20px;
        }
        
        .game-library {
            background: rgba(0, 0, 0, 0.8);
            border: 2px solid #00ff41;
            border-radius: 10px;
            padding: 20px;
            flex: 1;
            min-height: 400px;
        }
        
        .library-title {
            font-size: 1.5rem;
            margin-bottom: 20px;
            text-align: center;
            text-transform: uppercase;
            letter-spacing: 2px;
        }
        
        .games-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
            gap: 15px;
        }
        
        .game-item {
            background: linear-gradient(145deg, #1a1a2e, #16213e);
            border: 2px solid #00ff41;
            border-radius: 15px;
            padding: 20px;
            text-align: center;
            cursor: pointer;
            transition: all 0.3s ease;
            position: relative;
            overflow: hidden;
        }
        
        .game-item:hover {
            transform: translateY(-5px);
            box-shadow: 0 10px 30px rgba(0, 255, 65, 0.3);
            border-color: #00ffff;
        }
        
        .game-item.running {
            border-color: #ffff00;
            background: linear-gradient(145deg, #2e2e1a, #3e3e16);
        }
        
        .delete-btn {
            position: absolute;
            top: 5px;
            right: 5px;
            width: 25px;
            height: 25px;
            background: #ff4444;
            border: none;
            border-radius: 50%;
            color: white;
            cursor: pointer;
            opacity: 0;
            transition: opacity 0.3s ease;
            font-size: 14px;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        
        .game-item:hover .delete-btn {
            opacity: 1;
        }
        
        .delete-btn:hover {
            background: #ff0000;
        }
        
        .game-title {
            font-size: 1.1rem;
            font-weight: bold;
            margin-bottom: 10px;
            word-wrap: break-word;
        }
        
        .game-description {
            font-size: 0.8rem;
            opacity: 0.8;
            line-height: 1.4;
        }
        
        .sidecar {
            background: rgba(0, 0, 0, 0.9);
            border: 2px solid #00ff41;
            border-radius: 10px;
            padding: 20px;
            display: flex;
            flex-direction: column;
            max-height: calc(100vh - 200px);
        }
        
        .sidecar-title {
            font-size: 1.2rem;
            margin-bottom: 15px;
            text-align: center;
            text-transform: uppercase;
            letter-spacing: 1px;
        }
        
        .llm-output {
            flex: 1;
            background: #000;
            border: 1px solid #333;
            border-radius: 5px;
            padding: 15px;
            overflow-y: auto;
            font-size: 0.9rem;
            line-height: 1.5;
            white-space: pre-wrap;
            word-wrap: break-word;
        }
        
        .input-area {
            grid-column: 1 / -1;
            background: rgba(0, 0, 0, 0.8);
            border: 2px solid #00ff41;
            border-radius: 10px;
            padding: 20px;
            display: flex;
            gap: 15px;
            align-items: center;
        }
        
        .model-select {
            background: #1a1a2e;
            border: 2px solid #00ff41;
            border-radius: 5px;
            color: #00ff41;
            padding: 12px;
            font-family: inherit;
            min-width: 200px;
        }
        
        .prompt-input {
            flex: 1;
            background: #000;
            border: 2px solid #00ff41;
            border-radius: 5px;
            color: #00ff41;
            padding: 12px;
            font-family: inherit;
            font-size: 1rem;
        }
        
        .prompt-input:focus {
            outline: none;
            box-shadow: 0 0 10px rgba(0, 255, 65, 0.5);
        }
        
        .create-btn {
            background: linear-gradient(145deg, #00ff41, #00cc33);
            border: none;
            border-radius: 5px;
            color: #000;
            padding: 12px 25px;
            font-family: inherit;
            font-weight: bold;
            cursor: pointer;
            transition: all 0.3s ease;
            text-transform: uppercase;
            letter-spacing: 1px;
        }
        
        .create-btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(0, 255, 65, 0.4);
        }
        
        .create-btn:disabled {
            background: #333;
            color: #666;
            cursor: not-allowed;
            transform: none;
            box-shadow: none;
        }
        
        .spinner {
            display: none;
            text-align: center;
            padding: 20px;
        }
        
        .spinner.active {
            display: block;
        }
        
        .spinner-circle {
            width: 40px;
            height: 40px;
            border: 4px solid #333;
            border-top: 4px solid #00ff41;
            border-radius: 50%;
            animation: spin 1s linear infinite;
            margin: 0 auto 10px;
        }
        
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        
        .status-text {
            font-size: 1.1rem;
            color: #00ff41;
            margin-top: 10px;
        }
        
        .error-message {
            background: rgba(255, 68, 68, 0.1);
            border: 2px solid #ff4444;
            border-radius: 5px;
            color: #ff4444;
            padding: 15px;
            margin: 10px 0;
        }
        
        .get-lemonade-link {
            color: #00ffff;
            text-decoration: none;
            font-weight: bold;
        }
        
        .get-lemonade-link:hover {
            text-decoration: underline;
        }
        
        .empty-library {
            text-align: center;
            color: #666;
            font-style: italic;
            padding: 40px;
        }
        
        @media (max-width: 768px) {
            .container {
                grid-template-columns: 1fr;
                grid-template-rows: auto auto 1fr auto;
            }
            
            .sidecar {
                order: 2;
                max-height: 300px;
            }
            
            .main-content {
                order: 3;
            }
            
            .title {
                font-size: 2rem;
                letter-spacing: 4px;
            }
            
            .input-area {
                flex-direction: column;
                gap: 10px;
            }
            
            .model-select {
                min-width: auto;
                width: 100%;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="server-status" id="serverStatus">
                <div class="status-indicator status-offline" id="statusIndicator"></div>
                <span id="statusText">Checking...</span>
            </div>
            <div class="title">
                ██╗     ███████╗███╗   ███╗ ██████╗ ███╗   ██╗ █████╗ ██████╗ ███████╗<br>
                ██║     ██╔════╝████╗ ████║██╔═══██╗████╗  ██║██╔══██╗██╔══██╗██╔════╝<br>
                ██║     █████╗  ██╔████╔██║██║   ██║██╔██╗ ██║███████║██║  ██║█████╗<br>
                ██║     ██╔══╝  ██║╚██╔╝██║██║   ██║██║╚██╗██║██╔══██║██║  ██║██╔══╝<br>
                ███████╗███████╗██║ ╚═╝ ██║╚██████╔╝██║ ╚████║██║  ██║██████╔╝███████╗<br>
                ╚══════╝╚══════╝╚═╝     ╚═╝ ╚═════╝ ╚═╝  ╚═══╝╚═╝  ╚═╝╚═════╝ ╚══════╝<br>
                <br>
                 █████╗ ██████╗  ██████╗ █████╗ ██████╗ ███████╗<br>
                ██╔══██╗██╔══██╗██╔════╝██╔══██╗██╔══██╗██╔════╝<br>
                ███████║██████╔╝██║     ███████║██║  ██║█████╗<br>
                ██╔══██║██╔══██╗██║     ██╔══██║██║  ██║██╔══╝<br>
                ██║  ██║██║  ██║╚██████╗██║  ██║██████╔╝███████╗<br>
                ╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝╚═╝  ╚═╝╚═════╝ ╚══════╝
            </div>
        </div>
        
        <div class="main-content">
            <div class="game-library">
                <div class="library-title">Game Library</div>
                <div class="spinner" id="gameSpinner">
                    <div class="spinner-circle"></div>
                    <div class="status-text" id="spinnerStatus">Generating game...</div>
                </div>
                <div class="games-grid" id="gamesGrid">
                    <div class="empty-library">
                        No games yet. Create your first game below!
                    </div>
                </div>
            </div>
        </div>
        
        <div class="sidecar">
            <div class="sidecar-title">LLM Output</div>
            <div class="llm-output" id="llmOutput">Ready to generate games...</div>
        </div>
        
        <div class="input-area">
            <select class="model-select" id="modelSelect">
                <option>Loading models...</option>
            </select>
            <input type="text" class="prompt-input" id="promptInput" 
                   placeholder="Describe the game you want to create (e.g., 'snake but the food moves')" />
            <button class="create-btn" id="createBtn" onclick="createGame()">Create Game</button>
        </div>
    </div>
    
    <script>
        let isGenerating = false;
        let games = {};
        let runningGameId = null;
        
        // Check server status periodically
        async function checkServerStatus() {
            try {
                const response = await fetch('/api/server-status');
                const data = await response.json();
                const indicator = document.getElementById('statusIndicator');
                const statusText = document.getElementById('statusText');
                
                if (data.online) {
                    indicator.className = 'status-indicator status-online';
                    statusText.innerHTML = '🍋 Lemonade Server Online';
                } else {
                    indicator.className = 'status-indicator status-offline';
                    statusText.innerHTML = `Server Offline - <a href="https://lemonade-server.ai" target="_blank" class="get-lemonade-link">Get Lemonade</a>`;
                }
            } catch (error) {
                const indicator = document.getElementById('statusIndicator');
                const statusText = document.getElementById('statusText');
                indicator.className = 'status-indicator status-offline';
                statusText.innerHTML = `Connection Error - <a href="https://lemonade-server.ai" target="_blank" class="get-lemonade-link">Get Lemonade</a>`;
            }
        }
        
        // Load available models
        async function loadModels() {
            try {
                const response = await fetch('/api/models');
                const models = await response.json();
                const select = document.getElementById('modelSelect');
                
                select.innerHTML = '';
                if (models.length === 0) {
                    select.innerHTML = '<option>No models available</option>';
                } else {
                    models.forEach(model => {
                        const option = document.createElement('option');
                        option.value = model;
                        option.textContent = model;
                        select.appendChild(option);
                    });
                }
            } catch (error) {
                document.getElementById('modelSelect').innerHTML = '<option>Error loading models</option>';
            }
        }
        
        // Load existing games
        async function loadGames() {
            try {
                const response = await fetch('/api/games');
                games = await response.json();
                renderGames();
            } catch (error) {
                console.error('Error loading games:', error);
            }
        }
        
        // Render games in the library
        function renderGames() {
            const grid = document.getElementById('gamesGrid');
            
            if (Object.keys(games).length === 0) {
                grid.innerHTML = '<div class="empty-library">No games yet. Create your first game below!</div>';
                return;
            }
            
            grid.innerHTML = '';
            Object.entries(games).forEach(([gameId, gameData]) => {
                const gameItem = document.createElement('div');
                gameItem.className = 'game-item';
                if (runningGameId === gameId) {
                    gameItem.classList.add('running');
                }
                
                gameItem.innerHTML = `
                    <button class="delete-btn" onclick="deleteGame('${gameId}')">&times;</button>
                    <div class="game-title">${gameData.title}</div>
                    <div class="game-description">${gameData.description}</div>
                `;
                
                gameItem.addEventListener('click', (e) => {
                    if (!e.target.classList.contains('delete-btn')) {
                        launchGame(gameId);
                    }
                });
                
                grid.appendChild(gameItem);
            });
        }
        
        // Create a new game
        async function createGame() {
            const prompt = document.getElementById('promptInput').value.trim();
            const model = document.getElementById('modelSelect').value;
            
            if (!prompt || isGenerating) return;
            
            if (runningGameId) {
                alert('Please close the running game before creating a new one.');
                return;
            }
            
            isGenerating = true;
            document.getElementById('createBtn').disabled = true;
            document.getElementById('gameSpinner').classList.add('active');
            document.getElementById('gamesGrid').style.display = 'none';
            document.getElementById('llmOutput').textContent = '';
            
            try {
                const response = await fetch('/api/create-game', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        prompt: prompt,
                        model: model
                    })
                });
                
                if (!response.ok) {
                    throw new Error('Failed to create game');
                }
                
                const reader = response.body.getReader();
                const decoder = new TextDecoder();
                let fullResponse = '';
                
                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;
                    
                    const chunk = decoder.decode(value);
                    const lines = chunk.split('\\n');
                    
                    for (const line of lines) {
                        if (line.startsWith('data: ')) {
                            try {
                                const data = JSON.parse(line.slice(6));
                                if (data.type === 'content') {
                                    fullResponse += data.content;
                                    document.getElementById('llmOutput').textContent = fullResponse;
                                    document.getElementById('llmOutput').scrollTop = document.getElementById('llmOutput').scrollHeight;
                                } else if (data.type === 'status') {
                                    document.getElementById('spinnerStatus').textContent = data.message;
                                } else if (data.type === 'complete') {
                                    // Game created successfully
                                    await loadGames();
                                    document.getElementById('promptInput').value = '';
                                    if (data.game_id) {
                                        runningGameId = data.game_id;
                                        renderGames();
                                    }
                                }
                            } catch (e) {
                                // Ignore JSON parse errors for partial chunks
                            }
                        }
                    }
                }
            } catch (error) {
                document.getElementById('llmOutput').innerHTML = `<div class="error-message">Error: ${error.message}</div>`;
            } finally {
                isGenerating = false;
                document.getElementById('createBtn').disabled = false;
                document.getElementById('gameSpinner').classList.remove('active');
                document.getElementById('gamesGrid').style.display = 'grid';
            }
        }
        
        // Launch a game
        async function launchGame(gameId) {
            if (runningGameId) {
                alert('Please close the running game before launching another.');
                return;
            }
            
            try {
                const response = await fetch(`/api/launch-game/${gameId}`, {
                    method: 'POST'
                });
                
                if (response.ok) {
                    runningGameId = gameId;
                    renderGames();
                    startGameStatusCheck();
                } else {
                    alert('Failed to launch game');
                }
            } catch (error) {
                alert('Error launching game: ' + error.message);
            }
        }
        
        // Delete a game
        async function deleteGame(gameId) {
            if (!confirm('Are you sure you want to delete this game?')) {
                return;
            }
            
            try {
                const response = await fetch(`/api/delete-game/${gameId}`, {
                    method: 'DELETE'
                });
                
                if (response.ok) {
                    delete games[gameId];
                    if (runningGameId === gameId) {
                        runningGameId = null;
                    }
                    renderGames();
                } else {
                    alert('Failed to delete game');
                }
            } catch (error) {
                alert('Error deleting game: ' + error.message);
            }
        }
        
        // Check if running game is still active
        function startGameStatusCheck() {
            const checkStatus = async () => {
                if (!runningGameId) return;
                
                try {
                    const response = await fetch(`/api/game-status/${runningGameId}`);
                    const data = await response.json();
                    
                    if (!data.running) {
                        runningGameId = null;
                        renderGames();
                        return;
                    }
                } catch (error) {
                    // Game probably finished
                    runningGameId = null;
                    renderGames();
                    return;
                }
                
                setTimeout(checkStatus, 2000);
            };
            
            setTimeout(checkStatus, 2000);
        }
        
        // Handle Enter key in prompt input
        document.getElementById('promptInput').addEventListener('keydown', function(e) {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                createGame();
            }
        });
        
        // Initialize the app
        checkServerStatus();
        loadModels();
        loadGames();
        
        // Check server status every 30 seconds
        setInterval(checkServerStatus, 30000);
    </script>
</body>
</html>
    """
    return HTMLResponse(content=html_content)


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

    return app.response_class(generate(), media_type="text/plain")


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
