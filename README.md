
<pre align="center">
██╗███╗   ██╗███████╗██╗███╗   ██╗██╗████████╗██╗   ██╗
██║████╗  ██║██╔════╝██║████╗  ██║██║╚══██╔══╝╚██╗ ██╔╝
██║██╔██╗ ██║█████╗  ██║██╔██╗ ██║██║   ██║    ╚████╔╝ 
██║██║╚██╗██║██╔══╝  ██║██║╚██╗██║██║   ██║     ╚██╔╝  
██║██║ ╚████║██║     ██║██║ ╚████║██║   ██║      ██║   
╚═╝╚═╝  ╚═══╝╚═╝     ╚═╝╚═╝  ╚═══╝╚═╝   ╚═╝      ╚═╝   

 █████╗ ██████╗  ██████╗ █████╗ ██████╗ ███████╗
██╔══██╗██╔══██╗██╔════╝██╔══██╗██╔══██╗██╔════╝
███████║██████╔╝██║     ███████║██║  ██║█████╗  
██╔══██║██╔══██╗██║     ██╔══██║██║  ██║██╔══╝  
██║  ██║██║  ██║╚██████╗██║  ██║██████╔╝███████╗
╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝╚═╝  ╚═╝╚═════╝ ╚══════╝
</pre>

<p align="center">
  <a href="https://discord.gg/5xXzkMu8Zk">
    <img src="https://img.shields.io/badge/Discord-7289DA?logo=discord&logoColor=white" alt="Discord" /></a>
  <a href="docs/README.md#installation" title="Check out our instructions">
    <img src="https://img.shields.io/badge/Windows-11-0078D6?logo=windows&logoColor=white" alt="Windows 11" /></a>
  <a href="https://lemonade-server.ai/#linux" title="Ubuntu 24.04 & 25.04 Supported">
    <img src="https://img.shields.io/badge/Ubuntu-24.04%20%7C%2025.04-E95420?logo=ubuntu&logoColor=white" alt="Ubuntu 24.04 | 25.04" /></a>
  <a href="#installation" title="Check out our instructions">
    <img src="https://img.shields.io/badge/Python-3.10--3.13-blue?logo=python&logoColor=white" alt="Made with Python" /></a>
  <a href="https://github.com/lemonade-sdk/infinity-arcade/releases/latest" title="Download the latest release">
    <img src="https://img.shields.io/github/v/release/lemonade-sdk/infinity-arcade?include_prereleases" alt="Latest Release" /></a>
  <a href="https://tooomm.github.io/github-release-stats/?username=lemonade-sdk&repository=infinity-arcade">
    <img src="https://img.shields.io/github/downloads/lemonade-sdk/infinity-arcade/total.svg" alt="GitHub downloads" /></a>
  <a href="https://github.com/lemonade-sdk/infinity-arcade/blob/main/LICENSE">
    <img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License: MIT" /></a>
  <a href="https://star-history.com/#lemonade-sdk/infinity-arcade">
    <img src="https://img.shields.io/badge/Star%20History-View-brightgreen" alt="Star History Chart" /></a>
</p>

Create playable retro-style games with LLMs in minutes! Enter your prompt and your game pops open, it's that simple.

Push your imagination to the limit, it's 100% free and local.

