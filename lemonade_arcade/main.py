#!/usr/bin/env python3
"""
Lemonade Arcade - Main FastAPI application
"""

import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import (
    JSONResponse,
    StreamingResponse,
    RedirectResponse,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates


LEMONADE_VERSION = "8.1.4"

# Pygame will be imported on-demand to avoid early DLL loading issues
pygame = None

if os.environ.get("LEMONADE_ARCADE_MODEL"):
    REQUIRED_MODEL = os.environ.get("LEMONADE_ARCADE_MODEL")
else:
    REQUIRED_MODEL = "Qwen3-Coder-30B-A3B-Instruct-GGUF"

# Set up logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("lemonade_arcade.main")


def get_resource_path(relative_path):
    """Get absolute path to resource, works for dev and for PyInstaller"""
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
        # In PyInstaller bundle, resources are under lemonade_arcade/
        if relative_path in ["static", "templates", "builtin_games"]:
            return os.path.join(base_path, "lemonade_arcade", relative_path)
        else:
            return os.path.join(base_path, relative_path)
    except Exception:
        # Use the directory of this file as the base path for development
        base_path = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(base_path, relative_path)


app = FastAPI(title="Lemonade Arcade", version="0.1.0")

# Set up static files and templates
STATIC_DIR = get_resource_path("static")
TEMPLATES_DIR = get_resource_path("templates")

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Global state
LEMONADE_SERVER_URL = "http://localhost:8000"
GAMES_DIR = Path.home() / ".lemonade-arcade" / "games"
RUNNING_GAMES: Dict[str, subprocess.Popen] = {}
GAME_METADATA: Dict[str, Dict] = {}

# Server management state
SERVER_COMMAND = None  # Track which command is used for this server instance
SERVER_PROCESS = None  # Track the server process to avoid starting multiple instances

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


# Built-in games configuration
BUILTIN_GAMES = {
    "builtin_snake": {
        "title": "Dynamic Snake",
        "created": 0,  # Special marker for built-in games
        "prompt": "Snake but the food moves around",
        "builtin": True,
        "file": "snake_moving_food.py",
    },
    "builtin_invaders": {
        "title": "Rainbow Space Invaders",
        "created": 0,  # Special marker for built-in games
        "prompt": "Space invaders with rainbow colors",
        "builtin": True,
        "file": "rainbow_space_invaders.py",
    },
}

# Add built-in games to metadata if not already present
for game_id, game_data in BUILTIN_GAMES.items():
    if game_id not in GAME_METADATA:
        GAME_METADATA[game_id] = game_data.copy()


def save_metadata():
    """Save game metadata to disk."""
    try:
        with open(METADATA_FILE, "w") as f:
            json.dump(GAME_METADATA, f, indent=2)
    except Exception as e:
        print(f"Error saving metadata: {e}")


def is_pyinstaller_environment():
    """Check if we're running in a PyInstaller bundle."""
    return getattr(sys, "frozen", False)


def find_lemonade_server_paths():
    """Find actual lemonade-server installation paths by checking the environment."""
    paths = []

    # Check current PATH for lemonade_server/bin directories
    current_path = os.environ.get("PATH", "")
    # Use the correct path separator for the platform
    path_separator = ";" if sys.platform == "win32" else ":"
    for path_entry in current_path.split(path_separator):
        path_entry = path_entry.strip()
        if "lemonade_server" in path_entry.lower() and "bin" in path_entry.lower():
            if os.path.exists(path_entry):
                paths.append(path_entry)
                logger.info(f"Found lemonade-server path in PATH: {path_entry}")

    return paths


def reset_server_state():
    """Reset server state when installation changes."""
    global SERVER_COMMAND, SERVER_PROCESS
    logger.info("Resetting server state")
    SERVER_COMMAND = None
    if SERVER_PROCESS and SERVER_PROCESS.poll() is None:
        try:
            SERVER_PROCESS.terminate()
        except:
            pass
    SERVER_PROCESS = None


def refresh_environment():
    """Refresh the current process environment variables from the system."""
    try:
        import winreg
        import subprocess

        logger.info("Refreshing environment variables...")

        # Get system PATH
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment",
        ) as key:
            system_path = winreg.QueryValueEx(key, "PATH")[0]

        # Get user PATH
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment") as key:
                user_path = winreg.QueryValueEx(key, "PATH")[0]
        except FileNotFoundError:
            user_path = ""

        # Combine and update current process environment
        new_path = system_path
        if user_path:
            new_path = user_path + ";" + system_path

        os.environ["PATH"] = new_path
        logger.info(f"Updated PATH: {new_path[:200]}...")  # Log first 200 chars

    except Exception as e:
        logger.warning(f"Failed to refresh environment: {e}")


