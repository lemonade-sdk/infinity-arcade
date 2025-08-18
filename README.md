
![Lemonade Arcade Banner](./img/banner.png)

<p align="center">
  <a href="https://discord.gg/5xXzkMu8Zk">
    <img src="https://img.shields.io/badge/Discord-7289DA?logo=discord&logoColor=white" alt="Discord" />
  </a>
  <a href="docs/README.md#installation" title="Check out our instructions">
    <img src="https://img.shields.io/badge/Windows-11-0078D6?logo=windows&logoColor=white" alt="Windows 11" />
  </a>
  <a href="https://lemonade-server.ai/#linux" title="Ubuntu 24.04 & 25.04 Supported">
    <img src="https://img.shields.io/badge/Ubuntu-24.04%20%7C%2025.04-E95420?logo=ubuntu&logoColor=white" alt="Ubuntu 24.04 | 25.04" />
  </a>
  <a href="#installation" title="Check out our instructions">
    <img src="https://img.shields.io/badge/Python-3.10--3.13-blue?logo=python&logoColor=white" alt="Made with Python" />
  </a>
  <a href="https://github.com/lemonade-sdk/lemonade-arcade/releases/latest" title="Download the latest release">
    <img src="https://img.shields.io/github/v/release/lemonade-sdk/lemonade-arcade?include_prereleases" alt="Latest Release" />
  </a>
  <a href="https://tooomm.github.io/github-release-stats/?username=lemonade-sdk&repository=lemonade">
    <img src="https://img.shields.io/github/downloads/lemonade-sdk/lemonade-arcade/total.svg" alt="GitHub downloads" />
  </a>
  <a href="https://github.com/lemonade-sdk/lemonade-arcade/blob/main/LICENSE">
    <img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License: MIT" />
  </a>
  <a href="https://star-history.com/#lemonade-sdk/lemonade-arcade">
    <img src="https://img.shields.io/badge/Star%20History-View-brightgreen" alt="Star History Chart" />
  </a>
</p>

Use your overpowered GPU run AI that produces creative retro-style games! Enter your prompt, and the playable game pops open in minutes.

Push your imagination to the limit, it's 100% free and local.


## Hardware Requirement

Lemonade Arcade uses a 30 billion parameter LLM to generate games, which requires certain hardware specs to run well.

| Configuration | GPU/APU | Memory | Disk Space |
|---------------|---------|---------|---------|
| **Minimum (CPU)** | Ryzen AI 7000-series chip or newer | 64 GB RAM | 20 GB |
| **Suggested (dGPU)** | Radeon 7800XT or newer | 16 GB VRAM | 20 GB |
| **Suggested (APU)** | Strix Halo (Ryzen AI MAX 395) | 64 GB unified memory | 20 GB |

## Quick Start


<p align="center">Windows: click this:</p>
<p align="center">
   <img src=https://github.com/lemonade-sdk/assets/blob/main/arcade/exe_icon.png?raw=true alt="Arcade Quick Start"/>
</p>

<p align="center">
   Linux: click <a href="#linux-and-windows-devs">this</a>
</p>

## Demo

> [!TIP]
> Generate creative new retro-style games in minutes, based on prompts like `Make space invaders, but I can fly around the whole screen instead of being stuck on the bottom.`

![Lemonade Arcade GIF](https://github.com/lemonade-sdk/assets/blob/main/arcade/space_invaders_x.gif?raw=true)

> [!TIP]
> Right click any game you've generated to get the Python source code or the prompt, so you can edit and remix further!


<img src="https://github.com/lemonade-sdk/assets/blob/main/arcade/home2.png?raw=true" alt="Lemonade Arcade UI" width="75%">

> [!TIP]
> Everything you need to run an LLM on your GPU is automatically set up for you.

<img src="https://github.com/lemonade-sdk/assets/blob/main/arcade/setup.png?raw=true" alt="Lemonade Arcade setup" width="50%">

## Overview

Lemonade Arcade combines the convenience of a ChatGPT-like interface with the concept of a game emulator. Instead of emulating existing games, it uses LLMs (served by [Lemonade](https://github.com/lemonade-sdk/lemonade)) to generate completely new games based on your prompts, then lets you play them instantly.

## Features

- **Lemonade integration**: automatically connects to Lemonade Server and has access to any Lemonade LLM.
- **AI Game Generation**: Describe a game concept and watch as an LLM creates a playable Python game.
- **Game Library**: All generated games are saved and can be replayed anytime.
- **Easy Management**: View game source code, copy prompts for remixing, and delete games you don't want with a simple click.

## Installation

### Windows

Navigate to the [Releases page](https://github.com/lemonade-sdk/lemonade-arcade/releases), download the .exe, and get started!

### Linux (and Windows Devs)

1. Clone this repository:
   ```bash
   git clone https://github.com/lemonade-sdk/lemonade-arcade
   cd lemonade-arcade
   ```

2. Install the package:
   ```bash
   pip install -e .
   ```

3. Run it:
   ```bash
   lemonade-arcade
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

Games are cached under the `.lemonade-arcade` folder in your home directory.

```
~/.lemonade-arcade/
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
- Check the `lemonade-arcade` and Lemonade Server logs for errors.

## Examples

Here are some example prompts that work well:

- **Classic Games**: "pong", "tetris", "pacman maze game", "asteroids"
- **Variations**: "snake but food teleports", "breakout with power-ups", "flappy bird in space"
- **Original Ideas**: "catching falling stars", "color matching puzzle", "maze with moving walls"

## Contributing

Contributions are welcome! Feel free to:
- Report bugs or request features via GitHub issues.
- Submit pull requests for improvements.
- Share interesting game prompts and results.

## License and Attribution

This project is licensed under the [MIT license](./LICENSE). It was built with Python with ❤️ for the gaming and LLM communities. It is built on the shoulders of many great open source tools, including llama.cpp, Hugging Face Hub, and OpenAI API.

Most of the code for this project was generated by Claude Sonnet 4.

## Maintainer

This project is maintained by @jeremyfowers.


<!--Copyright (c) 2025 AMD-->