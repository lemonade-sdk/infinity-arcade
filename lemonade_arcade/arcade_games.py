import logging
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict


from lemonade_arcade.utils import get_resource_path
from lemonade_arcade.llm import ExtractedCode, generate_game_code_with_llm
from lemonade_arcade.lemonade_client import LemonadeClient

logger = logging.getLogger("lemonade_arcade.main")


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
        self.builtin_games = {
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
        for game_id, game_data in self.builtin_games.items():
            if game_id not in self.game_metadata:
                self.game_metadata[game_id] = game_data.copy()

    def save_metadata(self):
        """Save game metadata to disk."""
        try:
            with open(self.metadata_file, "w", encoding="utf-8") as f:
                json.dump(self.game_metadata, f, indent=2)
        except Exception as e:
            print(f"Error saving metadata: {e}")

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
        lemonade_handle: LemonadeClient,
        model: str,
        game_id: str,
        python_code: str,
        prompt: str,
        game_title: str = None,
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
                # pylint: disable=line-too-long
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
                lemonade_handle, model, game_id, game_title
            ):
                yield stream_item

        except Exception as e:
            error_type = "remixed game creation" if is_remix else "game creation"
            logger.exception(f"Error in {error_type}: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    async def launch_game_with_streaming(
        self,
        lemonade_handle: LemonadeClient,
        model: str,
        game_id: str,
        game_title: str = None,
        max_retries: int = 1,
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
            if game_id in self.builtin_games:
                # For built-in games, use the file from the builtin_games directory
                builtin_games_dir = get_resource_path("builtin_games")
                game_file = (
                    Path(builtin_games_dir) / self.builtin_games[game_id]["file"]
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
                and game_id not in self.builtin_games
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
                        lemonade_handle, model, "debug", current_code, error_message
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
