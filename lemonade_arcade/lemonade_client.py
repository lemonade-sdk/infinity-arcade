import logging
import os
import subprocess
import sys
import tempfile
import time
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional
import httpx


# Model information: (model_name, size_gb)
MODELS = {
    "high_end": ("Qwen3-Coder-30B-A3B-Instruct-GGUF", 18.6),
    "npu": ("Qwen-2.5-7B-Instruct-Hybrid", 8.4),
    "default": ("Qwen3-4B-Instruct-2507-GGUF", 2.5),
}

logger = logging.getLogger("lemonade_arcade.main")


class LemonadeClient:
    """
    Detect, install, and set up Lemonade Client.
    This class makes it easier to start a new Python project with Lemonade
    by automating many common tasks.
    """

    def __init__(self, minimum_version: str = "8.1.0"):
        # Track which command is used for this server instance
        self.server_command = None
        # Track the server process to avoid starting multiple instances
        self.server_process = None
        # Store the minimum required version
        self.minimum_version = minimum_version

        self.url = "http://localhost:8000"

    def is_pyinstaller_environment(self):
        """
        Check if the application is running in a PyInstaller bundle environment.

        Use this when your app needs to determine installation method preferences
        or adjust behavior based on deployment type. PyInstaller environments
        typically prefer installer-based server installation over pip.

        Returns:
            bool: True if running in PyInstaller bundle, False otherwise
        """
        return getattr(sys, "frozen", False)

    def find_lemonade_server_paths(self):
        """
        Find lemonade-server installation paths by scanning the system PATH.

        Use this to discover where lemonade-server binaries are installed on the system.
        Helpful for apps that need to verify installation locations or debug path issues.

        Returns:
            List[str]: List of directory paths containing lemonade-server installations
        """
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

    def reset_server_state(self):
        """
        Reset cached server state after installation changes or configuration updates.

        Call this when you've installed/updated lemonade-server or changed system configuration
        to ensure the client rediscovers server commands and processes. Essential after
        installation operations to avoid using stale cached paths.
        """

        logger.info("Resetting server state")
        self.server_command = None
        if self.server_process and self.server_process.poll() is None:
            try:
                self.server_process.terminate()
            except Exception:
                pass
        self.server_process = None

    def refresh_environment(self):
        """
        Refresh environment variables from the system registry (Windows only).

        Use this after installing lemonade-server to pick up newly added PATH entries
        without requiring an application restart. Essential for apps that install
        lemonade-server programmatically and need immediate access to the commands.
        """
        try:
            if sys.platform == "win32":
                # pylint: disable=import-error
                # This will raise an import exception on linux right now
                import winreg

                logger.info("Refreshing environment variables...")

                # Get system PATH
                with winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE,
                    r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment",
                ) as key:
                    system_path = winreg.QueryValueEx(key, "PATH")[0]

                # Get user PATH
                try:
                    with winreg.OpenKey(
                        winreg.HKEY_CURRENT_USER, r"Environment"
                    ) as key:
                        user_path = winreg.QueryValueEx(key, "PATH")[0]
                except FileNotFoundError:
                    user_path = ""

                # Combine and update current process environment
                new_path = system_path
                if user_path:
                    new_path = user_path + ";" + system_path

                # Also add common Python Scripts directories that pip might use
                python_scripts_paths = self._discover_python_scripts_paths()

                # Add these paths to the PATH if they're not already there
                for scripts_path in python_scripts_paths:
                    if scripts_path.lower() not in new_path.lower():
                        new_path = scripts_path + ";" + new_path
                        logger.info(f"Added {scripts_path} to PATH")

                os.environ["PATH"] = new_path
                logger.info(f"Updated PATH: {new_path[:200]}...")  # Log first 200 chars
            else:
                logger.info(
                    "Non-Windows platform, skipping registry-based PATH refresh"
                )

        except Exception as e:
            logger.warning(f"Failed to refresh environment: {e}")

    def _discover_python_scripts_paths(self):
        """Discover Python Scripts directories where pip installs console scripts."""
        python_scripts_paths = []

        # Add Python Scripts directory (where pip installs console scripts)
        python_base = os.path.dirname(sys.executable)
        scripts_dir = os.path.join(python_base, "Scripts")
        if os.path.exists(scripts_dir):
            python_scripts_paths.append(scripts_dir)
            logger.info(f"Found Python Scripts directory: {scripts_dir}")

        # Add user site-packages Scripts directory
        try:
            import site

            user_site = site.getusersitepackages()
            if user_site:
                user_scripts = os.path.join(os.path.dirname(user_site), "Scripts")
                if os.path.exists(user_scripts):
                    python_scripts_paths.append(user_scripts)
                    logger.info(f"Found user Scripts directory: {user_scripts}")
        except Exception:
            pass

        return python_scripts_paths

    async def execute_lemonade_server_command(
        self,
        args: List[str],
        timeout: int = 10,
        use_popen: bool = False,
        stdout_file=None,
        stderr_file=None,
    ):
        """
        Execute lemonade-server commands using the best available method for the system.

        Use this as the primary interface for running any lemonade-server command. The method
        automatically tries different installation methods (pip, installer, dev) and caches
        the successful command for future use. Essential for cross-platform compatibility.

        Args:
            args: Command arguments to pass to lemonade-server (e.g., ["--version"], ["serve"])
            timeout: Maximum seconds to wait for command completion
                (ignored for background processes)
            use_popen: True for background processes that shouldn't block,
                False for commands with output
            stdout_file: File handle to redirect standard output (only with use_popen=True)
            stderr_file: File handle to redirect error output (only with use_popen=True)

        Returns:
            subprocess.CompletedProcess for regular commands, subprocess.Popen for
            background processes, or None if all command attempts failed
        """
        logger.info(f"Executing lemonade-server command with args: {args}")

        # If we already know which command to use, use only that one
        if self.server_command:
            commands_to_try = [self.server_command + args]
        else:
            # Try different ways to find lemonade-server based on platform
            commands_to_try = []

            if sys.platform == "win32":
                # Windows: Try traditional commands first, then Python module fallback
                if not self.is_pyinstaller_environment():
                    commands_to_try.append(["lemonade-server-dev"] + args)

                # Windows traditional commands
                commands_to_try.extend(
                    [
                        ["lemonade-server"] + args,
                        ["lemonade-server.bat"] + args,
                    ]
                )

                # Add dynamically discovered Windows paths
                for bin_path in self.find_lemonade_server_paths():
                    commands_to_try.extend(
                        [
                            [os.path.join(bin_path, "lemonade-server.exe")] + args,
                            [os.path.join(bin_path, "lemonade-server.bat")] + args,
                        ]
                    )

                # Python module fallback (most reliable after pip install)
                commands_to_try.append([sys.executable, "-m", "lemonade_server"] + args)
            else:
                # Linux/Unix: Try lemonade-server-dev first, then Python module fallback
                commands_to_try.append(["lemonade-server-dev"] + args)
                commands_to_try.append([sys.executable, "-m", "lemonade_server"] + args)

        for i, cmd in enumerate(commands_to_try):
            try:
                logger.info(f"Trying command {i+1}: {cmd}")

                # Determine if we should use shell=True based on command type
                use_shell = not (len(cmd) >= 3 and cmd[1] == "-m")
                final_cmd = " ".join(cmd) if use_shell else cmd

                if use_popen:
                    # For background processes (like server start)
                    process = subprocess.Popen(
                        final_cmd,
                        stdout=stdout_file or subprocess.PIPE,
                        stderr=stderr_file or subprocess.PIPE,
                        creationflags=(
                            subprocess.CREATE_NO_WINDOW
                            if sys.platform == "win32"
                            else 0
                        ),
                        shell=use_shell,
                        env=os.environ.copy(),
                    )

                    # Store the successful command for future use
                    if not self.server_command:
                        self.server_command = cmd[: -len(args)]
                        logger.info(f"Stored server command: {self.server_command}")

                    return process
                else:
                    # For regular commands with output
                    result = subprocess.run(
                        final_cmd,
                        capture_output=True,
                        text=True,
                        timeout=timeout,
                        shell=use_shell,
                        env=os.environ.copy(),
                        check=False,  # Don't raise exception on non-zero exit
                    )

                    logger.debug(f"Command {i+1} returned code: {result.returncode}")
                    logger.debug(f"Command {i+1} stdout: '{result.stdout}'")
                    logger.debug(f"Command {i+1} stderr: '{result.stderr}'")

                    if result.returncode == 0:
                        # Store the successful command for future use
                        if not self.server_command:
                            self.server_command = cmd[: -len(args)]
                            logger.info(f"Stored server command: {self.server_command}")

                        return result
                    else:
                        logger.debug(
                            f"Command {i+1} failed with return code {result.returncode}"
                        )
                        if result.stderr:
                            logger.debug(f"stderr: {result.stderr}")
                        # Try next command
                        continue

            except FileNotFoundError as e:
                logger.debug(f"Command {i+1} not found: {e}")
                continue
            except subprocess.TimeoutExpired as e:
                logger.debug(f"Command {i+1} timed out: {e}")
                continue
            except Exception as e:
                logger.error(f"Unexpected error with command {i+1}: {e}")
                continue

        # If we get here, all commands failed
        logger.error("All lemonade-server commands failed")
        return None

    async def check_lemonade_sdk_available(self):
        """
        Check if the lemonade-sdk Python package is installed and importable.

        Use this to determine if pip-based installation is available before attempting
        SDK-based operations. Helpful for showing installation options to users or
        choosing between different installation methods.

        Returns:
            bool: True if lemonade-sdk package can be imported, False otherwise
        """
        logger.info("Checking for lemonade-sdk package...")
        try:
            # Handle Windows vs Unix path quoting differently
            cmd = [sys.executable, "-c", "import lemonade_server; print('available')"]

            if sys.platform == "win32":
                # On Windows, quote paths with spaces using double quotes
                quoted_args = []
                for arg in cmd:
                    if " " in arg:
                        quoted_args.append(f'"{arg}"')
                    else:
                        quoted_args.append(arg)
                cmd_str = " ".join(quoted_args)
            else:
                # On Unix systems, use shlex.quote
                import shlex

                cmd_str = " ".join(shlex.quote(arg) for arg in cmd)

            logger.debug(f"Executing command: {cmd_str}")
            result = subprocess.run(
                cmd_str,
                capture_output=True,
                text=True,
                timeout=10,
                shell=True,  # Keep shell=True for environment handling
                check=False,  # Don't raise exception on non-zero exit
            )

            logger.debug(
                f"Command result: returncode={result.returncode}, "
                f"stdout='{result.stdout.strip()}', stderr='{result.stderr.strip()}'"
            )
            is_available = result.returncode == 0 and "available" in result.stdout
            logger.info(f"lemonade-sdk package available: {is_available}")
            return is_available
        except Exception as e:
            logger.info(f"lemonade-sdk package check failed: {e}")
            return False

    async def check_lemonade_server_version(self):
        """
        Check lemonade-server installation status and version compatibility.

        Use this to verify that lemonade-server is installed and meets minimum version
        requirements before attempting to use server features. Essential for displaying
        installation status and guiding users through setup.

        Returns:
            dict: Contains 'installed' (bool), 'version' (str), 'compatible' (bool),
                  and 'required_version' (str) keys
        """
        logger.info("Checking lemonade-server version...")

        result = await self.execute_lemonade_server_command(["--version"])

        if result is None:
            logger.error("All lemonade-server commands failed")
            return {
                "installed": False,
                "version": None,
                "compatible": False,
                "required_version": self.minimum_version,
            }

        version_line = result.stdout.strip()
        logger.info(f"Raw version output: '{version_line}'")

        # Extract version number (format might be "lemonade-server 8.1.3" or just "8.1.3")
        version_match = re.search(r"(\d+\.\d+\.\d+)", version_line)
        if version_match:
            version = version_match.group(1)
            logger.info(f"Extracted version: {version}")

            # Check if the version number is allowed
            version_parts = [int(x) for x in version.split(".")]
            required_parts = [int(x) for x in self.minimum_version.split(".")]
            is_compatible = version_parts >= required_parts
            logger.info(
                f"Version parts: {version_parts}, Required: {required_parts}, "
                "Compatible: {is_compatible}"
            )

            return {
                "installed": True,
                "version": version,
                "compatible": is_compatible,
                "required_version": self.minimum_version,
            }
        else:
            logger.warning(f"Could not extract version from output: '{version_line}'")
            return {
                "installed": True,
                "version": "unknown",
                "compatible": False,
                "required_version": self.minimum_version,
            }

    async def check_lemonade_server_running(self):
        """
        Check if the lemonade-server process is currently running.

        Use this to determine server status before attempting operations that require
        a running server. Helps decide whether to start the server or proceed with
        API calls.

        Returns:
            bool: True if server process is running, False otherwise
        """
        logger.info("Checking if lemonade-server is running...")

        result = await self.execute_lemonade_server_command(["status"])

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

    async def start_lemonade_server(self):
        """
        Start the lemonade-server process in the background.

        Use this to launch the server when it's not running and your app needs server
        functionality. The server runs in a separate process and the method tracks the
        process to avoid multiple instances.

        Returns:
            dict: Contains 'success' (bool) and 'message' (str) keys indicating
                  whether the server started successfully
        """
        logger.info("Attempting to start lemonade-server...")

        # Check if server is already running
        if self.server_process and self.server_process.poll() is None:
            logger.info("Server process is already running")
            return {"success": True, "message": "Server is already running"}

        stdout_file = tempfile.NamedTemporaryFile(
            mode="w+", delete=False, suffix=".log"
        )
        stderr_file = tempfile.NamedTemporaryFile(
            mode="w+", delete=False, suffix=".log"
        )

        # Use the unified function to start the server
        process = await self.execute_lemonade_server_command(
            ["serve", "--ctx-size", "16384"],
            use_popen=True,
            stdout_file=stdout_file,
            stderr_file=stderr_file,
        )

        if process is None:
            logger.error("All lemonade-server start commands failed")
            stdout_file.close()
            stderr_file.close()
            try:
                os.unlink(stdout_file.name)
                os.unlink(stderr_file.name)
            except Exception:
                pass
            return {
                "success": False,
                "message": "Failed to start server: all commands failed",
            }

        # Give the process a moment to start and check if it's still running
        time.sleep(1)

        # Check if process is still alive
        if process.poll() is None:
            logger.info(f"Successfully started lemonade-server with PID: {process.pid}")
            self.server_process = process

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
                with open(stderr_file.name, "r", encoding="utf-8") as f:
                    stderr_content = f.read().strip()
                with open(stdout_file.name, "r", encoding="utf-8") as f:
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
                except Exception:
                    pass

            except Exception as read_error:
                logger.error(f"Could not read process output: {read_error}")

            return {"success": False, "message": "Server process died immediately"}

    async def install_lemonade_sdk_package(self):
        """
        Install the lemonade-sdk Python package using pip.

        Use this to install lemonade-server via pip when in development environments
        or when the SDK approach is preferred. Provides access to lemonade-server-dev
        command after successful installation.

        Returns:
            dict: Contains 'success' (bool) and 'message' (str) keys indicating
                  installation result and any error details
        """
        try:
            logger.info("Installing lemonade-sdk package using pip...")

            # Install the package
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "lemonade-sdk"],
                capture_output=True,
                text=True,
                timeout=300,  # 5 minutes timeout
                check=True,
            )

            if result.returncode == 0:
                logger.info("lemonade-sdk package installed successfully")
                return {
                    "success": True,
                    "message": "lemonade-sdk package installed successfully. "
                    "You can now use 'lemonade-server-dev' command.",
                }
            else:
                error_msg = (
                    result.stderr or result.stdout or "Unknown installation error"
                )
                logger.error(f"pip install failed: {error_msg}")
                return {"success": False, "message": f"pip install failed: {error_msg}"}

        except Exception as e:
            logger.error(f"Failed to install lemonade-sdk package: {e}")
            return {"success": False, "message": f"Failed to install: {e}"}

    async def download_and_install_lemonade_server(self):
        """
        Download and install lemonade-server using the best method for the environment.

        Use this as the primary installation method. Automatically chooses between pip
        installation (development environments) or executable installer (PyInstaller bundles).
        Handles the complete installation process including download and setup.

        Returns:
            dict: Contains 'success' (bool), 'message' (str), and optionally 'interactive' (bool)
                  or 'github_link' (str) keys with installation results and next steps
        """

        # Reset server state since we're installing/updating
        self.reset_server_state()

        # If not in PyInstaller environment, prefer pip installation
        if not self.is_pyinstaller_environment():
            logger.info(
                "Development environment detected, attempting pip installation first..."
            )
            pip_result = await self.install_lemonade_sdk_package()
            if pip_result["success"]:
                return pip_result
            else:
                logger.info(
                    "pip installation failed, falling back to GitHub instructions..."
                )
                return {
                    "success": False,
                    "message": "Could not install lemonade-sdk package. "
                    "Please visit https://github.com/lemonade-sdk/lemonade for "
                    "installation instructions.",
                    "github_link": "https://github.com/lemonade-sdk/lemonade",
                }

        # PyInstaller environment or fallback - use installer for Windows
        try:
            # Download the installer
            # pylint: disable=line-too-long
            installer_url = "https://github.com/lemonade-sdk/lemonade/releases/latest/download/Lemonade_Server_Installer.exe"

            # Create temp directory for installer
            temp_dir = tempfile.mkdtemp()
            installer_path = os.path.join(temp_dir, "Lemonade_Server_Installer.exe")

            logger.info(f"Downloading installer from {installer_url}")

            # Download with progress tracking
            async with httpx.AsyncClient(
                timeout=300.0, follow_redirects=True
            ) as client:
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
            try:
                process = subprocess.Popen(install_cmd)

                # Wait a moment to see if the process stays alive
                time.sleep(1)

                # Check if the process is still running
                if process.poll() is None:
                    # Process is still running, installer likely opened successfully
                    logger.info(
                        f"Installer launched successfully with PID: {process.pid}"
                    )
                    return {
                        "success": True,
                        "message": "Installer launched. Please complete the installation and then restart Lemonade Arcade.",
                        "interactive": True,
                    }
                else:
                    # Process died immediately
                    logger.error(
                        f"Installer process died immediately with return code: {process.returncode}"
                    )
                    return {
                        "success": False,
                        "message": "Failed to launch installer. Please download and install manually from: https://github.com/lemonade-sdk/lemonade/releases/latest/download/Lemonade_Server_Installer.exe",
                        "github_link": "https://github.com/lemonade-sdk/lemonade/releases/latest/download/Lemonade_Server_Installer.exe",
                    }

            except Exception as launch_error:
                logger.error(f"Failed to launch installer: {launch_error}")
                return {
                    "success": False,
                    "message": f"Failed to launch installer: {launch_error}. Please download and install manually from: https://github.com/lemonade-sdk/lemonade/releases/latest/download/Lemonade_Server_Installer.exe",
                    "github_link": "https://github.com/lemonade-sdk/lemonade/releases/latest/download/Lemonade_Server_Installer.exe",
                }

        except Exception as e:
            logger.error(f"Failed to download/install lemonade-server: {e}")
            return {"success": False, "message": f"Failed to install: {e}"}

    async def check_lemonade_server_api(self):
        """
        Check if the lemonade-server API is responding to requests.

        Use this to verify that the server is not only running but also accepting
        API connections. More reliable than process checks for determining if the
        server is ready to handle requests.

        Returns:
            bool: True if server API is responding, False otherwise
        """
        logger.info(f"Checking Lemonade Server at {self.url}")

        # Try multiple times with increasing delays to give server time to start
        for attempt in range(3):
            try:
                # Use a longer timeout and retry logic for more robust checking
                async with httpx.AsyncClient(timeout=15.0) as client:
                    response = await client.get(f"{self.url}/api/v1/models")
                    logger.info(
                        f"Server check attempt {attempt + 1} response status: "
                        f"{response.status_code}"
                    )
                    if response.status_code == 200:
                        return True
                    elif response.status_code == 404:
                        # Try the health endpoint if models endpoint doesn't exist
                        logger.info("Models endpoint not found, trying health endpoint")
                        try:
                            health_response = await client.get(f"{self.url}/health")
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
                logger.info(
                    f"Server check attempt {attempt + 1} connection failed: {e}"
                )
            except Exception as e:
                logger.info(f"Server check attempt {attempt + 1} failed: {e}")

            # Wait before next attempt (except on last attempt)
            if attempt < 2:
                import asyncio

                await asyncio.sleep(2)

        logger.info("All server check attempts failed")
        return False

    async def get_available_models(self):
        """
        Retrieve the list of models available on the lemonade-server.

        Use this to discover which models are installed and available for use.
        Helpful for displaying model options to users or verifying that required
        models are available before attempting to use them.

        Returns:
            List[str]: List of model names/IDs available on the server, empty list if none found
        """
        logger.info("Getting available models from Lemonade Server")
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.url}/api/v1/models")
                if response.status_code == 200:
                    data = response.json()
                    models = [model["id"] for model in data.get("data", [])]
                    logger.info(f"Found {len(models)} available models: {models}")
                    return models
                else:
                    logger.warning(
                        f"Failed to get models, status: {response.status_code}"
                    )
        except Exception as e:
            logger.info(f"Error getting models: {e}")
        return []

    async def check_model_installed(self, model):
        """
        Check if a specific model is installed on the server.

        Use this to verify model availability before attempting to load or use a model.
        Essential for apps that depend on specific models to function properly.

        Args:
            model: The model name/ID to check for (e.g., "Qwen3-Coder-30B-A3B-Instruct-GGUF")

        Returns:
            dict: Contains 'installed' (bool) and 'model_name' (str) keys
        """
        logger.info(f"Checking for required model: {model}")

        try:
            models = await self.get_available_models()
            is_installed = model in models
            logger.info(f"Required model installed: {is_installed}")
            return {"installed": is_installed, "model_name": model}
        except Exception as e:
            logger.error(f"Error checking required model: {e}")
            return {"installed": False, "model_name": model}

    async def check_model_loaded(self, model):
        """
        Check if a specific model is currently loaded and ready for inference.

        Use this to verify that a model is loaded before making inference requests.
        Models must be loaded before they can be used for chat completions or other
        inference operations.

        Args:
            model: The model name/ID to check (e.g., "Qwen3-Coder-30B-A3B-Instruct-GGUF")

        Returns:
            dict: Contains 'loaded' (bool), 'model_name' (str), and 'current_model' (str) keys
        """
        logger.info(f"Checking if model is loaded: {model}")

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(f"{self.url}/api/v1/health")

                if response.status_code == 200:
                    status_data = response.json()
                    # Check if the required model is the currently loaded model
                    loaded_model = status_data.get("model_loaded", "")
                    is_loaded = loaded_model == model
                    logger.info(
                        f"Model loaded status: {is_loaded}, current model: {loaded_model}"
                    )
                    return {
                        "loaded": is_loaded,
                        "model_name": model,
                        "current_model": loaded_model,
                    }
                else:
                    logger.warning(
                        f"Failed to get server status: HTTP {response.status_code}"
                    )
                    return {
                        "loaded": False,
                        "model_name": model,
                        "current_model": None,
                    }
        except Exception as e:
            logger.error(f"Error checking model loaded status: {e}")
            return {
                "loaded": False,
                "model_name": model,
                "current_model": None,
            }

    async def install_model(self, model):
        """
        Download and install a model on the lemonade-server.

        Use this to install models that your app requires but aren't currently available
        on the server. The installation process may take several minutes for large models
        and requires an active internet connection.

        Args:
            model: The model name/ID to install (e.g., "Qwen3-Coder-30B-A3B-Instruct-GGUF")

        Returns:
            dict: Contains 'success' (bool) and 'message' (str) keys indicating
                  installation result and any error details
        """
        logger.info(f"Installing model: {model}")

        try:
            async with httpx.AsyncClient(
                timeout=600.0
            ) as client:  # 10 minute timeout for model download
                response = await client.post(
                    f"{self.url}/api/v1/pull",
                    json={"model_name": model},
                    headers={"Content-Type": "application/json"},
                )

                if response.status_code == 200:
                    logger.info(f"Successfully installed model: {model}")
                    return {
                        "success": True,
                        "message": f"Model {model} installed successfully",
                    }
                else:
                    error_msg = f"Failed to install model: HTTP {response.status_code}"
                    logger.error(error_msg)
                    return {"success": False, "message": error_msg}
        except httpx.TimeoutException:
            error_msg = "Model installation timed out - this is a large model and may take longer"
            logger.warning(error_msg)
            return {"success": False, "message": error_msg}
        except Exception as e:
            error_msg = f"Error installing model: {e}"
            logger.error(error_msg)
            return {"success": False, "message": error_msg}

    async def load_model(self, model):
        """
        Load a model into memory for inference operations.

        Use this to prepare an installed model for use. Models must be loaded before
        they can handle chat completions or other inference requests. Only one model
        can be loaded at a time.

        Args:
            model: The model name/ID to load (e.g., "Qwen3-Coder-30B-A3B-Instruct-GGUF")

        Returns:
            dict: Contains 'success' (bool) and 'message' (str) keys indicating
                  whether the model loaded successfully
        """
        logger.info(f"Loading model: {model}")

        try:
            async with httpx.AsyncClient(
                timeout=600.0
            ) as client:  # 10 minute timeout for model loading
                response = await client.post(
                    f"{self.url}/api/v1/load",
                    json={"model_name": model},
                    headers={"Content-Type": "application/json"},
                )

                if response.status_code == 200:
                    logger.info(f"Successfully loaded model: {model}")
                    return {
                        "success": True,
                        "message": f"Model {model} loaded successfully",
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

    async def get_system_info(
        self,
        cache_dir: Optional[str] = None,
        cache_duration_hours: Optional[int] = None,
    ):
        """
        Get system information from lemonade-server with caching support.

        Use this to retrieve detailed hardware information including CPU, GPU, NPU, and memory specs.
        The system-info endpoint is slow, so results are cached by default. Cache never expires
        unless cache_duration_hours is explicitly set.

        Args:
            cache_dir: Directory to store cache file (defaults to ~/.lemonade-arcade)
            cache_duration_hours: Hours to keep cached data (None = never expire, default)

        Returns:
            dict: System information from server, or None if unavailable
        """
        logger.info("Getting system information from lemonade-server...")

        # Set up cache directory and file
        if cache_dir is None:
            cache_dir = Path.home() / ".cache" / "lemonade"
        else:
            cache_dir = Path(cache_dir)

        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file = cache_dir / "lemonade_system_info_cache.json"

        # Try to load from cache first
        if cache_file.exists():
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    cache_data = json.load(f)

                # Check if cache is still valid (if expiration is set)
                if cache_duration_hours is not None:
                    cache_time = datetime.fromisoformat(cache_data["timestamp"])
                    expiry_time = cache_time + timedelta(hours=cache_duration_hours)

                    if datetime.now() < expiry_time:
                        logger.info("Using cached system info (within expiry time)")
                        return cache_data["system_info"]
                    else:
                        logger.info("Cache expired, fetching fresh system info")
                else:
                    # Cache never expires
                    logger.info("Using cached system info (no expiry)")
                    return cache_data["system_info"]

            except Exception as e:
                logger.warning(f"Failed to read cache file: {e}")

        # Fetch fresh system info from server
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(f"{self.url}/api/v1/system-info")

                if response.status_code == 200:
                    system_info = response.json()
                    logger.info("Successfully retrieved system info from server")

                    # Cache the result
                    try:
                        cache_data = {
                            "timestamp": datetime.now().isoformat(),
                            "system_info": system_info,
                        }
                        with open(cache_file, "w", encoding="utf-8") as f:
                            json.dump(cache_data, f, indent=2)
                        logger.info(f"Cached system info to {cache_file}")
                    except Exception as e:
                        logger.warning(f"Failed to cache system info: {e}")

                    return system_info
                else:
                    logger.warning(
                        f"System info request failed: HTTP {response.status_code}"
                    )
                    return None

        except Exception as e:
            logger.error(f"Error fetching system info: {e}")
            return None

    def _parse_memory_size(self, memory_str: str) -> float:
        """
        Parse memory size string like '32.0 GB' to numeric value in GB.

        Args:
            memory_str: Memory string from system info (e.g., "32.0 GB")

        Returns:
            float: Memory size in GB, or 0.0 if parsing fails
        """
        try:
            # Extract number and unit
            match = re.match(r"(\d+\.?\d*)\s*(GB|MB|TB)", memory_str.upper())
            if not match:
                return 0.0

            value = float(match.group(1))
            unit = match.group(2)

            # Convert to GB
            if unit == "MB":
                return value / 1024
            elif unit == "TB":
                return value * 1024
            else:  # GB
                return value

        except Exception:
            return 0.0

    def _check_discrete_gpu_vram(self, devices: Dict) -> bool:
        """
        Check if any discrete GPU has 16GB+ VRAM.

        Args:
            devices: Devices section from system info

        Returns:
            bool: True if discrete GPU with sufficient VRAM found
        """
        try:
            # Check for NVIDIA discrete GPUs
            nvidia_dgpus = devices.get("nvidia_dgpu", [])
            if isinstance(nvidia_dgpus, list):
                for gpu in nvidia_dgpus:
                    if gpu.get("available", False):
                        vram_value = gpu.get("vram_gb", "0")
                        # Handle both numeric and string values
                        if isinstance(vram_value, (int, float)):
                            vram_gb = float(vram_value)
                        else:
                            vram_gb = self._parse_memory_size(str(vram_value))
                        if vram_gb >= 15.9:
                            logger.info(
                                f"Found NVIDIA discrete GPU with {vram_gb}GB VRAM"
                            )
                            return True

            # Check for AMD discrete GPUs
            amd_dgpus = devices.get("amd_dgpu", [])
            if isinstance(amd_dgpus, list):
                for gpu in amd_dgpus:
                    if gpu.get("available", False):
                        vram_value = gpu.get("vram_gb", "0")
                        # Handle both numeric and string values
                        if isinstance(vram_value, (int, float)):
                            vram_gb = float(vram_value)
                        else:
                            vram_gb = self._parse_memory_size(str(vram_value))
                        if vram_gb >= 15.9:
                            logger.info(f"Found AMD discrete GPU with {vram_gb}GB VRAM")
                            return True

        except Exception as e:
            logger.warning(f"Error checking discrete GPU VRAM: {e}")

        return False

    def _is_npu_available(self, devices: Dict) -> bool:
        """
        Check if NPU is available and functional with OGA inference engine.

        Args:
            devices: Devices section from system info

        Returns:
            bool: True if NPU is available and OGA inference engine is available
        """
        try:
            npu = devices.get("npu", {})
            npu_available = npu.get("available", False)

            if not npu_available:
                return False

            # Also check if OGA (ONNX GenAI) inference engine is available
            inference_engines = npu.get("inference_engines", {})
            oga_available = inference_engines.get("oga", {}).get("available", False)

            logger.info(
                f"NPU hardware available: {npu_available}, OGA inference engine available: {oga_available}"
            )
            return npu_available and oga_available
        except Exception:
            return False

    async def select_model_for_hardware(
        self, system_info: Optional[Dict] = None, cache_dir: Optional[str] = None
    ) -> tuple[str, float]:
        """
        Select the optimal model based on hardware capabilities.

        Use this to automatically choose the best model for the user's hardware. The selection
        logic prioritizes larger models for high-end hardware and falls back to smaller models
        for resource-constrained systems.

        Args:
            system_info: Pre-fetched system info (if None, will fetch automatically)
            cache_dir: Directory for caching system info (passed to get_system_info)

        Returns:
            tuple[str, float]: (model_name, size_gb) based on hardware capabilities
        """
        logger.info("Selecting model based on hardware capabilities...")

        # Get system info if not provided
        if system_info is None:
            system_info = await self.get_system_info(cache_dir=cache_dir)

        if system_info is None:
            logger.warning("Could not get system info, using default model")
            return MODELS["default"]

        try:
            # Extract hardware information
            physical_memory_str = system_info.get("Physical Memory", "0 GB")
            memory_gb = self._parse_memory_size(physical_memory_str)
            logger.info(f"System RAM: {memory_gb}GB")

            devices = system_info.get("devices", {})
            has_high_vram_gpu = self._check_discrete_gpu_vram(devices)
            has_npu = self._is_npu_available(devices)

            logger.info(f"High VRAM GPU available: {has_high_vram_gpu}")
            logger.info(f"NPU available: {has_npu}")

            # Apply selection logic
            if memory_gb >= 64.0 or has_high_vram_gpu:
                selected_model = MODELS["high_end"]
                logger.info(
                    f"Selected large model due to sufficient resources (RAM: {memory_gb}GB, High VRAM GPU: {has_high_vram_gpu})"
                )
            elif has_npu:
                selected_model = MODELS["npu"]
                logger.info("Selected NPU-optimized model due to NPU availability")
            else:
                selected_model = MODELS["default"]
                logger.info("Selected default model for standard hardware")

            return selected_model

        except Exception as e:
            logger.error(f"Error in model selection logic: {e}")
            return MODELS["default"]
