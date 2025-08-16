let isGenerating = false;
let games = {};
let runningGameId = null;
let selectedGameId = null;
let lastServerStatusTime = 0;
let isServerKnownOnline = false;
let setupInProgress = false;
let setupComplete = false;

// New User Experience - Checklist Setup
class SetupManager {
    constructor() {
        this.checks = {
            installed: { completed: false, inProgress: false },
            running: { completed: false, inProgress: false },
            connection: { completed: false, inProgress: false },
            model: { completed: false, inProgress: false },
            loaded: { completed: false, inProgress: false }
        };
        this.totalChecks = 5; // Updated to include model installation and loading
    }

    updateProgress() {
        const completed = Object.values(this.checks).filter(check => check.completed).length;
        const percentage = (completed / this.totalChecks) * 100;
        
        const progressFill = document.getElementById('progressFill');
        const progressText = document.getElementById('progressText');
        
        if (progressFill) {
            progressFill.style.width = `${percentage}%`;
        }
        
        if (progressText) {
            if (completed === this.totalChecks) {
                progressText.textContent = 'Setup complete! >>> READY TO LAUNCH <<<';
                // Auto-complete setup instead of showing Let's Go button
                setTimeout(() => this.completeSetup(), 1000);
            } else {
                progressText.textContent = `${completed}/${this.totalChecks} checks completed`;
            }
        }
    }

    updateCheckStatus(checkName, status, description, showButton = false, buttonText = '', buttonAction = null) {
        const icon = document.getElementById(`icon${checkName.charAt(0).toUpperCase() + checkName.slice(1)}`);
        const desc = document.getElementById(`desc${checkName.charAt(0).toUpperCase() + checkName.slice(1)}`);
        const btn = document.getElementById(`btn${checkName.charAt(0).toUpperCase() + checkName.slice(1)}`);
        
        if (icon) {
            icon.className = 'check-icon';
            if (status === 'pending') {
                icon.textContent = '[...]';
                icon.classList.add('pending');
            } else if (status === 'success') {
                icon.textContent = '[OK]';
                icon.classList.add('success');
                this.checks[checkName].completed = true;
                this.checks[checkName].inProgress = false;
            } else if (status === 'error') {
                icon.textContent = '[REQ]';
                icon.classList.add('error');
                this.checks[checkName].completed = false;
                this.checks[checkName].inProgress = false;
            }
        }
        
        if (desc) {
            desc.textContent = description;
        }
        
        if (btn) {
            if (showButton) {
                btn.style.display = 'block';
                btn.textContent = buttonText;
                btn.onclick = buttonAction;
                btn.disabled = false;
            } else {
                btn.style.display = 'none';
            }
        }
        
        this.updateProgress();
    }

    showLetsGoButton() {
        const letsGoBtn = document.getElementById('letsGoBtn');
        if (letsGoBtn) {
            letsGoBtn.style.display = 'block';
            letsGoBtn.onclick = () => this.completeSetup();
        }
    }

    showRetryButton() {
        const retryBtn = document.getElementById('retryBtn');
        if (retryBtn) {
            retryBtn.style.display = 'block';
            retryBtn.onclick = () => this.startSetup();
        }
    }

    async completeSetup() {
        console.log('Setup completed! Showing main interface...');
        setupComplete = true;
        
        // Hide setup screen and built-in games section
        const setupScreen = document.getElementById('setupScreen');
        const gameInterface = document.getElementById('gameInterface');
        const inputArea = document.getElementById('inputArea');
        
        if (setupScreen) setupScreen.style.display = 'none';
        if (gameInterface) gameInterface.style.display = 'block';
        if (inputArea) inputArea.style.display = 'flex';
        
        // Make sure built-in games section is hidden when entering main interface
        this.hideBuiltinGamesSection();
        
        // Load the main interface data
        checkServerStatus();
        loadModels();
        loadGames();
    }

