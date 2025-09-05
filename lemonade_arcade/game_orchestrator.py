import json
import logging
import time
from pathlib import Path
from typing import AsyncGenerator

from lemonade_arcade.arcade_games import ArcadeGames
from lemonade_arcade.game_launcher import GameLauncher
from lemonade_arcade.llm_service import LLMService, ExtractedCode


logger = logging.getLogger("lemonade_arcade.main")


class GameOrchestrator:
    """Coordinates storage, launching, and LLM to implement arcade workflows."""

    def __init__(
        self, storage: ArcadeGames, launcher: GameLauncher, llm_service: LLMService
    ) -> None:
        self.storage = storage
        self.launcher = launcher
        self.llm = llm_service

    def _get_game_file_path(self, game_id: str) -> Path:
        if game_id in self.storage.builtin_games:
            from lemonade_arcade.utils import get_resource_path

            builtin_games_dir = Path(get_resource_path("builtin_games"))
            return builtin_games_dir / self.storage.builtin_games[game_id]["file"]
        return self.storage.games_dir / f"{game_id}.py"

    async def create_and_launch_game_with_streaming(
        self, game_id: str, prompt: str
    ) -> AsyncGenerator[str, None]:
        # Status: connecting
        yield f"data: {json.dumps({'type': 'status', 'message': 'Connecting to LLM...'})}\n\n"
        # Status: generating
        yield f"data: {json.dumps({'type': 'status', 'message': 'Generating code...'})}\n\n"

        python_code: str | None = None
        async for result in self.llm.stream_game_code("create", prompt):
            if result is None:
                yield f"data: {json.dumps({'type': 'error', 'message': 'Failed to generate code'})}\n\n"
                return
            elif isinstance(result, ExtractedCode):
                python_code = result.code
                break
            elif isinstance(result, str):
                yield f"data: {json.dumps({'type': 'content', 'content': result})}\n\n"

        if not python_code:
            error_msg = "Could not extract valid Python code from response"
            yield f"data: {json.dumps({'type': 'error', 'message': error_msg})}\n\n"
            return

        yield f"data: {json.dumps({'type': 'status', 'message': 'Extracting code...'})}\n\n"

        # Generate title
        game_title = await self.llm.generate_title(prompt)

        # Save game file and metadata
        game_file = self.storage.games_dir / f"{game_id}.py"
        game_file.write_text(python_code, encoding="utf-8")
        self.storage.game_metadata[game_id] = {
            "title": game_title,
            "created": time.time(),
            "prompt": prompt,
        }
        self.storage.save_metadata()

        # Launch
        launch_message = "Launching game..."
        yield f"data: {json.dumps({'type': 'status', 'message': launch_message})}\n\n"
        async for item in self.launch_game_with_auto_fix_streaming(game_id, game_title):
            yield item

    async def remix_and_launch_game_with_streaming(
        self, original_game_id: str, new_game_id: str, remix_prompt: str, new_title: str
    ) -> AsyncGenerator[str, None]:
        # Read original code
        original_file = self._get_game_file_path(original_game_id)
        if not original_file.exists():
            yield f"data: {json.dumps({'type': 'error', 'message': 'Original game file not found'})}\n\n"
            return
        original_code = original_file.read_text(encoding="utf-8")

        # Status
        yield f"data: {json.dumps({'type': 'status', 'message': 'Remixing code...'})}\n\n"

        remixed_code: str | None = None
        async for result in self.llm.stream_game_code(
            "remix", original_code, remix_prompt
        ):
            if result is None:
                yield f"data: {json.dumps({'type': 'error', 'message': 'Failed to remix code'})}\n\n"
                return
            elif isinstance(result, ExtractedCode):
                remixed_code = result.code
                break
            elif isinstance(result, str):
                yield f"data: {json.dumps({'type': 'content', 'content': result})}\n\n"

        if not remixed_code:
            error_msg = "Could not extract valid Python code from remix response"
            yield f"data: {json.dumps({'type': 'error', 'message': error_msg})}\n\n"
            return

        yield f"data: {json.dumps({'type': 'status', 'message': 'Extracting remixed code...'})}\n\n"

        # Save new game
        game_file = self.storage.games_dir / f"{new_game_id}.py"
        game_file.write_text(remixed_code, encoding="utf-8")
        self.storage.game_metadata[new_game_id] = {
            "title": new_title,
            "created": time.time(),
            "prompt": f"Remix of '{self.storage.game_metadata.get(original_game_id, {}).get('title', 'Untitled Game')}': {remix_prompt}",
        }
        self.storage.save_metadata()

        # Launch
        launch_message = "Launching remixed game..."
        yield f"data: {json.dumps({'type': 'status', 'message': launch_message})}\n\n"
        async for item in self.launch_game_with_auto_fix_streaming(
            new_game_id, new_title
        ):
            yield item

    async def launch_game_with_auto_fix_streaming(
        self, game_id: str, game_title: str, max_retries: int = 1
    ) -> AsyncGenerator[str, None]:
        retry_count = 0
        while retry_count <= max_retries:
            game_file = self._get_game_file_path(game_id)
            if not game_file.exists():
                error_msg = f"Game file not found: {game_file}"
                yield f"data: {json.dumps({'type': 'error', 'message': error_msg})}\n\n"
                return

            success, error_message = self.launcher.launch_game_process(
                game_file, game_id
            )
            if success:
                message = f"Game '{game_title}' created and launched successfully!"
                complete_data = {
                    "type": "complete",
                    "game_id": game_id,
                    "message": message,
                }
                yield f"data: {json.dumps(complete_data)}\n\n"
                return

            # Retry with LLM fix
            if (
                retry_count < max_retries
                and game_id not in self.storage.builtin_games
                and game_id in self.storage.game_metadata
            ):
                status_msg = "Game hit an error, trying to fix it..."
                yield f"data: {json.dumps({'type': 'status', 'message': status_msg})}\n\n"

                error_separator = (
                    f"\n\n---\n\n# ⚠️ ERROR ENCOUNTERED\n\n"
                    f"> 🔧 **The generated game encountered an error during launch.**  \n"
                    f"> **Attempting to automatically fix the code...**\n\n"
                    f"**Error Details:**\n```\n{error_message}\n```\n\n---\n\n"
                    f"## 🛠️ Fix Attempt:\n\n"
                )
                yield f"data: {json.dumps({'type': 'content', 'content': error_separator})}\n\n"

                try:
                    current_code = game_file.read_text(encoding="utf-8")
                    fixed_code: str | None = None
                    async for result in self.llm.stream_game_code(
                        "debug", current_code, error_message
                    ):
                        if result is None:
                            break
                        elif isinstance(result, ExtractedCode):
                            fixed_code = result.code
                            break
                        elif isinstance(result, str):
                            yield f"data: {json.dumps({'type': 'content', 'content': result})}\n\n"

                    if fixed_code:
                        game_file.write_text(fixed_code, encoding="utf-8")
                        retry_count += 1
                        continue
                    else:
                        error_msg = f"Game '{game_title}' failed to launch and could not be automatically fixed: {error_message}"
                        final_error_content = f"\n\n---\n\n> ❌ **FINAL ERROR**  \n> {error_msg}\n\n---\n\n"
                        yield f"data: {json.dumps({'type': 'content', 'content': final_error_content})}\n\n"
                        yield f"data: {json.dumps({'type': 'error', 'message': 'Game launch failed after fix attempt'})}\n\n"
                        return
                except Exception as e:
                    error_msg = f"Error during automatic fix: {str(e)}"
                    exception_error_content = f"\n\n---\n\n> ❌ **FIX ATTEMPT FAILED**  \n> {error_msg}\n\n---\n\n"
                    yield f"data: {json.dumps({'type': 'content', 'content': exception_error_content})}\n\n"
                    yield f"data: {json.dumps({'type': 'error', 'message': 'Game launch failed during fix attempt'})}\n\n"
                    return
            else:
                error_msg = f"Game '{game_title}' failed to launch: {error_message}"
                no_retry_error_content = (
                    f"\n\n---\n\n> ❌ **LAUNCH FAILED**  \n> {error_msg}\n\n---\n\n"
                )
                yield f"data: {json.dumps({'type': 'content', 'content': no_retry_error_content})}\n\n"
                yield f"data: {json.dumps({'type': 'error', 'message': 'Game launch failed'})}\n\n"
                return

        # Max retries exceeded
        error_msg = f"Game '{game_title}' failed to launch after {max_retries} automatic fix attempts: {error_message}"
        max_retry_error_content = (
            f"\n\n---\n\n> ❌ **MAX RETRIES EXCEEDED**  \n> {error_msg}\n\n---\n\n"
        )
        yield f"data: {json.dumps({'type': 'content', 'content': max_retry_error_content})}\n\n"
        yield f"data: {json.dumps({'type': 'error', 'message': 'Game launch failed after max retries'})}\n\n"