async def execute_lemonade_server_command(
    args: List[str],
    timeout: int = 10,
    use_popen: bool = False,
    stdout_file=None,
    stderr_file=None,
):
    """
    Execute a lemonade-server command with the appropriate binary/method.

    Args:
        args: Command arguments (e.g., ["--version"], ["status"], ["serve"])
        timeout: Timeout in seconds for subprocess.run (ignored for Popen)
        use_popen: If True, use Popen for background processes, otherwise use run
        stdout_file: File object for stdout (only used with use_popen=True)
        stderr_file: File object for stderr (only used with use_popen=True)

    Returns:
        For subprocess.run: subprocess.CompletedProcess
        For subprocess.Popen: subprocess.Popen instance
        Returns None if all commands failed
    """
    global SERVER_COMMAND
    logger.info(f"Executing lemonade-server command with args: {args}")

    # If we already know which command to use, use only that one
    if SERVER_COMMAND:
        commands_to_try = [SERVER_COMMAND + args]
    else:
        # Try different ways to find lemonade-server based on platform
        commands_to_try = []

        if sys.platform == "win32":
            # Windows: Try multiple options including PyInstaller and pip installs
            if not is_pyinstaller_environment():
                commands_to_try.append(["lemonade-server-dev"] + args)

            # Windows traditional commands
            commands_to_try.extend(
                [
                    ["lemonade-server"] + args,
                    ["lemonade-server.bat"] + args,
                ]
            )

            # Add dynamically discovered Windows paths
            for bin_path in find_lemonade_server_paths():
                commands_to_try.extend(
                    [
                        [os.path.join(bin_path, "lemonade-server.exe")] + args,
                        [os.path.join(bin_path, "lemonade-server.bat")] + args,
                    ]
                )
        else:
            # Linux/Unix: Only lemonade-server-dev works (from pip install lemonade-sdk)
            commands_to_try.append(["lemonade-server-dev"] + args)

    for i, cmd in enumerate(commands_to_try):
        try:
            logger.info(f"Trying command {i+1}: {cmd}")

            if use_popen:
                # For background processes (like server start)
                # Convert command list to string for shell=True
                cmd_str = " ".join(cmd)
                process = subprocess.Popen(
                    cmd_str,
                    stdout=stdout_file or subprocess.PIPE,
                    stderr=stderr_file or subprocess.PIPE,
                    creationflags=(
                        subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
                    ),
                    shell=True,  # Use shell=True to help with PATH resolution
                )

                # Store the successful command for future use
                if not SERVER_COMMAND:
                    SERVER_COMMAND = cmd[
                        : -len(args)
                    ]  # Remove the args to get base command
                    logger.info(f"Stored server command: {SERVER_COMMAND}")

                return process
            else:
                # For regular commands with output
                # Convert command list to string for shell=True
                cmd_str = " ".join(cmd)
                result = subprocess.run(
                    cmd_str,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    shell=True,  # Use shell=True to help with PATH resolution
                )
                logger.info(f"Command {i+1} returned code: {result.returncode}")
                logger.info(f"Command {i+1} stdout: '{result.stdout}'")
                logger.info(f"Command {i+1} stderr: '{result.stderr}'")

                if result.returncode == 0:
                    # Store the successful command for future use
                    if not SERVER_COMMAND:
                        SERVER_COMMAND = cmd[
                            : -len(args)
                        ]  # Remove the args to get base command
                        logger.info(f"Stored server command: {SERVER_COMMAND}")

                    return result
                else:
                    logger.warning(
                        f"Command {i+1} failed with return code {result.returncode}"
                    )
                    if result.stderr:
                        logger.warning(f"stderr: {result.stderr}")
                    # Try next command
                    continue

        except FileNotFoundError as e:
            logger.info(f"Command {i+1} not found: {e}")
            continue
        except subprocess.TimeoutExpired as e:
            logger.warning(f"Command {i+1} timed out: {e}")
            continue
        except Exception as e:
            logger.error(f"Unexpected error with command {i+1}: {e}")
            continue

    # If we get here, all commands failed
    logger.error("All lemonade-server commands failed")
    return None


