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
import time
import uuid
from pathlib import Path
from typing import Dict, Optional, Union
from dataclasses import dataclass

import httpx
import uvicorn
from openai import AsyncOpenAI
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import (
    JSONResponse,
    StreamingResponse,
    RedirectResponse,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.responses import Response

import lemonade_arcade.lemonade_client as lc

lemonade_handle = lc.LemonadeClient()


@dataclass
class ExtractedCode:
    """Represents successfully extracted Python code from an LLM response."""

    code: str
    length: int

    def __post_init__(self):
        """Validate the extracted code."""
        if not self.code or not isinstance(self.code, str):
            raise ValueError("Code must be a non-empty string")
        if self.length != len(self.code):
            raise ValueError("Length must match the actual code length")

    def __str__(self) -> str:
        return self.code


# Pygame will be imported on-demand to avoid early DLL loading issues
# pylint: disable=invalid-name
pygame = None

if os.environ.get("LEMONADE_ARCADE_MODEL"):
    REQUIRED_MODEL = os.environ.get("LEMONADE_ARCADE_MODEL")
else:
    REQUIRED_MODEL = "Qwen3-Coder-30B-A3B-Instruct-GGUF"

# Logger will be configured by CLI or set to INFO if run directly
logger = logging.getLogger("lemonade_arcade.main")


def get_resource_path(relative_path):
    """Get absolute path to resource, works for dev and for PyInstaller"""
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        # pylint: disable=protected-access,no-member
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


class NoCacheStaticFiles(StaticFiles):
    """Custom StaticFiles class with no-cache headers"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def file_response(self, *args, **kwargs) -> Response:
        response = super().file_response(*args, **kwargs)
        # Add no-cache headers for all static files
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response


app.mount("/static", NoCacheStaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


class ArcadeGames:
    """
    Keep track of the state of saved and running games.
    """

    def __init__(self):

        # Global state
        self.games_dir = Path.home() / ".lemonade-arcade" / "games"
        self.running_games: Dict[str, subprocess.Popen] = {}
        self.game_metadata: Dict[str, Dict] = {}

        # Ensure games directory exists
        self.games_dir.mkdir(parents=True, exist_ok=True)

        # Load existing game metadata
        self.metadata_file = self.games_dir / "metadata.json"
        if self.metadata_file.exists():
            try:
                with open(self.metadata_file, "r", encoding="utf-8") as metadata_file:
                    self.game_metadata = json.load(metadata_file)
            except Exception:
                self.game_metadata = {}

        # Built-in games configuration
        self.BUILTIN_GAMES = {
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
        for game_id, game_data in self.BUILTIN_GAMES.items():
            if game_id not in self.game_metadata:
                self.game_metadata[game_id] = game_data.copy()

    def save_metadata(self):
        """Save game metadata to disk."""
        try:
            with open(self.metadata_file, "w", encoding="utf-8") as f:
                json.dump(self.game_metadata, f, indent=2)
        except Exception as e:
            print(f"Error saving metadata: {e}")

    async def launch_game(self, game_id: str, max_retries: int = 1) -> tuple[bool, str]:
        """Launch a game in a separate process and capture any immediate errors.
        If the game fails and it's a user-generated game, attempt to fix it using LLM.
        This is a simple wrapper around launch_game_with_streaming for non-streaming cases.

        Args:
            game_id: Unique identifier for the game
            max_retries: Maximum number of automatic retry attempts (default: 1)

        Returns:
            tuple: (success: bool, message: str)
        """
        # For non-streaming cases, we'll collect the final result from the streaming version

        final_result = None

        async for stream_item in self.launch_game_with_streaming(
            game_id, max_retries=max_retries
        ):
            # Parse the stream item to get the final result
            if '"type": "complete"' in stream_item:
                # Extract the message from the JSON
                try:
                    data = json.loads(stream_item.replace("data: ", "").strip())
                    final_result = (
                        True,
                        data.get("message", "Game launched successfully"),
                    )
                except:
                    final_result = (True, "Game launched successfully")
                break
            elif '"type": "error"' in stream_item:
                # Extract the error message from the JSON
                try:
                    data = json.loads(stream_item.replace("data: ", "").strip())
                    final_result = (False, data.get("message", "Game failed to launch"))
                except:
                    final_result = (False, "Game failed to launch")
                break

        if final_result is None:
            final_result = (False, "Unexpected error during game launch")

        return final_result

    def _attempt_game_launch(self, game_id: str, game_file: Path) -> tuple[bool, str]:
        """Attempt to launch a game and return success status and any error message."""
        # Launch the game with error capture
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

            # Launch with pipes to capture output
            # pylint: disable=consider-using-with
            process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )

            start_time = time.time()
            logger.debug(f"Game {game_id} subprocess started with PID {process.pid}")

            # Give the process a moment to start and check for immediate errors
            try:
                stdout, stderr = process.communicate(timeout=2)
                end_time = time.time()
                duration = end_time - start_time
                # Process exited within 2 seconds - this is likely an error for pygame games
                # Even if return code is 0, pygame games should keep running
                logger.debug(
                    f"Game {game_id} subprocess (PID {process.pid}) EXITED after {duration:.3f} "
                    f"seconds with return code {process.returncode}"
                )

                # Filter out pygame warnings from stderr to get actual errors
                stderr_lines = stderr.strip().split("\n") if stderr else []
                actual_errors = []

                for line in stderr_lines:
                    # Skip pygame deprecation warnings and other noise
                    if any(
                        skip_phrase in line
                        for skip_phrase in [
                            "UserWarning",
                            "pkg_resources is deprecated",
                            "from pkg_resources import",
                            "pygame community",
                            "https://www.pygame.org",
                        ]
                    ):
                        continue
                    # Only include lines that look like actual errors
                    # (have common error indicators)
                    if line.strip() and any(
                        error_indicator in line
                        for error_indicator in [
                            "Error",
                            "Exception",
                            "Traceback",
                            'File "',
                            "line ",
                            "NameError",
                            "ImportError",
                            "SyntaxError",
                            "AttributeError",
                            "TypeError",
                            "ValueError",
                        ]
                    ):
                        actual_errors.append(line)

                filtered_stderr = "\n".join(actual_errors).strip()

                # Debug logging to see what we captured
                print(f"DEBUG: filtered_stderr length: {len(filtered_stderr)}")
                print(f"DEBUG: filtered_stderr content: '{filtered_stderr}'")
                print(f"DEBUG: process.returncode: {process.returncode}")

                if filtered_stderr:
                    error_msg = filtered_stderr
                    print("DEBUG: Using filtered stderr as error message")
                elif process.returncode != 0:
                    # Non-zero exit but no clear error message
                    error_msg = (
                        f"Game exited with code {process.returncode} "
                        "but no error message was captured"
                    )
                    print("DEBUG: Using non-zero exit code message")
                else:
                    # Return code 0 but game exited immediately - likely missing game loop
                    error_msg = (
                        "Game completed successfully but exited immediately. "
                        "This usually means the game is missing a proper game loop "
                        "(while True loop) "
                        "or has a logical error that causes it to finish execution quickly."
                    )
                    print("DEBUG: Using missing game loop message")

                if process.returncode != 0:
                    logger.error(
                        f"Game {game_id} failed with return code {process.returncode}: {error_msg}"
                    )
                    print(
                        f"\n=== Game {game_id} Failed (Return Code: {process.returncode}) ==="
                    )
                else:
                    logger.error(
                        f"Game {game_id} exited immediately (return code 0) - "
                        "likely missing game loop or other issue: {error_msg}"
                    )
                    print(
                        f"\n=== Game {game_id} Exited Immediately (Return Code: 0) ==="
                    )

                # Print subprocess output to terminal for debugging
                if stdout:
                    print("STDOUT:")
                    print(stdout)
                if stderr:
                    print("STDERR:")
                    print(stderr)
                if not stdout and not stderr:
                    print("No output captured")
                print("=" * 60)

                return False, error_msg
            except subprocess.TimeoutExpired:
                # Timeout is good - means the game is still running
                end_time = time.time()
                duration = end_time - start_time
                self.running_games[game_id] = process
                logger.debug(
                    f"Game {game_id} subprocess (PID {process.pid}) STILL RUNNING after "
                    f"{duration:.3f} seconds timeout - this is GOOD for pygame games"
                )
                return True, "Game launched successfully"

        except Exception as e:
            logger.error(f"Error launching game {game_id}: {e}")
            return False, str(e)

    def stop_game(self, game_id: str):
        """Stop a running game."""
        if game_id in self.running_games:
            try:
                process = self.running_games[game_id]
                logger.debug(
                    f"MANUALLY STOPPING game {game_id} subprocess (PID {process.pid})"
                )
                process.terminate()
                # Wait a bit for graceful termination
                try:
                    process.wait(timeout=5)
                    logger.debug(
                        f"Game {game_id} subprocess (PID {process.pid}) terminated gracefully"
                    )
                except subprocess.TimeoutExpired:
                    logger.debug(
                        f"Game {game_id} subprocess (PID {process.pid}) "
                        "did not terminate gracefully, killing..."
                    )
                    process.kill()
                    logger.debug(
                        f"Game {game_id} subprocess (PID {process.pid}) killed"
                    )
            except Exception as e:
                print(f"Error stopping game {game_id}: {e}")
            finally:
                del self.running_games[game_id]

    def cleanup_finished_games(self):
        """Clean up finished game processes."""
        finished = []
        for game_id, process in self.running_games.items():
            if process.poll() is not None:  # Process has finished
                return_code = process.returncode
                logger.debug(
                    f"Game {game_id} subprocess (PID {process.pid})"
                    f"FINISHED with return code {return_code} - cleaning up"
                )
                finished.append(game_id)

        for game_id in finished:
            del self.running_games[game_id]

    async def create_and_launch_game_with_streaming(
        self,
        game_id: str,
        python_code: str,
        prompt: str,
        title: str = None,
        is_remix: bool = False,
    ):
        """
        Create a new game (or remixed game) and launch it with streaming status and content updates.
        This is an async generator that yields streaming messages.

        Args:
            game_id: Unique identifier for the game
            python_code: The game's Python code
            prompt: The original prompt or remix description
            title: Pre-generated title (for remixes) or None to generate one
            is_remix: Whether this is a remix operation
        """
        try:
            # Different status messages for create vs remix
            if is_remix:
                yield f"data: {json.dumps({'type': 'status', 'message': 'Saving remixed game...'})}\n\n"
                operation = "remixed game"
            else:
                yield f"data: {json.dumps({'type': 'status', 'message': 'Creating title...'})}\n\n"
                operation = "game"

            # Save the game file
            game_file = self.games_dir / f"{game_id}.py"
            logger.debug(f"Saving {operation} to: {game_file}")
            with open(game_file, "w", encoding="utf-8") as f:
                f.write(python_code)
            logger.debug(f"{operation.capitalize()} file saved successfully")

            # Generate title if not provided (for new games)
            if title is None:
                logger.debug("Generating game title")
                game_title = await generate_game_title(prompt)
            else:
                game_title = title

            # Save metadata
            self.game_metadata[game_id] = {
                "title": game_title,
                "created": time.time(),
                "prompt": prompt,
            }
            self.save_metadata()
            logger.debug(f"Saved metadata for {operation}: {game_title}")

            # Different launch messages for create vs remix
            launch_message = (
                "Launching remixed game..." if is_remix else "Launching game..."
            )
            yield f"data: {json.dumps({'type': 'status', 'message': launch_message})}\n\n"

            # Use the launch_game_with_streaming method for retry logic and streaming
            async for stream_item in self.launch_game_with_streaming(
                game_id, game_title
            ):
                yield stream_item

        except Exception as e:
            error_type = "remixed game creation" if is_remix else "game creation"
            logger.exception(f"Error in {error_type}: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    async def launch_game_with_streaming(
        self, game_id: str, game_title: str = None, max_retries: int = 1
    ):
        """
        Launch a game with retry logic and streaming status/content updates.
        This is an async generator that yields streaming messages.
        """
        logger.debug(f"Attempting to launch game {game_id}")

        if game_title is None:
            game_title = self.game_metadata.get(game_id, {}).get("title", game_id)

        retry_count = 0

        while retry_count <= max_retries:
            # Check if it's a built-in game
            if game_id in self.BUILTIN_GAMES:
                # For built-in games, use the file from the builtin_games directory
                builtin_games_dir = get_resource_path("builtin_games")
                game_file = (
                    Path(builtin_games_dir) / self.BUILTIN_GAMES[game_id]["file"]
                )
                logger.debug(f"Looking for built-in game file at: {game_file}")
            else:
                # For user-generated games, use the standard games directory
                game_file = self.games_dir / f"{game_id}.py"
                logger.debug(f"Looking for user game file at: {game_file}")

            if not game_file.exists():
                logger.error(f"Game file not found: {game_file}")
                error_msg = f"Game file not found: {game_file}"
                yield f"data: {json.dumps({'type': 'error', 'message': error_msg})}\n\n"
                return

            # Try to launch the game
            success, error_message = self._attempt_game_launch(game_id, game_file)

            if success:
                message = f"Game '{game_title}' created and launched successfully!"
                complete_data = {
                    "type": "complete",
                    "game_id": game_id,
                    "message": message,
                }
                yield f"data: {json.dumps(complete_data)}\n\n"
                return

            # Game failed - check if we should attempt to fix it
            if (
                retry_count < max_retries
                and game_id not in self.BUILTIN_GAMES
                and game_id in self.game_metadata
            ):

                logger.info(
                    f"Game {game_id} failed, attempting automatic retry {retry_count + 1}"
                )

                # Send status update
                status_msg = "Game hit an error, trying to fix it..."
                yield f"data: {json.dumps({'type': 'status', 'message': status_msg})}\n\n"

                # Add a content separator to clearly mark the start of the fix attempt
                error_separator = (
                    f"\n\n---\n\n# ⚠️ ERROR ENCOUNTERED\n\n"
                    f"> 🔧 **The generated game encountered an error during launch.**  \n"
                    f"> **Attempting to automatically fix the code...**\n\n"
                    f"**Error Details:**\n```\n{error_message}\n```\n\n---\n\n"
                    f"## 🛠️ Fix Attempt:\n\n"
                )
                yield f"data: {json.dumps({'type': 'content', 'content': error_separator})}\n\n"

                # Try to fix the code using LLM with streaming
                try:
                    # Read the current game code
                    with open(game_file, "r", encoding="utf-8") as f:
                        current_code = f.read()

                    logger.debug(f"Attempting to fix game {game_id} code using LLM")

                    # Try to fix the code using LLM and stream the output
                    fixed_code = None
                    async for result in generate_game_code_with_llm(
                        "debug", current_code, error_message
                    ):
                        if result is None:
                            # Error occurred in the LLM function
                            logger.error(
                                "Error in generate_game_code_with_llm during debug"
                            )
                            break
                        elif isinstance(result, ExtractedCode):
                            # This is the final extracted code from extract_python_code
                            fixed_code = result.code
                            logger.debug(
                                f"Received fixed code, length: {len(fixed_code)}"
                            )
                            break
                        elif isinstance(result, str):
                            # This is a content chunk, stream it directly
                            content_data = {"type": "content", "content": result}
                            yield f"data: {json.dumps(content_data)}\n\n"

                    if fixed_code:
                        # Save the fixed code
                        with open(game_file, "w", encoding="utf-8") as f:
                            f.write(fixed_code)
                        logger.info(f"Fixed code saved for game {game_id}")
                        retry_count += 1
                        continue
                    else:
                        logger.error(f"Could not get fixed code for game {game_id}")
                        error_msg = (
                            f"Game '{game_title}' failed to launch and could not be "
                            f"automatically fixed: {error_message}"
                        )
                        # pylint: disable=line-too-long
                        final_error_content = f"\n\n---\n\n> ❌ **FINAL ERROR**  \n> {error_msg}\n\n---\n\n"
                        content_data = {
                            "type": "content",
                            "content": final_error_content,
                        }
                        yield f"data: {json.dumps(content_data)}\n\n"
                        error_msg = "Game launch failed after fix attempt"
                        error_data = {"type": "error", "message": error_msg}
                        yield f"data: {json.dumps(error_data)}\n\n"
                        return

                except Exception as e:
                    logger.error(f"Error attempting to fix game {game_id}: {e}")
                    error_msg = f"Error during automatic fix: {str(e)}"
                    # pylint: disable=line-too-long
                    exception_error_content = f"\n\n---\n\n> ❌ **FIX ATTEMPT FAILED**  \n> {error_msg}\n\n---\n\n"
                    content_data = {
                        "type": "content",
                        "content": exception_error_content,
                    }
                    yield f"data: {json.dumps(content_data)}\n\n"
                    error_msg = "Game launch failed during fix attempt"
                    error_data = {"type": "error", "message": error_msg}
                    yield f"data: {json.dumps(error_data)}\n\n"
                    return
            else:
                # No more retries or built-in game failed
                error_msg = f"Game '{game_title}' failed to launch: {error_message}"
                no_retry_error_content = (
                    f"\n\n---\n\n> ❌ **LAUNCH FAILED**  \n> {error_msg}\n\n---\n\n"
                )
                content_data = {"type": "content", "content": no_retry_error_content}
                yield f"data: {json.dumps(content_data)}\n\n"
                yield f"data: {json.dumps({'type': 'error', 'message': 'Game launch failed'})}\n\n"
                return

        # Max retries exceeded
        error_msg = (
            f"Game '{game_title}' failed to launch after {max_retries} "
            f"automatic fix attempts: {error_message}"
        )
        max_retry_error_content = (
            f"\n\n---\n\n> ❌ **MAX RETRIES EXCEEDED**  \n> {error_msg}\n\n---\n\n"
        )
        content_data = {"type": "content", "content": max_retry_error_content}
        yield f"data: {json.dumps(content_data)}\n\n"
        error_data = {
            "type": "error",
            "message": "Game launch failed after max retries",
        }
        yield f"data: {json.dumps(error_data)}\n\n"


arcade_games = ArcadeGames()


async def generate_game_title(prompt: str) -> str:
    """Generate a short title for the game based on the prompt."""
    logger.debug(f"Generating title for prompt: {prompt[:50]}...")

    try:
        # pylint: disable=line-too-long
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
                f"{lemonade_handle.url}/api/v1/chat/completions",
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


def extract_python_code(llm_response: str) -> Optional[ExtractedCode]:
    """Extract Python code block from LLM response."""
    logger.debug(f"Extracting Python code from response of length {len(llm_response)}")

    # Debug: Log the first 500 and last 500 characters of the response
    logger.debug(f"Response start: {repr(llm_response[:500])}")
    logger.debug(f"Response end: {repr(llm_response[-500:])}")

    # Look for code blocks with python/py language specifier
    patterns = [
        r"```python\s*\n(.*?)\n```",
        r"```py\s*\n(.*?)\n```",
        r"```\s*\n(.*?)\n```",  # Generic code block
    ]

    # Collect all valid pygame code blocks and choose the longest one
    valid_code_blocks = []

    for i, pattern in enumerate(patterns):
        logger.debug(f"Trying pattern {i+1}: {pattern}")
        matches = re.findall(pattern, llm_response, re.DOTALL)
        for match in matches:
            code = match.strip()
            pattern_num = i + 1
            logger.debug(
                f"Found code block with pattern {pattern_num}, length: {len(code)}"
            )
            # Debug: Log the first 200 characters of the extracted code
            logger.debug(f"Extracted code start: {repr(code[:200])}")

            # Basic validation - should contain pygame
            if "pygame" in code.lower():
                logger.debug("Code contains pygame, validation passed")
                valid_code_blocks.append(code)
            else:
                logger.warning("Code block found but doesn't contain pygame")
                # Debug: Log what we actually found instead of pygame
                logger.debug(f"Code content (first 300 chars): {repr(code[:300])}")

    # If we found valid pygame code blocks, return the longest one (most likely to be complete)
    if valid_code_blocks:
        longest_code = max(valid_code_blocks, key=len)
        logger.debug(f"Selected longest pygame code block, length: {len(longest_code)}")
        return ExtractedCode(code=longest_code, length=len(longest_code))

    logger.error("No valid Python code block found in response")

    # Debug: Let's also check if there are any code blocks at all
    all_code_blocks = re.findall(r"```.*?\n(.*?)\n```", llm_response, re.DOTALL)
    logger.debug(f"Total code blocks found: {len(all_code_blocks)}")
    for i, block in enumerate(all_code_blocks):
        logger.debug(
            f"Block {i+1} length: {len(block)}, starts with: {repr(block[:100])}"
        )

    return None


async def generate_game_code_with_llm(
    mode: str, content: str, message: str = None
) -> Union[str, ExtractedCode, None]:
    """Unified function to generate or fix game code using LLM.

    Args:
        mode: "create" for new games, "debug" for fixing existing games, "remix" for modifying existing games
        content: For "create" mode: user's game prompt. For "debug" mode: the buggy code. For "remix" mode: the original game code
        message: For "debug" mode: the error that occurred. For "remix" mode: the remix prompt

    Returns:
        Optional[str]: The generated/fixed code, or None if failed
    """

    if mode == "create":
        # pylint: disable=line-too-long
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

        user_prompt = f"Create a game: {content}"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    elif mode == "debug":
        # Extract error type from error message
        error_type = None
        if "UnboundLocalError" in message:
            error_type = "UnboundLocalError"
        elif "NameError" in message:
            error_type = "NameError"
        elif "AttributeError" in message:
            error_type = "AttributeError"
        elif "TypeError" in message:
            error_type = "TypeError"
        elif "IndexError" in message:
            error_type = "IndexError"

        # Build error-specific guidance
        error_guidance = ""
        if error_type == "UnboundLocalError":
            # pylint: disable=line-too-long
            error_guidance = """UnboundLocalError. To fix:
Add 'global variable_name' at the start of the function that's trying to modify a global variable."""
        elif error_type == "NameError":
            error_guidance = """NameError. To fix:
Either define the missing variable or fix the typo in the variable name."""
        elif error_type == "AttributeError":
            error_guidance = """AttributeError. To fix:
Use the correct method/attribute name or check the object type."""
        elif error_type == "TypeError":
            error_guidance = """TypeError. To fix:
Fix the function arguments or type mismatch."""
        elif error_type == "IndexError":
            error_guidance = """IndexError. To fix:
Check list/array bounds before accessing."""

        # pylint: disable=line-too-long
        system_prompt = """You are a Python expert debugging a pygame script that has an error.

Output format:
1. One sentence explaining the fix.
2. Incorporate the fix into a code snippet in the style of a before/after git diff.
    a. Show the fix and a couple surrounding lines of code.
    b. ONLY 5-10 lines of code.
3. Complete CORRECTED code in a python code block.

IMPORTANT:
- The final code you output must have the fix applied.
- Be CAREFUL not to get carried away repeating the old code.
"""

        user_prompt = f"""The code below has this error:
{message}

Here is some guidance on the error:

{error_guidance}

Look at the code below and give me a complete pygame script where the error is fixed:

```python
{content}
```
"""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    elif mode == "remix":
        # pylint: disable=line-too-long
        system_prompt = """You are an expert Python game developer. You will be given an existing pygame game and a modification request. Your task is to modify the existing game according to the user's request while keeping it fully functional.

Rules:
1. Use ONLY the pygame library - no external images, sounds, or files
2. Keep the core game mechanics intact unless specifically asked to change them
3. Make the requested modifications while ensuring the game remains playable
4. Maintain proper pygame event handling and game loop
5. Add comments explaining the changes you made
6. Make sure the game window closes properly when the user clicks the X button
7. Use reasonable colors and make the game visually appealing with pygame primitives

Generate ONLY the complete modified Python code in a single code block. Do not include any explanations outside the code block."""

        user_prompt = f"""Here is the existing game code:

```python
{content}
```

Please modify this game according to this request: {message}

Provide the complete modified game code."""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
    else:
        logger.error(f"Invalid mode: {mode}")
        yield None
        return  # Early return without value is allowed

    # Debug logging for OpenAI messages structure
    logger.debug(f"=== OpenAI Messages Debug for {mode} mode ===")
    logger.debug(f"Number of messages: {len(messages)}")
    for i, message in enumerate(messages):
        role = message["role"]
        content = message["content"]
        content_length = len(content)
        logger.debug(
            f"Message {i+1} - Role: {role}, Content length: {content_length} chars"
        )
        # Log first 200 chars and last 100 chars to see structure without overwhelming logs
        if content_length <= 300:
            logger.debug(f"Message {i+1} - Full content: {repr(content)}")
        else:
            logger.debug(f"Message {i+1} - Content start: {repr(content[:200])}")
            logger.debug(f"Message {i+1} - Content end: {repr(content[-100:])}")
    logger.debug("=== End OpenAI Messages Debug ===")

    try:
        # Create OpenAI client pointing to Lemonade Server
        openai_client = AsyncOpenAI(
            base_url=f"{lemonade_handle.url}/api/v1",
            api_key="dummy",
            timeout=600.0,
        )

        response = await openai_client.chat.completions.create(
            model=REQUIRED_MODEL,
            messages=messages,
            stream=True,  # Always stream for both create and debug modes
            max_tokens=4000,
        )

        # Handle streaming response for both create and debug modes
        full_response = ""
        async for chunk in response:
            if chunk.choices and len(chunk.choices) > 0:
                delta = chunk.choices[0].delta
                if delta.content is not None:
                    content_chunk = delta.content
                    full_response += content_chunk
                    # Yield the content chunk for streaming to LLM Output sidecar
                    yield content_chunk

        # After all chunks, extract and yield the final code
        extracted_code = extract_python_code(full_response)
        if extracted_code:
            logger.debug(f"Successfully extracted code for {mode} mode")
            yield extracted_code  # Yield the final extracted code
        else:
            logger.error(f"Could not extract code from LLM response in {mode} mode")
            yield None

    except Exception as e:
        logger.error(f"Error calling LLM for {mode}: {e}")
        yield None


def generate_game_id():
    """Generate a unique game ID."""
    return str(uuid.uuid4())[:8]


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
    online = await lemonade_handle.check_lemonade_server_api()
    return JSONResponse({"online": online})


@app.get("/api/games")
async def get_games():
    """Get all saved games."""
    arcade_games.cleanup_finished_games()
    return JSONResponse(arcade_games.game_metadata)


@app.get("/api/installation-status")
async def installation_status():
    """Check lemonade-server installation status ONLY."""
    logger.info("Installation status endpoint called")
    version_info = await lemonade_handle.check_lemonade_server_version()
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
    is_running = await lemonade_handle.check_lemonade_server_running()
    logger.info(f"Initial running check result: {is_running}")

    # If server is not running, try to start it automatically
    if not is_running:
        logger.info("Server not running, attempting to start automatically...")
        start_result = await lemonade_handle.start_lemonade_server()
        logger.info(f"Auto-start result: {start_result}")

        if start_result["success"]:
            # Give it a moment to start up
            import asyncio

            logger.info("Waiting 2 seconds for server to initialize...")
            await asyncio.sleep(2)

            # Check again
            is_running = await lemonade_handle.check_lemonade_server_running()
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
    api_online = await lemonade_handle.check_lemonade_server_api()
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
    model_status = await lemonade_handle.check_model_installed(REQUIRED_MODEL)
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
    model_loaded_status = await lemonade_handle.check_model_loaded(REQUIRED_MODEL)
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

    is_pyinstaller = lemonade_handle.is_pyinstaller_environment()
    sdk_available = (
        await lemonade_handle.check_lemonade_sdk_available()
        if not is_pyinstaller
        else False
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
        lemonade_handle.refresh_environment()
        # Also reset server state so it will re-discover commands
        lemonade_handle.reset_server_state()
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
    result = await lemonade_handle.download_and_install_lemonade_server()
    logger.info(f"Install result: {result}")
    return JSONResponse(result)


@app.post("/api/start-server")
async def start_server():
    """Start lemonade-server if installed."""
    logger.info("Start server endpoint called")
    result = await lemonade_handle.start_lemonade_server()
    logger.info(f"Start server result: {result}")
    return JSONResponse(result)


@app.post("/api/install-model")
async def install_model():
    """Install the required model."""
    logger.info("Install model endpoint called")
    result = await lemonade_handle.install_model(REQUIRED_MODEL)
    logger.info(f"Install model result: {result}")
    return JSONResponse(result)


@app.post("/api/load-model")
async def load_model():
    """Load the required model."""
    logger.info("Load model endpoint called")
    result = await lemonade_handle.load_model(REQUIRED_MODEL)
    logger.info(f"Load model result: {result}")
    return JSONResponse(result)


def generate_next_version_title(original_title: str) -> str:
    """Generate the next version number for a remixed game title."""
    # Check if the title already has a version number
    import re

    version_match = re.search(r" v(\d+)$", original_title)

    if version_match:
        # Extract current version number and increment
        current_version = int(version_match.group(1))
        next_version = current_version + 1
        # Replace the version number
        base_title = original_title[: version_match.start()]
        return f"{base_title} v{next_version}"
    else:
        # No version number, add v2
        return f"{original_title} v2"


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

            # Use the centralized function to generate game code
            yield f"data: {json.dumps({'type': 'status', 'message': 'Generating code...'})}\n\n"

            python_code = None
            async for result in generate_game_code_with_llm("create", prompt):
                if result is None:
                    # Error occurred in the LLM function
                    logger.error("Error in generate_game_code_with_llm")
                    error_data = {"type": "error", "message": "Failed to generate code"}
                    yield f"data: {json.dumps(error_data)}\n\n"
                    return
                elif isinstance(result, ExtractedCode):
                    # This is the final extracted code from extract_python_code
                    python_code = result.code
                    logger.debug(f"Received final code, length: {len(python_code)}")
                    break
                elif isinstance(result, str):
                    # This is a content chunk, stream it to the client
                    content_data = {"type": "content", "content": result}
                    yield f"data: {json.dumps(content_data)}\n\n"

            # Verify we got the code
            if not python_code:
                logger.error(
                    "Could not get Python code from generate_game_code_with_llm"
                )
                error_msg = "Could not extract valid Python code from response"
                error_data = {"type": "error", "message": error_msg}
                yield f"data: {json.dumps(error_data)}\n\n"
                return

            yield f"data: {json.dumps({'type': 'status', 'message': 'Extracting code...'})}\n\n"
            logger.debug("Code extraction completed")

            logger.debug(
                f"Successfully extracted Python code, length: {len(python_code)}"
            )

            # Create and launch the game using ArcadeGames
            # We'll use async generator delegation to stream from create_and_launch_game
            async for stream_item in arcade_games.create_and_launch_game_with_streaming(
                game_id, python_code, prompt
            ):
                yield stream_item

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


@app.post("/api/remix-game")
async def remix_game_endpoint(request: Request):
    """Remix an existing game using LLM."""
    logger.debug("Starting game remix endpoint")

    data = await request.json()
    game_id = data.get("game_id", "")
    remix_prompt = data.get("remix_prompt", "")

    logger.debug(
        f"Received remix request - game_id: '{game_id}', remix_prompt: '{remix_prompt[:50]}...'"
    )

    if not game_id or not remix_prompt:
        logger.error("Game ID and remix prompt are required")
        raise HTTPException(
            status_code=400, detail="Game ID and remix prompt are required"
        )

    # Check if the game exists
    if game_id not in arcade_games.game_metadata:
        logger.error(f"Game not found: {game_id}")
        raise HTTPException(status_code=404, detail="Game not found")

    # Prevent remixing built-in games
    if game_id in arcade_games.BUILTIN_GAMES:
        logger.error(f"Cannot remix built-in game: {game_id}")
        raise HTTPException(status_code=403, detail="Cannot remix built-in games")

    # Generate a unique game ID for the remixed version
    new_game_id = generate_game_id()
    logger.debug(f"Generated new game ID for remix: {new_game_id}")

    async def generate():
        try:
            logger.debug("Starting remix generate() function")
            # Send status update
            yield f"data: {json.dumps({'type': 'status', 'message': 'Connecting to LLM...'})}\n\n"
            logger.debug("Sent 'Connecting to LLM...' status")

            # Read the original game code
            original_game_file = arcade_games.games_dir / f"{game_id}.py"
            if not original_game_file.exists():
                logger.error(f"Original game file not found: {original_game_file}")
                error_data = {
                    "type": "error",
                    "message": "Original game file not found",
                }
                yield f"data: {json.dumps(error_data)}\n\n"
                return

            with open(original_game_file, "r", encoding="utf-8") as f:
                original_code = f.read()

            logger.debug(f"Read original game code, length: {len(original_code)}")

            # Use the centralized function to remix the game code
            yield f"data: {json.dumps({'type': 'status', 'message': 'Remixing code...'})}\n\n"

            remixed_code = None
            async for result in generate_game_code_with_llm(
                "remix", original_code, remix_prompt
            ):
                if result is None:
                    # Error occurred in the LLM function
                    logger.error("Error in generate_game_code_with_llm during remix")
                    error_data = {"type": "error", "message": "Failed to remix code"}
                    yield f"data: {json.dumps(error_data)}\n\n"
                    return
                elif isinstance(result, ExtractedCode):
                    # This is the final extracted code from extract_python_code
                    remixed_code = result.code
                    logger.debug(f"Received remixed code, length: {len(remixed_code)}")
                    break
                elif isinstance(result, str):
                    # This is a content chunk, stream it to the client
                    content_data = {"type": "content", "content": result}
                    yield f"data: {json.dumps(content_data)}\n\n"

            # Verify we got the remixed code
            if not remixed_code:
                logger.error(
                    "Could not get remixed Python code from generate_game_code_with_llm"
                )
                error_msg = "Could not extract valid Python code from remix response"
                error_data = {"type": "error", "message": error_msg}
                yield f"data: {json.dumps(error_data)}\n\n"
                return

            yield f"data: {json.dumps({'type': 'status', 'message': 'Extracting remixed code...'})}\n\n"
            logger.debug("Remix code extraction completed")

            logger.debug(
                f"Successfully extracted remixed Python code, length: {len(remixed_code)}"
            )

            # Generate new title with version number
            original_title = arcade_games.game_metadata[game_id].get(
                "title", "Untitled Game"
            )
            new_title = generate_next_version_title(original_title)

            # Create the remix prompt for metadata
            original_prompt = arcade_games.game_metadata[game_id].get("prompt", "")
            full_remix_prompt = f"Remix of '{original_title}': {remix_prompt}"

            # Create and launch the remixed game using ArcadeGames
            async for stream_item in arcade_games.create_and_launch_game_with_streaming(
                new_game_id, remixed_code, full_remix_prompt, new_title, is_remix=True
            ):
                yield stream_item

        except Exception as e:
            logger.exception(f"Error in game remix: {e}")
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
    """Launch a specific game with streaming support for error fixes."""
    arcade_games.cleanup_finished_games()

    if arcade_games.running_games:
        raise HTTPException(status_code=400, detail="Another game is already running")

    if game_id not in arcade_games.game_metadata:
        raise HTTPException(status_code=404, detail="Game not found")

    # Get game title for better messaging
    game_title = arcade_games.game_metadata.get(game_id, {}).get("title", game_id)

    async def generate():
        try:
            # Stream the launch process with potential error fixing
            async for stream_item in arcade_games.launch_game_with_streaming(
                game_id, game_title, max_retries=1
            ):
                yield stream_item

        except Exception as e:
            logger.exception(f"Error in game launch: {e}")
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


@app.get("/api/game-status/{game_id}")
async def game_status(game_id: str):
    """Check if a game is currently running."""
    arcade_games.cleanup_finished_games()
    running = game_id in arcade_games.running_games
    return JSONResponse({"running": running})


@app.delete("/api/delete-game/{game_id}")
async def delete_game_endpoint(game_id: str):
    """Delete a game."""
    if game_id not in arcade_games.game_metadata:
        raise HTTPException(status_code=404, detail="Game not found")

    # Prevent deletion of built-in games
    if game_id in arcade_games.BUILTIN_GAMES:
        raise HTTPException(status_code=403, detail="Cannot delete built-in games")

    # Stop the game if it's running
    if game_id in arcade_games.running_games:
        arcade_games.stop_game(game_id)

    # Delete the file
    game_file = arcade_games.games_dir / f"{game_id}.py"
    if game_file.exists():
        game_file.unlink()

    # Remove from metadata
    del arcade_games.game_metadata[game_id]
    arcade_games.save_metadata()

    return JSONResponse({"success": True})


@app.get("/api/game-metadata/{game_id}")
async def get_game_metadata(game_id: str):
    """Get metadata for a specific game."""
    if game_id not in arcade_games.game_metadata:
        raise HTTPException(status_code=404, detail="Game not found")

    metadata = arcade_games.game_metadata[game_id].copy()

    # For built-in games, hide sensitive information
    if game_id in arcade_games.BUILTIN_GAMES:
        # Remove prompt and other sensitive data for built-in games
        metadata.pop("prompt", None)
        metadata["builtin"] = True

    return JSONResponse(metadata)


@app.post("/api/open-game-file/{game_id}")
async def open_game_file(game_id: str):
    """Open the Python file for a game in the default editor."""
    if game_id not in arcade_games.game_metadata:
        raise HTTPException(status_code=404, detail="Game not found")

    # Prevent opening built-in game files
    if game_id in arcade_games.BUILTIN_GAMES:
        raise HTTPException(
            status_code=403, detail="Cannot view source code of built-in games"
        )

    game_file = arcade_games.games_dir / f"{game_id}.py"
    if not game_file.exists():
        raise HTTPException(status_code=404, detail="Game file not found")

    try:
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
        raise HTTPException(
            status_code=500, detail=f"Failed to open file: {str(e)}"
        ) from e


def run_game_file(game_file_path):
    """Run a game file directly - used when executable is called with a game file."""
    try:
        print(f"Lemonade Arcade - Running game: {game_file_path}")

        # Import pygame here, right before we need it
        # pylint: disable=global-statement
        global pygame
        if pygame is None:
            try:
                # pylint: disable=redefined-outer-name
                import pygame

                print(f"Pygame {pygame.version.ver} loaded successfully")
            except ImportError as e:
                print(f"Error: Failed to import pygame: {e}")
                sys.exit(1)

        # Read and execute the game file
        with open(game_file_path, "r", encoding="utf-8") as f:
            game_code = f.read()

        # Execute the game code - pygame should now be available
        # pylint: disable=exec-used
        exec(game_code, {"__name__": "__main__", "__file__": game_file_path})

    except Exception as e:
        print(f"Error running game {game_file_path}: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


def main():
    """Main entry point for the application."""
    # Configure logging if not already configured (when run directly, not via CLI)
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )
        # Suppress noisy httpcore debug messages
        logging.getLogger("httpcore").setLevel(logging.WARNING)
        logging.getLogger("httpx").setLevel(logging.WARNING)

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
        for game_id in list(arcade_games.running_games.keys()):
            arcade_games.stop_game(game_id)


if __name__ == "__main__":
    main()

# Copyright (c) 2025 AMD