    async startSetup() {
        if (setupInProgress) return;
        setupInProgress = true;
        
        console.log('Starting setup process...');
        
        // Reset all checks
        this.checks = {
            installed: { completed: false, inProgress: false },
            running: { completed: false, inProgress: false },
            connection: { completed: false, inProgress: false },
            model: { completed: false, inProgress: false },
            loaded: { completed: false, inProgress: false }
        };
        
        // Hide buttons and built-in games section
        const letsGoBtn = document.getElementById('letsGoBtn');
        const retryBtn = document.getElementById('retryBtn');
        if (letsGoBtn) letsGoBtn.style.display = 'none';
        if (retryBtn) retryBtn.style.display = 'none';
        this.hideBuiltinGamesSection();
        
        this.updateProgress();
        
        // Step 1: Check and complete installation
        console.log('Step 1: Checking installation...');
        await this.doInstallationStep();
        if (!this.checks.installed.completed) {
            setupInProgress = false;
            this.showRetryButton();
            return;
        }
        
        // Step 2: Check and start server if needed
        console.log('Step 2: Checking server...');
        await this.doServerStep();
        if (!this.checks.running.completed) {
            setupInProgress = false;
            this.showRetryButton();
            return;
        }
        
        // Step 3: Check connection
        console.log('Step 3: Checking connection...');
        await this.doConnectionStep();
        if (!this.checks.connection.completed) {
            setupInProgress = false;
            this.showRetryButton();
            return;
        }
        
        // Step 4: Check and install model if needed
        console.log('Step 4: Checking model...');
        await this.doModelStep();
        if (!this.checks.model.completed) {
            setupInProgress = false;
            this.showRetryButton();
            return;
        }
        
        // Step 5: Check and load model if needed
        console.log('Step 5: Checking model loaded...');
        await this.doModelLoadedStep();
        if (!this.checks.loaded.completed) {
            setupInProgress = false;
            this.showRetryButton();
            return;
        }
        
        console.log('Setup completed successfully!');
        setupInProgress = false;
    }

    async doInstallationStep() {
        this.updateCheckStatus('installed', 'pending', 'Checking if Lemonade Server is installed...');
        
        try {
            const response = await fetch('/api/installation-status');
            const status = await response.json();
            
            if (status.installed && status.compatible) {
                this.checks.installed.completed = true;
                this.updateCheckStatus('installed', 'success', `Lemonade Server v${status.version} is installed and compatible`);
            } else if (status.installed && !status.compatible) {
                this.updateCheckStatus('installed', 'error', 
                    `Found version ${status.version}, but version 8.1.3+ is required`,
                    true, 'Update Now', () => this.installServer());
                return; // Stop here, user needs to take action
            } else {
                this.updateCheckStatus('installed', 'error', 
                    'Lemonade Server is not installed',
                    true, 'Install Now', () => this.installServer());
                return; // Stop here, user needs to take action
            }
        } catch (error) {
            console.error('Failed to check installation:', error);
            this.updateCheckStatus('installed', 'error', 
                'Failed to check installation status',
                true, 'Retry', () => this.startSetup());
        }
    }

    async doServerStep() {
        this.updateCheckStatus('running', 'pending', 'Checking if Lemonade Server is running...');
        
        try {
            const response = await fetch('/api/server-running-status');
            const status = await response.json();
            
            if (status.running) {
                this.checks.running.completed = true;
                this.updateCheckStatus('running', 'success', 'Lemonade Server is running');
            } else {
                this.updateCheckStatus('running', 'error', 
                    'Lemonade Server failed to start automatically',
                    true, 'Retry', () => this.startSetup());
            }
        } catch (error) {
            console.error('Failed to check server status:', error);
            this.updateCheckStatus('running', 'error', 
                'Failed to check server status',
                true, 'Retry', () => this.startSetup());
        }
    }

    async doConnectionStep() {
        this.updateCheckStatus('connection', 'pending', 'Testing connection to Lemonade Server...');
        
        try {
            const response = await fetch('/api/api-connection-status');
            const status = await response.json();
            
            if (status.api_online) {
                this.checks.connection.completed = true;
                this.updateCheckStatus('connection', 'success', 'Successfully connected to Lemonade Server API');
            } else {
                this.updateCheckStatus('connection', 'error', 
                    'Cannot connect to Lemonade Server API',
                    true, 'Retry', () => this.startSetup());
            }
        } catch (error) {
            console.error('Failed to check API connection:', error);
            this.updateCheckStatus('connection', 'error', 
                'Failed to test API connection',
                true, 'Retry', () => this.startSetup());
        }
    }