async def check_lemonade_sdk_available():
    """Check if lemonade-sdk package is available in the current environment."""
    logger.info("Checking for lemonade-sdk package...")
    try:
        # Convert command list to string for shell=True
        cmd = [sys.executable, "-c", "import lemonade_server; print('available')"]
        cmd_str = " ".join(cmd)
        result = subprocess.run(
            cmd_str,
            capture_output=True,
            text=True,
            timeout=10,
            shell=True,  # Use shell=True to get updated environment after pip install
        )
        is_available = result.returncode == 0 and "available" in result.stdout
        logger.info(f"lemonade-sdk package available: {is_available}")
        return is_available
    except Exception as e:
        logger.info(f"lemonade-sdk package check failed: {e}")
        return False


async def check_lemonade_server_version():
    """Check if lemonade-server is installed and get its version."""
    logger.info("Checking lemonade-server version...")

    result = await execute_lemonade_server_command(["--version"])

    if result is None:
        logger.error("All lemonade-server commands failed")
        return {"installed": False, "version": None, "compatible": False}

    version_line = result.stdout.strip()
    logger.info(f"Raw version output: '{version_line}'")

    # Extract version number (format might be "lemonade-server 8.1.3" or just "8.1.3")
    import re

    version_match = re.search(r"(\d+\.\d+\.\d+)", version_line)
    if version_match:
        version = version_match.group(1)
        logger.info(f"Extracted version: {version}")

        # Check if the version number is allowed
        version_parts = [int(x) for x in version.split(".")]
        required_parts = [int(x) for x in LEMONADE_VERSION.split(".")]
        is_compatible = version_parts >= required_parts
        logger.info(
            f"Version parts: {version_parts}, Required: {required_parts}, Compatible: {is_compatible}"
        )

        return {
            "installed": True,
            "version": version,
            "compatible": is_compatible,
            "required_version": LEMONADE_VERSION,
        }
    else:
        logger.warning(f"Could not extract version from output: '{version_line}'")
        return {
            "installed": True,
            "version": "unknown",
            "compatible": False,
            "required_version": LEMONADE_VERSION,
        }


async def check_lemonade_server_running():
    """Check if lemonade-server is currently running."""
    logger.info("Checking if lemonade-server is running...")

    result = await execute_lemonade_server_command(["status"])

    if result is None:
        logger.error("All lemonade-server status commands failed")
        return False

    output = result.stdout.strip()
    logger.info(f"Status output: '{output}'")
    if "Server is running" in output:
        logger.info("Server is running according to status command")
        return True
    else:
        logger.info("Server is not running according to status command")
        return False