![Infinity Arcade GIF](https://github.com/lemonade-sdk/assets/blob/main/arcade/infinity-arcade-demo.gif?raw=true)


## Hardware Requirement

Infinity Arcade will detect the hardware you have available and load a recommended LLM.

| Configuration | GPU/APU | Memory | Disk Space | LLM |
|---------------|---------|---------|---------|---------|
| **Minimum (CPU)** | Ryzen AI 7000-series chip or newer | 32 GB RAM | 5 GB | [Playable1-GGUF](https://huggingface.co/playable/Playable1-GGUF) |
| **Suggested (iGPU)** | Ryzen AI 300-series chip or newer | 32 GB RAM | 5 GB | [Playable1-GGUF](https://huggingface.co/playable/Playable1-GGUF) |
| **Suggested (dGPU)** | Radeon 7800XT or newer | 16 GB VRAM | 20 GB | Qwen3-Coder-30B |
| **Suggested (APU)** | Strix Halo (Ryzen AI MAX 395) | 64 GB unified memory | 20 GB | Qwen3-Coder-30B |

## Quick Start


<p align="center">Windows: click this:</p>
<p align="center">
   <a href="https://github.com/lemonade-sdk/infinity-arcade/releases/latest/download/InfinityArcade.exe"><img src=img/icon.ico?raw=true alt="Arcade Quick Start"/></a>
</p>

<p align="center">
   Linux: click <a href="#linux-and-windows-devs">this</a>
</p>

## Overview

Infinity Arcade combines the convenience of a ChatGPT-like interface with the concept of a game emulator. Instead of emulating existing games, it uses LLMs (served by [Lemonade](https://github.com/lemonade-sdk/lemonade)) to generate completely new games based on your prompts, then lets you play them instantly.

## Features

- **Lemonade integration**: automatically connects to Lemonade Server and has access to any Lemonade LLM.
- **AI Game Generation**: Describe a game concept and watch as an LLM creates a playable Python game.
- **Game Library**: All generated games are saved and can be replayed anytime.
- **Easy Management**: View game source code, copy prompts for remixing, and delete games you don't want with a simple click.

## Installation

### Windows

Navigate to the [Releases page](https://github.com/lemonade-sdk/infinity-arcade/releases), download the .exe, and get started!

### Linux (and Windows Devs)

From PyPI (recommended):

```bash
pip install infinity-arcade
infinity-arcade
```

From Source:

1. Clone this repository:
   ```bash
   git clone https://github.com/lemonade-sdk/infinity-arcade
   cd infinity-arcade
   ```

2. Install the package:
   ```bash
   pip install -e .
   ```

3. Run it:
   ```bash
   infinity-arcade
   ```

## Architecture

### Game Generation

Games are generated with the following constraints:
- Pure Python using the pygame library only.
- No external images, sounds, or asset files.
- Complete and playable with proper game mechanics.
- Proper event handling and game loops.
- Visual appeal using pygame's built-in drawing functions.

> Note: LLMs are imperfect, and may fail to generate the game you asked for or fail to generate a functioning game at all.

### Game Cache

Games are cached under the `.infinity-arcade` folder in your home directory.

```
~/.infinity-arcade/
└── games/
    ├── metadata.json    # Game titles and descriptions
    ├── abc12345.py      # Generated game files
    └── xyz67890.py
```

## Troubleshooting

### "Server Offline" Status
- Ensure Lemonade Server is running on `http://localhost:8000`.
- Check that you have models installed in Lemonade Server by opening the model manager: http://localhost:8000/#model-management.
- Visit [lemonade-server.ai](https://lemonade-server.ai) for setup instructions.

### Game Won't Launch
- Check the generated code for any syntax errors.
- Try regenerating the game with a more specific prompt.

### Generation Failures
- Try a simpler game concept.
- Make sure your selected model supports code generation.
- Check the `infinity-arcade` and Lemonade Server logs for errors.

## Examples

Here are some example prompts that work well:

- **Classic Games**: "pong", "tetris", "pacman maze game", "asteroids"
- **Variations**: "snake but food teleports", "breakout with power-ups", "flappy bird in space"
- **Original Ideas**: "catching falling stars", "color matching puzzle", "maze with moving walls"

## Contributing

Contributions are welcome! Feel free to:
- Share interesting game prompts and results by opening an issue!
- Report bugs or request features via GitHub issues.
- Submit pull requests for improvements.


## License and Attribution

This project is licensed under the [MIT license](./LICENSE). It was built with Python with ❤️ for the gaming and LLM communities. It is built on the shoulders of many great open source tools, including llama.cpp, Hugging Face Hub, and OpenAI API.

Most of the code for this project was generated by Claude Sonnet 4.

## Maintainer

This project is maintained by @jeremyfowers.


<!--Copyright (c) 2025 AMD-->
