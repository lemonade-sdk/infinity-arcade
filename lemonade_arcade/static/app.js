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
document.addEventListener('DOMContentLoaded', function() {
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
});