async def start_lemonade_server():
    """Start lemonade-server in the background."""
    global SERVER_PROCESS
    logger.info("Attempting to start lemonade-server...")

    # Check if server is already running
    if SERVER_PROCESS and SERVER_PROCESS.poll() is None:
        logger.info("Server process is already running")
        return {"success": True, "message": "Server is already running"}

    # Create temp files to capture output for debugging
    import tempfile

    stdout_file = tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".log")
    stderr_file = tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".log")

    # Use the unified function to start the server
    process = await execute_lemonade_server_command(
        ["serve"], use_popen=True, stdout_file=stdout_file, stderr_file=stderr_file
    )

    if process is None:
        logger.error("All lemonade-server start commands failed")
        stdout_file.close()
        stderr_file.close()
        try:
            os.unlink(stdout_file.name)
            os.unlink(stderr_file.name)
        except:
            pass
        return {
            "success": False,
            "message": "Failed to start server: all commands failed",
        }

    # Give the process a moment to start and check if it's still running
    import time

    time.sleep(1)

    # Check if process is still alive
    if process.poll() is None:
        logger.info(f"Successfully started lemonade-server with PID: {process.pid}")
        SERVER_PROCESS = process

        # Close temp files
        stdout_file.close()
        stderr_file.close()

        return {"success": True, "message": "Server start command issued"}
    else:
        # Process died immediately, check error output
        stdout_file.close()
        stderr_file.close()

        # Read the error output
        try:
            with open(stderr_file.name, "r") as f:
                stderr_content = f.read().strip()
            with open(stdout_file.name, "r") as f:
                stdout_content = f.read().strip()

            logger.error(
                f"Server failed immediately. Return code: {process.returncode}"
            )
            if stderr_content:
                logger.error(f"Stderr: {stderr_content}")
            if stdout_content:
                logger.info(f"Stdout: {stdout_content}")

            # Clean up temp files
            try:
                os.unlink(stdout_file.name)
                os.unlink(stderr_file.name)
            except:
                pass

        except Exception as read_error:
            logger.error(f"Could not read process output: {read_error}")

        return {"success": False, "message": "Server process died immediately"}


async def install_lemonade_sdk_package():
    """Install lemonade-sdk package using pip."""
    try:
        logger.info("Installing lemonade-sdk package using pip...")

        # Install the package
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "lemonade-sdk"],
            capture_output=True,
            text=True,
            timeout=300,  # 5 minutes timeout
        )

        if result.returncode == 0:
            logger.info("lemonade-sdk package installed successfully")
            return {
                "success": True,
                "message": "lemonade-sdk package installed successfully. You can now use 'lemonade-server-dev' command.",
            }
        else:
            error_msg = result.stderr or result.stdout or "Unknown installation error"
            logger.error(f"pip install failed: {error_msg}")
            return {"success": False, "message": f"pip install failed: {error_msg}"}

    except Exception as e:
        logger.error(f"Failed to install lemonade-sdk package: {e}")
        return {"success": False, "message": f"Failed to install: {e}"}


async def download_and_install_lemonade_server():
    """Download and install lemonade-server using the appropriate method."""

    # Reset server state since we're installing/updating
    reset_server_state()

    # If not in PyInstaller environment, prefer pip installation
    if not is_pyinstaller_environment():
        logger.info(
            "Development environment detected, attempting pip installation first..."
        )
        pip_result = await install_lemonade_sdk_package()
        if pip_result["success"]:
            return pip_result
        else:
            logger.info(
                "pip installation failed, falling back to GitHub instructions..."
            )
            return {
                "success": False,
                "message": "Could not install lemonade-sdk package. Please visit https://github.com/lemonade-sdk/lemonade for installation instructions.",
                "github_link": "https://github.com/lemonade-sdk/lemonade",
            }

    # PyInstaller environment or fallback - use installer for Windows
    try:
        # Download the installer
        installer_url = "https://github.com/lemonade-sdk/lemonade/releases/latest/download/Lemonade_Server_Installer.exe"

        # Create temp directory for installer
        temp_dir = tempfile.mkdtemp()
        installer_path = os.path.join(temp_dir, "Lemonade_Server_Installer.exe")

        logger.info(f"Downloading installer from {installer_url}")

        # Download with progress tracking
        async with httpx.AsyncClient(timeout=300.0, follow_redirects=True) as client:
            async with client.stream("GET", installer_url) as response:
                if response.status_code != 200:
                    return {
                        "success": False,
                        "message": f"Failed to download installer: HTTP {response.status_code}",
                    }

                with open(installer_path, "wb") as f:
                    async for chunk in response.aiter_bytes(8192):
                        f.write(chunk)

        logger.info(f"Downloaded installer to {installer_path}")

        # Run interactive installation (not silent)
        install_cmd = [installer_path]

        logger.info(f"Running interactive installation: {' '.join(install_cmd)}")

        # Start the installer but don't wait for it to complete
        # This allows the user to see the installation UI
        process = subprocess.Popen(install_cmd)

        return {
            "success": True,
            "message": "Installer launched. Please complete the installation and then restart Lemonade Arcade.",
            "interactive": True,
        }

    except Exception as e:
        logger.error(f"Failed to download/install lemonade-server: {e}")
        return {"success": False, "message": f"Failed to install: {e}"}


