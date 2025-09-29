import logging
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, Tuple


logger = logging.getLogger("infinity_arcade.main")


class GameLauncher:
    """Handles game process execution and lifecycle management."""

    def __init__(self) -> None:
        self.running_games: Dict[str, subprocess.Popen] = {}

    def launch_game_process(self, game_file: Path, game_id: str) -> Tuple[bool, str]:
        """Launch a game process and return (success, error_message).

        This mirrors the previous behavior used in ArcadeGames: if the process
        exits within ~2 seconds, treat that as a failure for pygame-based games
        and capture stderr to present a useful error message.
        """
        try:
            if getattr(sys, "frozen", False):
                cmd = [sys.executable, str(game_file)]
                logger.debug(f"PyInstaller mode - Launching: {' '.join(cmd)}")
            else:
                cmd = [sys.executable, str(game_file)]
                logger.debug(f"Development mode - Launching: {' '.join(cmd)}")

            # pylint: disable=consider-using-with
            process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )

            start_time = time.time()
            logger.debug(f"Game {game_id} subprocess started with PID {process.pid}")

            try:
                stdout, stderr = process.communicate(timeout=2)
                end_time = time.time()
                duration = end_time - start_time
                logger.debug(
                    f"Game {game_id} subprocess (PID {process.pid}) EXITED after {duration:.3f} "
                    f"seconds with return code {process.returncode}"
                )

                # Filter out noisy warnings from stderr to get actual errors
                stderr_lines = stderr.strip().split("\n") if stderr else []
                actual_errors = []
                for line in stderr_lines:
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
                    if line.strip() and any(
                        indicator in line
                        for indicator in [
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

                if process.returncode != 0:
                    error_msg = (
                        filtered_stderr
                        if filtered_stderr
                        else f"Game exited with code {process.returncode} but no error message was captured"
                    )
                    logger.error(
                        f"Game {game_id} failed with return code {process.returncode}: {error_msg}"
                    )
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

                # Success path for quick-and-clean exit (no time-based failure)
                logger.debug(
                    f"Game {game_id} exited quickly with return code 0; treating as successful completion"
                )
                if stdout:
                    print("STDOUT:")
                    print(stdout)
                if stderr:
                    print("STDERR:")
                    print(stderr)
                if not stdout and not stderr:
                    print("No output captured")
                print("=" * 60)
                return True, "Game exited successfully"
            except subprocess.TimeoutExpired:
                # Timeout is good - means the game is still running
                end_time = time.time()
                duration = end_time - start_time
                self.running_games[game_id] = process
                logger.debug(
                    f"Game {game_id} subprocess (PID {process.pid}) STILL RUNNING after {duration:.3f} seconds timeout"
                )
                return True, "Game launched successfully"
        except Exception as e:
            logger.error(f"Error launching game {game_id}: {e}")
            return False, str(e)

    def stop_game(self, game_id: str) -> None:
        if game_id in self.running_games:
            try:
                process = self.running_games[game_id]
                logger.debug(
                    f"MANUALLY STOPPING game {game_id} subprocess (PID {process.pid})"
                )
                process.terminate()
                try:
                    process.wait(timeout=5)
                    logger.debug(
                        f"Game {game_id} subprocess (PID {process.pid}) terminated gracefully"
                    )
                except subprocess.TimeoutExpired:
                    logger.debug(
                        f"Game {game_id} subprocess (PID {process.pid}) did not terminate gracefully, killing..."
                    )
                    process.kill()
                    logger.debug(
                        f"Game {game_id} subprocess (PID {process.pid}) killed"
                    )
            except Exception as e:
                print(f"Error stopping game {game_id}: {e}")
            finally:
                del self.running_games[game_id]

    def cleanup_finished_games(self) -> None:
        finished: list[str] = []
        for game_id, process in self.running_games.items():
            if process.poll() is not None:
                return_code = process.returncode
                logger.debug(
                    f"Game {game_id} subprocess (PID {process.pid}) FINISHED with return code {return_code} - cleaning up"
                )
                finished.append(game_id)
        for game_id in finished:
            del self.running_games[game_id]
