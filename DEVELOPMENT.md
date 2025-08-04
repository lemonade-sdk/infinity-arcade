# Lemonade Arcade Development Guide

## Project Structure

```
lemonade-arcade/
├── lemonade_arcade/
│   ├── __init__.py          # Package initialization
│   ├── main.py              # Main FastAPI application
│   └── cli.py               # Command-line interface
├── setup.py                 # Package setup and dependencies
├── requirements.txt         # Dependencies list
├── test_installation.py     # Installation verification script
├── create_demo_games.py     # Demo game creation script
├── README.md               # User documentation
└── .gitignore              # Git ignore rules
```

## How It Works

### 1. Web Interface
- The main application serves an HTML interface with embedded CSS and JavaScript
- Uses a dark arcade-style theme with ASCII art branding
- Real-time status checking for Lemonade Server connectivity
- Model selection dropdown populated from Lemonade Server
- Game library grid showing generated games
- Real-time LLM output streaming in sidebar

### 2. Game Generation Process
1. User enters a game description prompt
2. Application connects to Lemonade Server via OpenAI-compatible API
3. Sends a system prompt with game generation rules + user prompt
4. Streams LLM response in real-time to the sidebar
5. Extracts Python code from the response using regex patterns
6. Saves the code as a .py file with unique ID
7. Automatically launches the generated game
8. Adds game to library with title and description

### 3. Game Management
- Games are stored in `~/.lemonade-arcade/games/`
- Metadata stored in `metadata.json` with titles, descriptions, timestamps
- Each game gets a unique 8-character ID
- Games can be launched by clicking library icons
- Games can be deleted with confirmation dialog
- Only one game can run at a time

### 4. Game Requirements
Generated games must follow these rules:
- Pure Python using only pygame library
- No external images, sounds, or asset files
- Complete and playable with proper game mechanics
- Proper pygame event handling and game loop
- Window closes properly when user clicks X
- Visual appeal using pygame's built-in drawing functions

## API Endpoints

### Frontend Routes
- `GET /` - Serves the main HTML interface

### API Routes
- `GET /api/server-status` - Check if Lemonade Server is online
- `GET /api/models` - Get available models from Lemonade Server
- `GET /api/games` - Get all saved games metadata
- `POST /api/create-game` - Generate a new game (streaming response)
- `POST /api/launch-game/{game_id}` - Launch a specific game
- `GET /api/game-status/{game_id}` - Check if a game is running
- `DELETE /api/delete-game/{game_id}` - Delete a game

## Development Setup

### Prerequisites
- Python 3.8 or higher
- Conda (recommended) or pip
- Lemonade Server running locally

### Installation
```bash
# Create conda environment
conda create -n arcade python=3.11 -y
conda activate arcade

# Clone and install
git clone <repository>
cd lemonade-arcade
pip install -e .

# Verify installation
python test_installation.py

# Create demo games (optional)
python create_demo_games.py
```

### Running the Application
```bash
conda activate arcade
lemonade-arcade
```

The application will:
1. Start FastAPI server on port 8080
2. Automatically open web browser
3. Check Lemonade Server connectivity
4. Load available models
5. Display any existing games in library

## System Prompt for Game Generation

The application uses this system prompt for generating games:

```
You are an expert Python game developer. Generate a complete, working Python game using pygame based on the user's description.

Rules:
1. Use ONLY the pygame library - no external images, sounds, or files
2. Create everything (graphics, colors, shapes) using pygame's built-in drawing functions
3. Make the game fully playable and fun
4. Include proper game mechanics (win/lose conditions, scoring if appropriate)
5. Use proper pygame event handling and game loop
6. Add comments explaining key parts of the code
7. Make sure the game window closes properly when the user clicks the X button
8. Use reasonable colors and make the game visually appealing with pygame primitives

Generate ONLY the Python code in a single code block. Do not include any explanations outside the code block.
```

## Code Extraction

The application extracts Python code using these regex patterns:
1. `r'```python\s*\n(.*?)\n```'` - Python code blocks
2. `r'```py\s*\n(.*?)\n```'` - Py code blocks  
3. `r'```\s*\n(.*?)\n```'` - Generic code blocks

It validates extracted code by checking for 'pygame' in the content.

## Error Handling

- Connection errors to Lemonade Server are displayed in status indicator
- Game generation failures show error messages in LLM output area
- Game launch failures are reported via alerts
- Missing dependencies are caught during import testing

## Security Considerations

- Generated code is executed directly - only use with trusted LLMs
- Games run in separate processes to isolate failures
- No network access restrictions on generated games
- File paths are validated but not sandboxed

## Customization Options

### Changing the Port
Edit the `port` variable in `main.py`:
```python
port = 8080  # Change to desired port
```

### Modifying the UI Theme
The CSS is embedded in the HTML template in `main.py`. Key color variables:
- `#00ff41` - Primary green (matrix style)
- `#1a1a2e` - Dark blue background
- `#16213e` - Darker blue accents

### Adding New Game Templates
Add sample games to `create_demo_games.py` for testing without LLM.

### Extending the API
Add new FastAPI routes to `main.py` for additional functionality.

## Troubleshooting

### "Server Offline" Status
- Ensure Lemonade Server is running on http://localhost:8000
- Check firewall settings
- Verify models are loaded in Lemonade Server

### Games Won't Launch
- Check pygame installation: `pip install pygame`
- Verify Python executable permissions
- Check generated code for syntax errors

### Import Errors
- Ensure all dependencies are installed: `pip install -r requirements.txt`
- Verify correct conda environment is activated
- Run installation test: `python test_installation.py`

## Contributing

To contribute to Lemonade Arcade:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly with various game prompts
5. Submit a pull request

### Code Style
- Follow PEP 8 Python style guidelines
- Add type hints where helpful
- Include docstrings for functions
- Comment complex logic

### Testing
- Test with multiple models
- Verify games work across different prompts
- Check error handling edge cases
- Ensure UI works on different screen sizes