async def check_lemonade_server():
    """Check if Lemonade Server is running."""
    logger.info(f"Checking Lemonade Server at {LEMONADE_SERVER_URL}")

    # Try multiple times with increasing delays to give server time to start
    for attempt in range(3):
        try:
            # Use a longer timeout and retry logic for more robust checking
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(f"{LEMONADE_SERVER_URL}/api/v1/models")
                logger.info(
                    f"Server check attempt {attempt + 1} response status: {response.status_code}"
                )
                if response.status_code == 200:
                    return True
                elif response.status_code == 404:
                    # Try the health endpoint if models endpoint doesn't exist
                    logger.info("Models endpoint not found, trying health endpoint")
                    try:
                        health_response = await client.get(
                            f"{LEMONADE_SERVER_URL}/health"
                        )
                        logger.info(
                            f"Health check response status: {health_response.status_code}"
                        )
                        return health_response.status_code == 200
                    except Exception as e:
                        logger.info(f"Health check failed: {e}")

        except httpx.TimeoutException:
            logger.info(
                f"Server check attempt {attempt + 1} timed out - server might be starting up"
            )
        except httpx.ConnectError as e:
            logger.info(f"Server check attempt {attempt + 1} connection failed: {e}")
        except Exception as e:
            logger.info(f"Server check attempt {attempt + 1} failed: {e}")

        # Wait before next attempt (except on last attempt)
        if attempt < 2:
            import asyncio

            await asyncio.sleep(2)

    logger.info("All server check attempts failed")
    return False


async def get_available_models():
    """Get list of available models from Lemonade Server."""
    logger.info("Getting available models from Lemonade Server")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{LEMONADE_SERVER_URL}/api/v1/models")
            if response.status_code == 200:
                data = response.json()
                models = [model["id"] for model in data.get("data", [])]
                logger.info(f"Found {len(models)} available models: {models}")
                return models
            else:
                logger.warning(f"Failed to get models, status: {response.status_code}")
    except Exception as e:
        logger.info(f"Error getting models: {e}")
    return []


async def check_required_model():
    """Check if the required model is installed."""
    logger.info(f"Checking for required model: {REQUIRED_MODEL}")

    try:
        models = await get_available_models()
        is_installed = REQUIRED_MODEL in models
        logger.info(f"Required model installed: {is_installed}")
        return {"installed": is_installed, "model_name": REQUIRED_MODEL}
    except Exception as e:
        logger.error(f"Error checking required model: {e}")
        return {"installed": False, "model_name": REQUIRED_MODEL}


async def check_model_loaded():
    """Check if the required model is currently loaded."""
    logger.info(f"Checking if model is loaded: {REQUIRED_MODEL}")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(f"{LEMONADE_SERVER_URL}/api/v1/health")

            if response.status_code == 200:
                status_data = response.json()
                # Check if the required model is the currently loaded model
                loaded_model = status_data.get("model_loaded", "")
                is_loaded = loaded_model == REQUIRED_MODEL
                logger.info(
                    f"Model loaded status: {is_loaded}, current model: {loaded_model}"
                )
                return {
                    "loaded": is_loaded,
                    "model_name": REQUIRED_MODEL,
                    "current_model": loaded_model,
                }
            else:
                logger.warning(
                    f"Failed to get server status: HTTP {response.status_code}"
                )
                return {
                    "loaded": False,
                    "model_name": REQUIRED_MODEL,
                    "current_model": None,
                }
    except Exception as e:
        logger.error(f"Error checking model loaded status: {e}")
        return {"loaded": False, "model_name": REQUIRED_MODEL, "current_model": None}