    async doModelStep() {
        this.updateCheckStatus('model', 'pending', 'Checking for required model...');
        
        try {
            const response = await fetch('/api/model-installation-status');
            const status = await response.json();
            
            if (status.model_installed) {
                this.checks.model.completed = true;
                this.updateCheckStatus('model', 'success', `Required model ${status.model_name} is installed`);
            } else {
                this.updateCheckStatus('model', 'error', 
                    `Required model ${status.model_name} is not installed`,
                    true, 'Install Model (18.6 GB)', () => this.installModel());
                return; // Stop here, user needs to take action
            }
        } catch (error) {
            console.error('Model check failed:', error);
            this.updateCheckStatus('model', 'error', 
                'Failed to check model status',
                true, 'Retry', () => this.startSetup());
        }
    }

    async doModelLoadedStep() {
        this.updateCheckStatus('loaded', 'pending', 'Checking if model is loaded...');
        
        try {
            const response = await fetch('/api/model-loading-status');
            const status = await response.json();
            
            if (status.model_loaded) {
                this.checks.loaded.completed = true;
                this.updateCheckStatus('loaded', 'success', 'Required model is loaded and ready');
            } else {
                this.updateCheckStatus('loaded', 'pending', 'Required model is not loaded. Loading automatically...');
                
                // Try to load the model
                const loadResponse = await fetch('/api/load-model', { method: 'POST' });
                const loadResult = await loadResponse.json();
                
                if (loadResult.success) {
                    this.checks.loaded.completed = true;
                    this.updateCheckStatus('loaded', 'success', 'Required model loaded successfully');
                } else {
                    this.updateCheckStatus('loaded', 'error', 
                        `Failed to load model: ${loadResult.message}`,
                        true, 'Retry Load', () => this.startSetup());
                }
            }
        } catch (error) {
            console.error('Model load check failed:', error);
            this.updateCheckStatus('loaded', 'error', 
                'Failed to check if model is loaded',
                true, 'Retry', () => this.startSetup());
        }
    }

    async checkInstallation() {
        console.log('Checking installation...');
        this.updateCheckStatus('installed', 'pending', 'Checking if Lemonade Server is installed...');
        
        try {
            const response = await fetch('/api/installation-status');
            const status = await response.json();
            
            await this.processInstallationStatus(status);
        } catch (error) {
            console.error('Failed to check installation:', error);
            this.updateCheckStatus('installed', 'error', 
                'Failed to check installation status',
                true, 'Retry', () => this.checkInstallation());
        }
    }

    async checkServerRunning() {
        console.log('Checking if server is running...');
        this.updateCheckStatus('running', 'pending', 'Checking if Lemonade Server is running...');
        
        try {
            const response = await fetch('/api/server-running-status');
            const status = await response.json();
            
            await this.processRunningStatus(status);
        } catch (error) {
            console.error('Failed to check server status:', error);
            this.updateCheckStatus('running', 'error', 
                'Failed to check server status',
                true, 'Retry', () => this.checkServerRunning());
        }
    }

    async checkConnection() {
        console.log('Checking API connection...');
        this.updateCheckStatus('connection', 'pending', 'Testing connection to Lemonade Server...');
        
        try {
            const response = await fetch('/api/api-connection-status');
            const status = await response.json();
            
            await this.processConnectionStatus(status);
            
            // Automatically proceed to checking the model if connection is successful
            if (this.checks.connection.completed) {
                setTimeout(() => {
                    this.checkModel();
                }, 1000);
            }
        } catch (error) {
            console.error('Failed to check API connection:', error);
            this.updateCheckStatus('connection', 'error', 
                'Failed to test API connection',
                true, 'Retry', () => this.checkConnection());
        }
    }

    async installServer() {
        const btn = document.getElementById('btnInstalled');
        if (btn) {
            btn.disabled = true;
            btn.textContent = 'Installing...';
        }
        
        this.updateCheckStatus('installed', 'pending', 'Downloading and installing Lemonade Server... This may take several minutes.');
        
        try {
            const response = await fetch('/api/install-server', { method: 'POST' });
            const result = await response.json();
            
            if (result.success) {
                this.updateCheckStatus('installed', 'success', 'Lemonade Server installed successfully!');
                
                // Wait a moment then restart the setup process
                setTimeout(() => {
                    this.startSetup();
                }, 2000);
            } else {
                this.updateCheckStatus('installed', 'error', 
                    `Installation failed: ${result.message}`,
                    true, 'Retry Install', () => this.installServer());
            }
        } catch (error) {
            console.error('Installation failed:', error);
            this.updateCheckStatus('installed', 'error', 
                'Installation failed due to network error',
                true, 'Retry Install', () => this.installServer());
        }
    }

