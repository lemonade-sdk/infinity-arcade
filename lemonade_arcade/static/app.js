let isGenerating = false;
let games = {};
let runningGameId = null;
let selectedGameId = null;

// Context menu functionality
function showContextMenu(x, y, gameId) {
    const contextMenu = document.getElementById('contextMenu');
    selectedGameId = gameId;
    
    contextMenu.style.display = 'block';
    contextMenu.style.left = x + 'px';
    contextMenu.style.top = y + 'px';
    
    // Ensure menu doesn't go off screen
    const rect = contextMenu.getBoundingClientRect();
    if (rect.right > window.innerWidth) {
        contextMenu.style.left = (window.innerWidth - rect.width - 10) + 'px';
    }
    if (rect.bottom > window.innerHeight) {
        contextMenu.style.top = (window.innerHeight - rect.height - 10) + 'px';
    }
}

function hideContextMenu() {
    document.getElementById('contextMenu').style.display = 'none';
    selectedGameId = null;
}

// Context menu actions
async function openGameFile() {
    if (!selectedGameId) return;
    
    try {
        const response = await fetch(`/api/open-game-file/${selectedGameId}`, {
            method: 'POST'
        });
        
        if (response.ok) {
            console.log('File opened successfully');
        } else {
            const error = await response.json();
            alert('Failed to open file: ' + (error.detail || 'Unknown error'));
        }
    } catch (error) {
        alert('Error opening file: ' + error.message);
    }
    hideContextMenu();
}

async function copyPrompt() {
    if (!selectedGameId) return;
    
    try {
        const response = await fetch(`/api/game-metadata/${selectedGameId}`);
        if (response.ok) {
            const metadata = await response.json();
            const prompt = metadata.prompt || 'No prompt available';
            
            // Copy to clipboard
            await navigator.clipboard.writeText(prompt);
            
            // Show temporary feedback
            const button = document.getElementById('copyPrompt');
            const originalText = button.innerHTML;
            button.innerHTML = '✅ Copied!';
            setTimeout(() => {
                button.innerHTML = originalText;
            }, 1500);
            
        } else {
            alert('Failed to get game metadata');
        }
    } catch (error) {
        alert('Error copying prompt: ' + error.message);
    }
    hideContextMenu();
}

// Markdown rendering functions
function unescapeJsonString(str) {
    try {
        return str.replace(/\\n/g, '\n')
                 .replace(/\\\\/g, '\\');
    } catch (error) {
        console.error('Error unescaping string:', error);
        return str;
    }
}