async def install_required_model():
    """Install the required model using the pull endpoint."""
    logger.info(f"Installing required model: {REQUIRED_MODEL}")

    try:
        async with httpx.AsyncClient(
            timeout=600.0
        ) as client:  # 10 minute timeout for model download
            response = await client.post(
                f"{LEMONADE_SERVER_URL}/api/v1/pull",
                json={"model_name": REQUIRED_MODEL},
                headers={"Content-Type": "application/json"},
            )

            if response.status_code == 200:
                logger.info(f"Successfully installed model: {REQUIRED_MODEL}")
                return {
                    "success": True,
                    "message": f"Model {REQUIRED_MODEL} installed successfully",
                }
            else:
                error_msg = f"Failed to install model: HTTP {response.status_code}"
                logger.error(error_msg)
                return {"success": False, "message": error_msg}
    except httpx.TimeoutException:
        error_msg = (
            "Model installation timed out - this is a large model and may take longer"
        )
        logger.warning(error_msg)
        return {"success": False, "message": error_msg}
    except Exception as e:
        error_msg = f"Error installing model: {e}"
        logger.error(error_msg)
        return {"success": False, "message": error_msg}


async def load_required_model():
    """Load the required model using the load endpoint."""
    logger.info(f"Loading required model: {REQUIRED_MODEL}")

    try:
        async with httpx.AsyncClient(
            timeout=600.0
        ) as client:  # 10 minute timeout for model loading
            response = await client.post(
                f"{LEMONADE_SERVER_URL}/api/v1/load",
                json={"model_name": REQUIRED_MODEL},
                headers={"Content-Type": "application/json"},
            )

            if response.status_code == 200:
                logger.info(f"Successfully loaded model: {REQUIRED_MODEL}")
                return {
                    "success": True,
                    "message": f"Model {REQUIRED_MODEL} loaded successfully",
                }
            else:
                error_msg = f"Failed to load model: HTTP {response.status_code}"
                logger.error(error_msg)
                return {"success": False, "message": error_msg}
    except httpx.TimeoutException:
        error_msg = "Model loading timed out"
        logger.warning(error_msg)
        return {"success": False, "message": error_msg}
    except Exception as e:
        error_msg = f"Error loading model: {e}"
        logger.error(error_msg)
        return {"success": False, "message": error_msg}


async def generate_game_title(prompt: str) -> str:
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
                    "model": REQUIRED_MODEL,
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

    # Check if it's a built-in game
    if game_id in BUILTIN_GAMES:
        # For built-in games, use the file from the builtin_games directory
        builtin_games_dir = get_resource_path("builtin_games")
        game_file = Path(builtin_games_dir) / BUILTIN_GAMES[game_id]["file"]
        logger.debug(f"Looking for built-in game file at: {game_file}")
    else:
        # For user-generated games, use the standard games directory
        game_file = GAMES_DIR / f"{game_id}.py"
        logger.debug(f"Looking for user game file at: {game_file}")

    if not game_file.exists():
        logger.error(f"Game file not found: {game_file}")
        raise FileNotFoundError(f"Game file not found: {game_file}")

    # Launch the game
    try:
        # In PyInstaller environment, use the same executable with the game file as argument
        # This ensures the game runs with the same DLL configuration
        if getattr(sys, "frozen", False):
            # We're in PyInstaller - use the same executable that has the SDL2 DLLs
            cmd = [sys.executable, str(game_file)]
            logger.debug(f"PyInstaller mode - Launching: {' '.join(cmd)}")
        else:
            # Development mode - use regular Python
            cmd = [sys.executable, str(game_file)]
            logger.debug(f"Development mode - Launching: {' '.join(cmd)}")

        process = subprocess.Popen(cmd)
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