    async startServer() {
        const btn = document.getElementById('btnRunning');
        if (btn) {
            btn.disabled = true;
            btn.textContent = 'Starting...';
        }
        
        this.updateCheckStatus('running', 'pending', 'Starting Lemonade Server...');
        
        try {
            const response = await fetch('/api/start-server', { method: 'POST' });
            const result = await response.json();
            
            if (result.success) {
                this.updateCheckStatus('running', 'pending', 'Server started. Waiting for it to be ready...');
                
                // Wait for server to be ready
                await this.waitForServerReady();
            } else {
                this.updateCheckStatus('running', 'error', 
                    `Failed to start server: ${result.message}`,
                    true, 'Retry Start', () => this.startServer());
            }
        } catch (error) {
            console.error('Failed to start server:', error);
            this.updateCheckStatus('running', 'error', 
                'Failed to start server due to network error',
                true, 'Retry Start', () => this.startServer());
        }
    }

    async waitForServerReady() {
        let attempts = 0;
        const maxAttempts = 60; // 120 seconds total (2 minutes)
        
        while (attempts < maxAttempts) {
            await new Promise(resolve => setTimeout(resolve, 2000));
            
            try {
                const response = await fetch('/api/server-running-status');
                const status = await response.json();
                
                if (status.running) {
                    this.updateCheckStatus('running', 'success', 'Lemonade Server is running');
                    return; // Just return, the main setup flow will continue
                }
            } catch (error) {
                console.log('Still waiting for server...');
            }
            
            attempts++;
        }
        
        // If we get here, server didn't start in time
        this.updateCheckStatus('running', 'error', 
            'Server started but is taking too long to respond',
            true, 'Retry', () => this.startSetup());
        throw new Error('Server startup timeout');
    }

    async checkModel() {
        if (this.checks.model.inProgress) return;
        this.checks.model.inProgress = true;
        
        this.updateCheckStatus('model', 'pending', 'Checking for required model...');
        
        try {
            const response = await fetch('/api/model-installation-status');
            const status = await response.json();
            
            await this.processModelStatus(status);
            
            // Automatically proceed to checking if model is loaded if model is installed
            if (this.checks.model.completed) {
                setTimeout(() => {
                    this.checkModelLoaded();
                }, 1000);
            }
        } catch (error) {
            console.error('Model check failed:', error);
            this.updateCheckStatus('model', 'error', 
                'Failed to check model status',
                true, 'Retry Check', () => this.checkModel());
        }
        
        this.checks.model.inProgress = false;
        this.updateProgress();
    }