function renderMarkdown(text) {
    try {
        // Clean up incomplete code blocks before rendering
        let cleanedText = text;
        
        // Remove trailing incomplete code block markers
        cleanedText = cleanedText.replace(/```\s*$/, '');
        
        // If there's an odd number of ``` markers, add a closing one
        const codeBlockMarkers = (cleanedText.match(/```/g) || []).length;
        if (codeBlockMarkers % 2 === 1) {
            cleanedText += '\n```';
        }
        
        const html = marked.parse(cleanedText);
        return html;
    } catch (error) {
        console.error('Error rendering markdown:', error);
        return text;
    }
}

function setLLMOutput(text, isMarkdown = true) {
    const outputElement = document.getElementById('llmOutput');
    if (isMarkdown) {
        // Add class for markdown styling
        outputElement.classList.add('markdown-content');
        
        // Render as markdown
        outputElement.innerHTML = renderMarkdown(text);
        
        // Remove empty code blocks
        const emptyCodeBlocks = outputElement.querySelectorAll('pre');
        emptyCodeBlocks.forEach(pre => {
            const code = pre.querySelector('code');
            if (code && code.textContent.trim() === '') {
                pre.remove();
            }
        });
        
        // Add language attributes to code blocks for styling
        const codeBlocks = outputElement.querySelectorAll('pre code');
        codeBlocks.forEach(block => {
            const pre = block.parentElement;
            const codeText = block.textContent;
            
            // Check if this looks like Python code
            if (codeText.includes('import ') || 
                codeText.includes('def ') || 
                codeText.includes('pygame') ||
                codeText.includes('class ') ||
                codeText.includes('if __name__') ||
                codeText.match(/^\s*#.*$/m)) { // Python comments
                pre.setAttribute('data-lang', 'python');
                block.classList.add('language-python');
            }
        });
        
        // Re-render MathJax if present
        if (window.MathJax && window.MathJax.typesetPromise) {
            window.MathJax.typesetPromise([outputElement]).catch(console.error);
        }
    } else {
        // Remove markdown class for plain text
        outputElement.classList.remove('markdown-content');
        // Set as plain text
        outputElement.textContent = text;
    }
    
    // Auto-scroll to bottom
    outputElement.scrollTop = outputElement.scrollHeight;
}

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
        `;
        
        // Left click to launch game
        gameItem.addEventListener('click', (e) => {
            if (!e.target.classList.contains('delete-btn')) {
                launchGame(gameId);
            }
        });
        
        // Right click for context menu
        gameItem.addEventListener('contextmenu', (e) => {
            e.preventDefault();
            showContextMenu(e.clientX, e.clientY, gameId);
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
    setLLMOutput('', false); // Clear output
    
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
            const lines = chunk.split('\n');
            
            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    console.log('Received streaming data:', line); // Debug log
                    try {
                        const data = JSON.parse(line.slice(6));
                        if (data.type === 'content') {
                            fullResponse += data.content;
                            setLLMOutput(fullResponse, true); // Render as markdown
                        } else if (data.type === 'status') {
                            document.getElementById('spinnerStatus').textContent = data.message;
                        } else if (data.type === 'complete') {
                            // Game created successfully
                            await loadGames();
                            document.getElementById('promptInput').value = '';
                            if (data.game_id) {
                                runningGameId = data.game_id;
                                renderGames();
                                // Keep spinner active for playing state
                                document.getElementById('spinnerStatus').textContent = 'Playing game...';
                                startGameStatusCheck();
                                // Don't hide spinner here - game is now running
                            } else {
                                // No game launched, hide spinner
                                isGenerating = false;
                                document.getElementById('createBtn').disabled = false;
                                document.getElementById('gameSpinner').classList.remove('active');
                                document.getElementById('gamesGrid').style.display = 'grid';
                            }
                        } else if (data.type === 'error') {
                            document.getElementById('llmOutput').innerHTML = `<div class="error-message">Error: ${data.message}</div>`;
                            // Hide spinner on error
                            isGenerating = false;
                            document.getElementById('createBtn').disabled = false;
                            document.getElementById('gameSpinner').classList.remove('active');
                            document.getElementById('gamesGrid').style.display = 'grid';
                        }
                    } catch (e) {
                        // Handle potential streaming chunks from SSE format
                        // Check if it's a streaming chunk that needs different parsing
                        if (line.trim() === 'data: [DONE]' || line.trim() === '[DONE]') continue;
                        
                        // Try to parse as OpenAI streaming format
                        try {
                            const streamData = JSON.parse(line.slice(6));
                            if (streamData.choices && streamData.choices[0] && streamData.choices[0].delta && streamData.choices[0].delta.content) {
                                const content = streamData.choices[0].delta.content;
                                fullResponse += content;
                                setLLMOutput(fullResponse, true); // Render as markdown
                            }
                        } catch (e2) {
                            // Ignore JSON parse errors for partial chunks
                        }
                    }
                }
            }
        }
    } catch (error) {
        const outputElement = document.getElementById('llmOutput');
        outputElement.innerHTML = `<div class="error-message">Error: ${error.message}</div>`;
        // Hide spinner on error
        isGenerating = false;
        document.getElementById('createBtn').disabled = false;
        document.getElementById('gameSpinner').classList.remove('active');
        document.getElementById('gamesGrid').style.display = 'grid';
    }
    // Note: We don't use finally here because state is managed by the streaming events
}

// Launch a game
async function launchGame(gameId) {
    if (runningGameId) {
        alert('Please close the running game before launching another.');
        return;
    }
    
    // Show spinner for launching
    document.getElementById('gameSpinner').classList.add('active');
    document.getElementById('gamesGrid').style.display = 'none';
    document.getElementById('spinnerStatus').textContent = 'Launching game...';
    
    try {
        const response = await fetch(`/api/launch-game/${gameId}`, {
            method: 'POST'
        });
        
        if (response.ok) {
            runningGameId = gameId;
            renderGames();
            document.getElementById('spinnerStatus').textContent = 'Playing game...';
            startGameStatusCheck();
        } else {
            alert('Failed to launch game');
            // Hide spinner on failure
            document.getElementById('gameSpinner').classList.remove('active');
            document.getElementById('gamesGrid').style.display = 'grid';
        }
    } catch (error) {
        alert('Error launching game: ' + error.message);
        // Hide spinner on error
        document.getElementById('gameSpinner').classList.remove('active');
        document.getElementById('gamesGrid').style.display = 'grid';
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
                // Hide spinner when running game is deleted and reset create button
                isGenerating = false;
                document.getElementById('createBtn').disabled = false;
                document.getElementById('gameSpinner').classList.remove('active');
                document.getElementById('gamesGrid').style.display = 'grid';
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
                // Hide spinner when game finishes and reset create button
                isGenerating = false;
                document.getElementById('createBtn').disabled = false;
                document.getElementById('gameSpinner').classList.remove('active');
                document.getElementById('gamesGrid').style.display = 'grid';
                return;
            }
        } catch (error) {
            // Game probably finished
            runningGameId = null;
            renderGames();
            // Hide spinner when game finishes and reset create button
            isGenerating = false;
            document.getElementById('createBtn').disabled = false;
            document.getElementById('gameSpinner').classList.remove('active');
            document.getElementById('gamesGrid').style.display = 'grid';
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
    
    // Context menu event listeners
    document.getElementById('openFile').addEventListener('click', openGameFile);
    document.getElementById('copyPrompt').addEventListener('click', copyPrompt);
    
    // Hide context menu when clicking elsewhere
    document.addEventListener('click', function(e) {
        if (!e.target.closest('#contextMenu')) {
            hideContextMenu();
        }
    });
    
    // Hide context menu on escape key
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            hideContextMenu();
        }
    });
    
    // Initialize the app
    checkServerStatus();
    loadModels();
    loadGames();
    
    // Check server status every 30 seconds
    setInterval(checkServerStatus, 30000);
});