@app.get("/favicon.ico")
async def favicon():
    """Redirect to favicon in static directory."""
    return RedirectResponse(url="/static/favicon.ico")


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


@app.get("/api/installation-status")
async def installation_status():
    """Check lemonade-server installation status ONLY."""
    logger.info("Installation status endpoint called")
    version_info = await check_lemonade_server_version()
    logger.info(f"Version check result: {version_info}")

    result = {
        "installed": version_info["installed"],
        "version": version_info["version"],
        "compatible": version_info["compatible"],
        "required_version": version_info["required_version"],
    }
    logger.info(f"Returning installation status: {result}")
    return JSONResponse(result)


@app.get("/api/server-running-status")
async def server_running_status():
    """Check if lemonade-server is running ONLY, and auto-start if needed."""
    logger.info("=== Server running status endpoint called ===")

    # Check if server is currently running
    is_running = await check_lemonade_server_running()
    logger.info(f"Initial running check result: {is_running}")

    # If server is not running, try to start it automatically
    if not is_running:
        logger.info("Server not running, attempting to start automatically...")
        start_result = await start_lemonade_server()
        logger.info(f"Auto-start result: {start_result}")

        if start_result["success"]:
            # Give it a moment to start up
            import asyncio

            logger.info("Waiting 2 seconds for server to initialize...")
            await asyncio.sleep(2)

            # Check again
            is_running = await check_lemonade_server_running()
            logger.info(f"Running check after auto-start: {is_running}")
        else:
            logger.warning(
                f"Auto-start failed: {start_result.get('error', 'Unknown error')}"
            )

    result = {
        "running": is_running,
    }
    logger.info(f"=== Returning server running status: {result} ===")
    return JSONResponse(result)


@app.get("/api/api-connection-status")
async def api_connection_status():
    """Check API connection status ONLY."""
    logger.info("=== API connection status endpoint called ===")
    api_online = await check_lemonade_server()
    logger.info(f"API online check result: {api_online}")

    result = {
        "api_online": api_online,
    }
    logger.info(f"=== Returning API connection status: {result} ===")
    return JSONResponse(result)


@app.get("/api/model-installation-status")
async def model_installation_status():
    """Check if required model is installed ONLY."""
    logger.info("Model installation status endpoint called")
    model_status = await check_required_model()
    logger.info(f"Model check result: {model_status}")

    result = {
        "model_installed": model_status["installed"],
        "model_name": model_status["model_name"],
    }
    logger.info(f"Returning model installation status: {result}")
    return JSONResponse(result)


@app.get("/api/model-loading-status")
async def model_loading_status():
    """Check if required model is loaded ONLY."""
    logger.info("Model loading status endpoint called")
    model_loaded_status = await check_model_loaded()
    logger.info(f"Model loaded check result: {model_loaded_status}")

    result = {
        "model_loaded": model_loaded_status["loaded"],
        "model_name": model_loaded_status["model_name"],
        "current_model": model_loaded_status["current_model"],
    }
    logger.info(f"Returning model loading status: {result}")
    return JSONResponse(result)


@app.get("/api/installation-environment")
async def installation_environment():
    """Check installation environment and available methods."""
    logger.info("Installation environment endpoint called")

    is_pyinstaller = is_pyinstaller_environment()
    sdk_available = (
        await check_lemonade_sdk_available() if not is_pyinstaller else False
    )

    result = {
        "is_pyinstaller": is_pyinstaller,
        "sdk_available": sdk_available,
        "platform": sys.platform,
        "preferred_method": "pip" if not is_pyinstaller else "installer",
    }

    logger.info(f"Returning installation environment: {result}")
    return JSONResponse(result)


@app.post("/api/refresh-environment")
async def refresh_environment_endpoint():
    """Refresh environment variables after installation."""
    logger.info("Refresh environment endpoint called")
    try:
        refresh_environment()
        # Also reset server state so it will re-discover commands
        reset_server_state()
        return JSONResponse({"success": True, "message": "Environment refreshed"})
    except Exception as e:
        logger.error(f"Failed to refresh environment: {e}")
        return JSONResponse(
            {"success": False, "message": f"Failed to refresh environment: {e}"}
        )


