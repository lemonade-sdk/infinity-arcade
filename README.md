# Lemonade Arcade

🍋 An AI-powered game generator and arcade that creates playable Python games using LLMs.

## Overview

Lemonade Arcade is a unique application that combines the convenience of a ChatGPT-like interface with the concept of a game emulator. Instead of emulating existing games, it uses Large Language Models (served by Lemonade Server) to generate completely new games based on your prompts, then lets you play them instantly.

## Features

- **AI Game Generation**: Describe any game concept and watch as an LLM creates a playable Python game
- **Real-time Streaming**: Watch the LLM generate code in real-time in the sidebar
- **Game Library**: All generated games are saved and can be replayed anytime
- **No External Assets**: Games are generated using only Python and pygame - no images or files needed
- **Retro Arcade UI**: Dark, arcade-style interface with ASCII art branding
- **Easy Management**: Delete games you don't want with a simple click

## Requirements

- Python 3.8 or higher
- [Lemonade Server](https://lemonade-server.ai) running locally
- Modern web browser

## Installation

1. Clone this repository:
   ```bash
   git clone https://github.com/lemonade-sdk/lemonade
   cd lemonade-arcade
   ```

2. Install the package:
   ```bash
   pip install -e .
   ```

3. Make sure Lemonade Server is running with at least one language model loaded.

## Usage

1. Start Lemonade Arcade:
   ```bash
   lemonade-arcade
   ```

2. The application will automatically open in your web browser at `http://localhost:8080`

3. Check that the status indicator shows Lemonade Server is online (🍋)

4. Select a model from the dropdown

5. Enter a game description in the prompt box, for example:
   - "Create a snake game but the food moves around"
   - "Make a space invaders clone with rainbow colors"
   - "Build a simple platformer where you collect coins"

6. Click "Create Game" and watch the magic happen!

7. Once generated, the game will automatically launch and be added to your library

8. Click any game in your library to play it again

9. Hover over games and click the X button to delete games you no longer want

## Game Generation

Games are generated with the following constraints:
- Pure Python using the pygame library only
- No external images, sounds, or asset files
- Complete and playable with proper game mechanics
- Proper event handling and game loops
- Visual appeal using pygame's built-in drawing functions

## File Structure

```
~/.lemonade-arcade/
└── games/
    ├── metadata.json    # Game titles and descriptions
    ├── abc12345.py      # Generated game files
    └── xyz67890.py
```

## Troubleshooting

### "Server Offline" Status
- Ensure Lemonade Server is running on `http://localhost:8000`
- Check that you have models loaded in Lemonade Server
- Visit [lemonade-server.ai](https://lemonade-server.ai) for setup instructions

### Game Won't Launch
- Make sure pygame is installed: `pip install pygame`
- Check the generated code for any syntax errors
- Try regenerating the game with a more specific prompt

### Generation Failures
- Try a simpler game concept
- Make sure your selected model supports code generation
- Check Lemonade Server logs for errors

## Examples

Here are some example prompts that work well:

- **Classic Games**: "pong", "tetris", "pacman maze game", "asteroids"
- **Variations**: "snake but food teleports", "breakout with power-ups", "flappy bird in space"
- **Original Ideas**: "catching falling stars", "color matching puzzle", "maze with moving walls"

## Contributing

Contributions are welcome! Feel free to:
- Report bugs or request features via GitHub issues
- Submit pull requests for improvements
- Share interesting game prompts and results

## License

This project is licensed under the same terms as the main Lemonade project.

## Credits

Powered by [Lemonade Server](https://lemonade-server.ai) - bringing AI to your local machine.