    async installModel() {
        const btn = document.getElementById('btnModel');
        if (btn) {
            btn.disabled = true;
            btn.textContent = 'Installing...';
        }
        
        this.updateCheckStatus('model', 'pending', 'Installing required model (18.6 GB - this may take several minutes)...');
        
        // Always show built-in games section during download
        this.showBuiltinGamesSection();
        
        try {
            // Use a very long timeout for model installation (30 minutes)
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 1800000); // 30 minutes
            
            const response = await fetch('/api/install-model', { 
                method: 'POST',
                signal: controller.signal
            });
            clearTimeout(timeoutId);
            
            const result = await response.json();
            
            if (result.success) {
                this.updateCheckStatus('model', 'success', 'Required model installed successfully!');
                
                // Hide built-in games section when download completes
                this.hideBuiltinGamesSection();
                
                // Restart setup process to continue to next step
                setTimeout(() => {
                    this.startSetup();
                }, 2000);
            } else {
                this.updateCheckStatus('model', 'error', 
                    `Model installation failed: ${result.message}`,
                    true, 'Retry Install (18.6 GB)', () => this.installModel());
                
                // Hide built-in games section on error
                this.hideBuiltinGamesSection();
            }
        } catch (error) {
            console.error('Model installation failed:', error);
            if (error.name === 'AbortError') {
                this.updateCheckStatus('model', 'error', 
                    'Model installation timed out after 30 minutes',
                    true, 'Retry Install (18.6 GB)', () => this.installModel());
            } else {
                this.updateCheckStatus('model', 'error', 
                    'Model installation failed due to network error',
                    true, 'Retry Install (18.6 GB)', () => this.installModel());
            }
            
            // Hide built-in games section on error
            this.hideBuiltinGamesSection();
        }
    }

    async checkModelLoaded() {
        if (this.checks.loaded.inProgress) return;
        this.checks.loaded.inProgress = true;
        
        this.updateCheckStatus('loaded', 'pending', 'Checking if model is loaded...');
        
        try {
            const response = await fetch('/api/model-loading-status');
            const status = await response.json();
            
            await this.processModelLoadedStatus(status);
        } catch (error) {
            console.error('Model load check failed:', error);
            this.updateCheckStatus('loaded', 'error', 
                'Failed to check if model is loaded',
                true, 'Retry Check', () => this.checkModelLoaded());
        }
        
        this.checks.loaded.inProgress = false;
        this.updateProgress();
    }

    async loadModel() {
        const btn = document.getElementById('btnLoaded');
        if (btn) {
            btn.disabled = true;
            btn.textContent = 'Loading...';
        }
        
        this.updateCheckStatus('loaded', 'pending', 'Loading model into memory...');
        
        try {
            // Use a long timeout for model loading (10 minutes)
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 600000); // 10 minutes
            
            const response = await fetch('/api/load-model', { 
                method: 'POST',
                signal: controller.signal
            });
            clearTimeout(timeoutId);
            
            const result = await response.json();
            
            if (result.success) {
                this.updateCheckStatus('loaded', 'success', 'Model loaded successfully and ready to use!');
            } else {
                this.updateCheckStatus('loaded', 'error', 
                    `Model loading failed: ${result.message}`,
                    true, 'Retry Load', () => this.loadModel());
            }
        } catch (error) {
            console.error('Model loading failed:', error);
            this.updateCheckStatus('loaded', 'error', 
                'Model loading failed due to network error',
                true, 'Retry Load', () => this.loadModel());
        }
    }
    
    showBuiltinGamesSection() {
        const builtinGamesSection = document.getElementById('builtinGamesSection');
        if (builtinGamesSection) {
            builtinGamesSection.style.display = 'block';
            this.loadBuiltinGames();
        }
    }
    
    hideBuiltinGamesSection() {
        const builtinGamesSection = document.getElementById('builtinGamesSection');
        if (builtinGamesSection) {
            builtinGamesSection.style.display = 'none';
        }
    }
    
    async loadBuiltinGames() {
        const builtinGamesGrid = document.getElementById('builtinGamesGrid');
        if (!builtinGamesGrid) return;
        
        try {
            // Fetch the built-in games from the server
            const response = await fetch('/api/games');
            const allGames = await response.json();
            
            // Filter for built-in games only
            const builtinGames = Object.entries(allGames).filter(([gameId, gameData]) => 
                gameData.builtin || gameId.startsWith('builtin_')
            );
            
            if (builtinGames.length === 0) {
                builtinGamesGrid.innerHTML = '<div class="no-builtin-games">No built-in games available</div>';
                return;
            }
            
            builtinGamesGrid.innerHTML = '';
            
            builtinGames.forEach(([gameId, gameData]) => {
                const gameItem = document.createElement('div');
                gameItem.className = 'builtin-game-item';
                
                gameItem.innerHTML = `
                    <div class="builtin-game-icon">🎮</div>
                    <div class="builtin-game-title">${gameData.title}</div>
                    <div class="builtin-game-description">${gameData.prompt}</div>
                `;
                
                // Click to launch the built-in game
                gameItem.addEventListener('click', () => {
                    this.launchBuiltinGame(gameId);
                });
                
                builtinGamesGrid.appendChild(gameItem);
            });
        } catch (error) {
            console.error('Failed to load built-in games:', error);
            builtinGamesGrid.innerHTML = '<div class="builtin-games-error">Failed to load built-in games</div>';
        }
    }
    
    async launchBuiltinGame(gameId) {
        try {
            // Launch the built-in game using the correct endpoint with game_id as path parameter
            const response = await fetch(`/api/launch-game/${gameId}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                }
            });
            
            const result = await response.json();
            
            if (result.success) {
                console.log(`Built-in game ${gameId} launched successfully`);
                // You could show a message or update UI to indicate the game is running
            } else {
                console.error(`Failed to launch built-in game: ${result.message}`);
                alert(`Failed to launch game: ${result.message}`);
            }
        } catch (error) {
            console.error('Error launching built-in game:', error);
            alert('Failed to launch game due to network error');
        }
    }
}

// Global setup manager instance
const setupManager = new SetupManager();

// Debug function for manual testing
window.debugSetup = function() {
    console.log('Manual setup debug triggered');
    setupManager.startSetup();
};

// Context menu functionality
function showContextMenu(x, y, gameId) {
    const contextMenu = document.getElementById('contextMenu');
    selectedGameId = gameId;
    
    // Check if it's a built-in game
    const isBuiltin = games[gameId] && (games[gameId].builtin || gameId.startsWith('builtin_'));
    
    if (isBuiltin) {
        // Show built-in game context menu
        contextMenu.innerHTML = `
            <div class="context-menu-item builtin-info">
                🎮 Built-in game
            </div>
        `;
    } else {
        // Show regular context menu for user-created games
        contextMenu.innerHTML = `
            <button class="context-menu-item" id="openFile" onclick="openGameFile()">
                📄 Open Python File
            </button>
            <div class="context-menu-separator"></div>
            <button class="context-menu-item" id="copyPrompt" onclick="copyPrompt()">
                📋 Copy Prompt
            </button>
        `;
    }
    
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
    
    // Check if it's a built-in game
    if (games[selectedGameId] && (games[selectedGameId].builtin || selectedGameId.startsWith('builtin_'))) {
        alert('Cannot view source code of built-in games');
        hideContextMenu();
        return;
    }
    
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
    
    // Check if it's a built-in game
    if (games[selectedGameId] && (games[selectedGameId].builtin || selectedGameId.startsWith('builtin_'))) {
        alert('Cannot copy prompt for built-in games');
        hideContextMenu();
        return;
    }
    
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
            button.innerHTML = '[OK] Copied!';
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
// This function is more robust during LLM generation phases:
// - Uses longer timeouts during generation
// - Maintains "online" status during brief connection issues if server was recently working
// - Only marks server as offline if it's been unreachable for a significant time during generation
async function checkServerStatus() {
    try {
        // During LLM generation, use a longer timeout and be more forgiving
        // Increased timeouts to handle slow server loading
        const timeout = isGenerating ? 60000 : 30000;
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), timeout);
        
        const response = await fetch('/api/server-status', {
            signal: controller.signal
        });
        clearTimeout(timeoutId);
        
        const data = await response.json();
        const indicator = document.getElementById('statusIndicator');
        const statusText = document.getElementById('statusText');
        
        if (data.online) {
            indicator.className = 'status-indicator status-online';
            statusText.innerHTML = '🍋 Lemonade Server Online';
            isServerKnownOnline = true;
            lastServerStatusTime = Date.now();
        } else {
            // Only show offline if we're not generating or if it's been offline for a while
            if (!isGenerating || (Date.now() - lastServerStatusTime > 60000)) {
                indicator.className = 'status-indicator status-offline';
                statusText.innerHTML = `Server Offline - <a href="https://lemonade-server.ai" target="_blank" class="get-lemonade-link">Get Lemonade</a>`;
                isServerKnownOnline = false;
            }
            // If generating and server was recently online, keep showing online status
        }
    } catch (error) {
        const indicator = document.getElementById('statusIndicator');
        const statusText = document.getElementById('statusText');
        
        // During generation, be more forgiving about timeouts
        if (isGenerating && isServerKnownOnline && (Date.now() - lastServerStatusTime < 120000)) {
            // Server was recently online and we're generating - probably just busy
            console.log('Server check failed during generation, but keeping online status:', error.message);
            return; // Don't change status
        }
        
        indicator.className = 'status-indicator status-offline';
        statusText.innerHTML = `Connection Error - <a href="https://lemonade-server.ai" target="_blank" class="get-lemonade-link">Get Lemonade</a>`;
        isServerKnownOnline = false;
    }
}

// Load available models
async function loadModels() {
    try {
        const response = await fetch('/api/models');
        const models = await response.json();
        const select = document.getElementById('modelSelect');
        
        // Hide the model selector since we're using a fixed model
        select.style.display = 'none';
        
        // Set the required model as selected (for any code that might still read it)
        const requiredModel = "Qwen3-Coder-30B-A3B-Instruct-GGUF";
        select.innerHTML = `<option value="${requiredModel}" selected>${requiredModel}</option>`;
        
    } catch (error) {
        const select = document.getElementById('modelSelect');
        select.style.display = 'none';
        select.innerHTML = '<option>Error loading models</option>';
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
    
    // Sort games so built-in games appear first
    const sortedGames = Object.entries(games).sort(([gameIdA, gameDataA], [gameIdB, gameDataB]) => {
        const isBuiltinA = gameDataA.builtin || gameIdA.startsWith('builtin_');
        const isBuiltinB = gameDataB.builtin || gameIdB.startsWith('builtin_');
        
        // Built-in games come first
        if (isBuiltinA && !isBuiltinB) return -1;
        if (!isBuiltinA && isBuiltinB) return 1;
        
        // Within each category, sort by creation time (or alphabetically for built-ins)
        if (isBuiltinA && isBuiltinB) {
            return gameDataA.title.localeCompare(gameDataB.title);
        } else {
            return (gameDataB.created || 0) - (gameDataA.created || 0); // Newer first for user games
        }
    });
    
    sortedGames.forEach(([gameId, gameData]) => {
        const gameItem = document.createElement('div');
        gameItem.className = 'game-item';
        
        // Check if it's a built-in game
        const isBuiltin = gameData.builtin || gameId.startsWith('builtin_');
        
        if (runningGameId === gameId) {
            gameItem.classList.add('running');
        }
        
        if (isBuiltin) {
            gameItem.classList.add('builtin');
        }
        
        // Only show delete button for non-built-in games
        let deleteButtonHtml = '';
        if (!isBuiltin) {
            deleteButtonHtml = `<button class="delete-btn" onclick="deleteGame('${gameId}')">&times;</button>`;
        }
        
        gameItem.innerHTML = `
            ${deleteButtonHtml}
            <div class="game-title">${gameData.title}</div>
        `;
        
        // Left click to launch game
        gameItem.addEventListener('click', (e) => {
            if (!e.target.classList.contains('delete-btn')) {
                launchGame(gameId);
            }
        });
        
        // Right click for context menu (for all games)
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
    const model = "Qwen3-Coder-30B-A3B-Instruct-GGUF"; // Use the required model directly
    
    if (!prompt || isGenerating) return;
    
    if (runningGameId) {
        alert('Please close the running game before creating a new one.');
        return;
    }
    
    isGenerating = true;
    isServerKnownOnline = true; // We're about to use the server, so it should be online
    lastServerStatusTime = Date.now();
    
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
        
        // Server responded successfully, update status immediately
        isServerKnownOnline = true;
        lastServerStatusTime = Date.now();
        const indicator = document.getElementById('statusIndicator');
        const statusText = document.getElementById('statusText');
        indicator.className = 'status-indicator status-online';
        statusText.innerHTML = '🍋 Lemonade Server Online';
        
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
    // Check if it's a built-in game
    if (games[gameId] && (games[gameId].builtin || gameId.startsWith('builtin_'))) {
        alert('Cannot delete built-in games');
        return;
    }
    
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
    console.log('DOM Content Loaded - Lemonade Arcade initialized');
    
    // Check if setup screen exists
    const setupScreen = document.getElementById('setupScreen');
    console.log('Setup screen element found:', !!setupScreen);
    
    // Setup keyboard event listeners
    const promptInput = document.getElementById('promptInput');
    if (promptInput) {
        promptInput.addEventListener('keydown', function(e) {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                createGame();
            }
        });
    }
    
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
    
    // Start the new user experience setup process
    setTimeout(() => {
        console.log('Starting new user experience setup...');
        setupManager.startSetup().catch(error => {
            console.error('Setup process failed:', error);
        });
    }, 500);
    
    // Regular status checking - only if setup is complete
    setInterval(() => {
        if (setupComplete) {
            checkServerStatus();
        }
    }, 15000); // Check every 15 seconds
});