@app.post("/api/install-server")
async def install_server():
    """Download and install lemonade-server."""
    logger.info("Install server endpoint called")
    result = await download_and_install_lemonade_server()
    logger.info(f"Install result: {result}")
    return JSONResponse(result)


@app.post("/api/start-server")
async def start_server():
    """Start lemonade-server if installed."""
    logger.info("Start server endpoint called")
    result = await start_lemonade_server()
    logger.info(f"Start server result: {result}")
    return JSONResponse(result)


@app.post("/api/install-model")
async def install_model():
    """Install the required model."""
    logger.info("Install model endpoint called")
    result = await install_required_model()
    logger.info(f"Install model result: {result}")
    return JSONResponse(result)


@app.post("/api/load-model")
async def load_model():
    """Load the required model."""
    logger.info("Load model endpoint called")
    result = await load_required_model()
    logger.info(f"Load model result: {result}")
    return JSONResponse(result)


@app.post("/api/create-game")
async def create_game_endpoint(request: Request):
    """Create a new game using LLM."""
    logger.debug("Starting game creation endpoint")

    data = await request.json()
    prompt = data.get("prompt", "")

    logger.debug(f"Received request - prompt: '{prompt[:50]}...'")

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
                        "model": REQUIRED_MODEL,
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

            game_title = await generate_game_title(prompt)

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

    # Prevent deletion of built-in games
    if game_id in BUILTIN_GAMES:
        raise HTTPException(status_code=403, detail="Cannot delete built-in games")

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

    metadata = GAME_METADATA[game_id].copy()

    # For built-in games, hide sensitive information
    if game_id in BUILTIN_GAMES:
        # Remove prompt and other sensitive data for built-in games
        metadata.pop("prompt", None)
        metadata["builtin"] = True

    return JSONResponse(metadata)


@app.post("/api/open-game-file/{game_id}")
async def open_game_file(game_id: str):
    """Open the Python file for a game in the default editor."""
    if game_id not in GAME_METADATA:
        raise HTTPException(status_code=404, detail="Game not found")

    # Prevent opening built-in game files
    if game_id in BUILTIN_GAMES:
        raise HTTPException(
            status_code=403, detail="Cannot view source code of built-in games"
        )

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


def run_game_file(game_file_path):
    """Run a game file directly - used when executable is called with a game file."""
    try:
        print(f"Lemonade Arcade - Running game: {game_file_path}")

        # Import pygame here, right before we need it
        global pygame
        if pygame is None:
            try:
                import pygame

                print(f"Pygame {pygame.version.ver} loaded successfully")
            except ImportError as e:
                print(f"Error: Failed to import pygame: {e}")
                sys.exit(1)

        # Read and execute the game file
        with open(game_file_path, "r", encoding="utf-8") as f:
            game_code = f.read()

        # Execute the game code - pygame should now be available
        exec(game_code, {"__name__": "__main__", "__file__": game_file_path})

    except Exception as e:
        print(f"Error running game {game_file_path}: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


def main():
    """Main entry point for the application."""
    # Check if we're being called to run a specific game file
    if len(sys.argv) == 2 and sys.argv[1].endswith(".py"):
        # Game mode: run the specified game file
        run_game_file(sys.argv[1])
        return

    # Server mode: start the Lemonade Arcade server
    import webbrowser
    import threading

    # Keep console visible for debugging and control
    print("Starting Lemonade Arcade...")
    print("Press Ctrl+C to quit")

    port = 8080

    # Start the server in a separate thread
    def run_server():
        print(f"Starting Lemonade Arcade server on http://127.0.0.1:{port}")
        try:
            uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
        except Exception as e:
            print(f"Error starting server: {e}")

    print("Launching server thread...")
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()

    # Wait a moment then open browser
    print("Waiting for server to start...")
    time.sleep(3)
    print(f"Opening browser to http://127.0.0.1:{port}")
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

# Copyright (c) 2025 AMD
