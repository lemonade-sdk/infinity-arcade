import unittest
from unittest.mock import patch, MagicMock, AsyncMock, mock_open
import asyncio
import sys
import os
import subprocess
import tempfile
import httpx
import platform
import json
import time
from datetime import datetime, timedelta

# Add the lemonade_arcade package to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from lemonade_arcade.lemonade_client import LemonadeClient
from lemonade_arcade.main import LEMONADE_MINIMUM_VERSION


class TestLemonadeClient(unittest.TestCase):
    def setUp(self):
        """Set up test fixtures before each test method."""
        self.client = LemonadeClient(minimum_version=LEMONADE_MINIMUM_VERSION)

    def test_init(self):
        """Test LemonadeClient initialization."""
        client = LemonadeClient()
        self.assertIsNone(client.server_command)
        self.assertIsNone(client.server_process)
        self.assertEqual(client.url, "http://localhost:8000")
        self.assertEqual(client.minimum_version, "8.1.0")  # Default value

        # Test with custom minimum version
        custom_client = LemonadeClient(minimum_version="8.2.0")
        self.assertEqual(custom_client.minimum_version, "8.2.0")

    def test_is_pyinstaller_environment_false(self):
        """Test is_pyinstaller_environment returns False when not in PyInstaller."""
        with patch.object(sys, "frozen", create=True, new=False):
            result = self.client.is_pyinstaller_environment()
            self.assertFalse(result)

    def test_is_pyinstaller_environment_true(self):
        """Test is_pyinstaller_environment returns True when in PyInstaller."""
        with patch.object(sys, "frozen", create=True, new=True):
            result = self.client.is_pyinstaller_environment()
            self.assertTrue(result)

    def test_is_pyinstaller_environment_no_attribute(self):
        """Test is_pyinstaller_environment returns False when frozen attribute doesn't exist."""
        if hasattr(sys, "frozen"):
            delattr(sys, "frozen")
        result = self.client.is_pyinstaller_environment()
        self.assertFalse(result)

    @unittest.skipIf(platform.system() != "Windows", "Windows-specific test")
    @patch("os.path.exists")
    @patch("os.environ.get")
    def test_find_lemonade_server_paths_windows(self, mock_env_get, mock_exists):
        """Test finding lemonade server paths on Windows."""
        # Mock PATH with lemonade_server entries
        mock_env_get.return_value = "C:\\Windows\\System32;C:\\lemonade_server\\bin;D:\\other\\bin\\lemonade_server"
        mock_exists.side_effect = lambda path: "lemonade_server" in path

        with patch("sys.platform", "win32"):
            paths = self.client.find_lemonade_server_paths()
            expected_paths = [
                "C:\\lemonade_server\\bin",
                "D:\\other\\bin\\lemonade_server",
            ]
            self.assertEqual(paths, expected_paths)

    @patch("os.path.exists")
    @patch("os.environ.get")
    def test_find_lemonade_server_paths_linux(self, mock_env_get, mock_exists):
        """Test finding lemonade server paths on Linux."""
        mock_env_get.return_value = (
            "/usr/bin:/home/user/lemonade_server/bin:/usr/local/bin"
        )
        mock_exists.side_effect = lambda path: "lemonade_server" in path

        with patch("sys.platform", "linux"):
            paths = self.client.find_lemonade_server_paths()
            expected_paths = ["/home/user/lemonade_server/bin"]
            self.assertEqual(paths, expected_paths)

    @patch("os.path.exists")
    @patch("os.environ.get")
    def test_find_lemonade_server_paths_empty(self, mock_env_get, mock_exists):
        """Test finding lemonade server paths returns empty list when none found."""
        mock_env_get.return_value = "/usr/bin:/usr/local/bin"
        mock_exists.return_value = False

        paths = self.client.find_lemonade_server_paths()
        self.assertEqual(paths, [])

    def test_reset_server_state(self):
        """Test resetting server state."""
        # Set up initial state
        self.client.server_command = ["test", "command"]
        mock_process = MagicMock()
        mock_process.poll.return_value = None  # Process is running
        self.client.server_process = mock_process

        self.client.reset_server_state()

        self.assertIsNone(self.client.server_command)
        self.assertIsNone(self.client.server_process)
        mock_process.terminate.assert_called_once()

    def test_reset_server_state_process_already_terminated(self):
        """Test resetting server state when process is already terminated."""
        self.client.server_command = ["test", "command"]
        mock_process = MagicMock()
        mock_process.poll.return_value = 1  # Process has terminated
        self.client.server_process = mock_process

        self.client.reset_server_state()

        self.assertIsNone(self.client.server_command)
        self.assertIsNone(self.client.server_process)
        mock_process.terminate.assert_not_called()

    def test_reset_server_state_terminate_exception(self):
        """Test resetting server state when terminate raises exception."""
        self.client.server_command = ["test", "command"]
        mock_process = MagicMock()
        mock_process.poll.return_value = None
        mock_process.terminate.side_effect = Exception("Test exception")
        self.client.server_process = mock_process

        # Should not raise exception
        self.client.reset_server_state()

        self.assertIsNone(self.client.server_command)
        self.assertIsNone(self.client.server_process)

    @unittest.skipIf(platform.system() != "Windows", "Windows-specific test")
    @patch("winreg.OpenKey")
    @patch("winreg.QueryValueEx")
    @patch("os.environ")
    def test_refresh_environment_windows_success(
        self, mock_environ, mock_query, mock_open_key
    ):
        """Test refreshing environment variables on Windows successfully."""
        # Mock registry access
        mock_context_manager = MagicMock()
        mock_open_key.return_value.__enter__.return_value = mock_context_manager
        mock_query.side_effect = [
            ("C:\\Windows\\System32;C:\\Program Files", 1),  # System PATH
            ("C:\\Users\\User\\bin", 1),  # User PATH
        ]

        # Mock Python Scripts discovery to return empty list
        with patch.object(
            self.client, "_discover_python_scripts_paths", return_value=[]
        ):
            self.client.refresh_environment()

        # Check that PATH was updated
        expected_path = "C:\\Users\\User\\bin;C:\\Windows\\System32;C:\\Program Files"
        mock_environ.__setitem__.assert_called_with("PATH", expected_path)

    @unittest.skipIf(platform.system() != "Windows", "Windows-specific test")
    @patch("winreg.OpenKey")
    @patch("winreg.QueryValueEx")
    def test_refresh_environment_windows_no_user_path(self, mock_query, mock_open_key):
        """Test refreshing environment variables when user PATH doesn't exist."""
        mock_context_manager = MagicMock()
        mock_open_key.return_value.__enter__.return_value = mock_context_manager
        mock_query.side_effect = [
            ("C:\\Windows\\System32", 1),  # System PATH
            FileNotFoundError(),  # User PATH not found
        ]

        with patch("os.environ") as mock_environ:
            # Mock Python Scripts discovery to return empty list
            with patch.object(
                self.client, "_discover_python_scripts_paths", return_value=[]
            ):
                self.client.refresh_environment()
            # Should still set PATH to system PATH only
            mock_environ.__setitem__.assert_called_with("PATH", "C:\\Windows\\System32")

    @unittest.skipIf(platform.system() != "Windows", "Windows-specific test")
    @patch("winreg.OpenKey")
    def test_refresh_environment_windows_exception(self, mock_open_key):
        """Test refreshing environment variables when registry access fails."""
        mock_open_key.side_effect = Exception("Registry error")

        # Should not raise exception
        self.client.refresh_environment()

    async def test_execute_lemonade_server_command_with_stored_command(self):
        """Test executing command when server_command is already stored."""
        self.client.server_command = ["lemonade-server"]

        with patch("subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = "test output"
            mock_result.stderr = ""
            mock_run.return_value = mock_result

            result = await self.client.execute_lemonade_server_command(["--version"])

            self.assertEqual(result, mock_result)
            mock_run.assert_called_once()
            # Check that the command includes the stored command + args
            args, kwargs = mock_run.call_args
            self.assertIn("lemonade-server --version", args[0])

    @unittest.skipIf(platform.system() != "Windows", "Windows-specific test")
    async def test_execute_lemonade_server_command_windows_success(self):
        """Test executing command on Windows with successful result."""
        with patch("sys.platform", "win32"), patch.object(
            self.client, "is_pyinstaller_environment", return_value=False
        ), patch.object(
            self.client, "find_lemonade_server_paths", return_value=[]
        ), patch(
            "subprocess.run"
        ) as mock_run:

            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = "version 8.1.5"
            mock_result.stderr = ""
            mock_run.return_value = mock_result

            result = await self.client.execute_lemonade_server_command(["--version"])

            self.assertEqual(result, mock_result)
            self.assertEqual(self.client.server_command, ["lemonade-server-dev"])

    async def test_execute_lemonade_server_command_linux_success(self):
        """Test executing command on Linux with successful result."""
        with patch("sys.platform", "linux"), patch("subprocess.run") as mock_run:

            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = "version 8.1.5"
            mock_result.stderr = ""
            mock_run.return_value = mock_result

            result = await self.client.execute_lemonade_server_command(["--version"])

            self.assertEqual(result, mock_result)
            self.assertEqual(self.client.server_command, ["lemonade-server-dev"])

    async def test_execute_lemonade_server_command_popen_mode(self):
        """Test executing command with use_popen=True."""
        with patch("subprocess.Popen") as mock_popen:
            mock_process = MagicMock()
            mock_popen.return_value = mock_process

            result = await self.client.execute_lemonade_server_command(
                ["serve"], use_popen=True
            )

            self.assertEqual(result, mock_process)
            mock_popen.assert_called_once()

    async def test_execute_lemonade_server_command_all_fail(self):
        """Test executing command when all commands fail."""
        with patch("sys.platform", "linux"), patch("subprocess.run") as mock_run:

            mock_run.side_effect = FileNotFoundError("Command not found")

            result = await self.client.execute_lemonade_server_command(["--version"])

            self.assertIsNone(result)

    async def test_execute_lemonade_server_command_timeout(self):
        """Test executing command with timeout."""
        with patch("sys.platform", "linux"), patch("subprocess.run") as mock_run:

            mock_run.side_effect = subprocess.TimeoutExpired("cmd", 10)

            result = await self.client.execute_lemonade_server_command(["--version"])

            self.assertIsNone(result)

    async def test_check_lemonade_sdk_available_true(self):
        """Test checking lemonade-sdk availability when available."""
        with patch("subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = "available"
            mock_run.return_value = mock_result

            result = await self.client.check_lemonade_sdk_available()

            self.assertTrue(result)

    async def test_check_lemonade_sdk_available_false(self):
        """Test checking lemonade-sdk availability when not available."""
        with patch("subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 1
            mock_result.stdout = "error"
            mock_run.return_value = mock_result

            result = await self.client.check_lemonade_sdk_available()

            self.assertFalse(result)

    async def test_check_lemonade_sdk_available_exception(self):
        """Test checking lemonade-sdk availability when exception occurs."""
        with patch("subprocess.run", side_effect=Exception("Test error")):
            result = await self.client.check_lemonade_sdk_available()
            self.assertFalse(result)

    async def test_check_lemonade_server_version_success(self):
        """Test checking lemonade server version successfully."""
        with patch.object(self.client, "execute_lemonade_server_command") as mock_exec:
            mock_result = MagicMock()
            # Calculate a compatible version by incrementing the patch version
            min_parts = LEMONADE_MINIMUM_VERSION.split(".")
            compatible_version = (
                f"{min_parts[0]}.{min_parts[1]}.{int(min_parts[2]) + 1}"
            )
            mock_result.stdout = f"lemonade-server {compatible_version}"
            mock_exec.return_value = mock_result

            result = await self.client.check_lemonade_server_version()

            expected = {
                "installed": True,
                "version": compatible_version,
                "compatible": True,
                "required_version": LEMONADE_MINIMUM_VERSION,
            }
            self.assertEqual(result, expected)

    async def test_check_lemonade_server_version_incompatible(self):
        """Test checking lemonade server version with incompatible version."""
        with patch.object(self.client, "execute_lemonade_server_command") as mock_exec:
            mock_result = MagicMock()
            mock_result.stdout = "lemonade-server 8.1.0"  # Lower than minimum
            mock_exec.return_value = mock_result

            result = await self.client.check_lemonade_server_version()

            expected = {
                "installed": True,
                "version": "8.1.0",
                "compatible": False,
                "required_version": LEMONADE_MINIMUM_VERSION,
            }
            self.assertEqual(result, expected)

    async def test_check_lemonade_server_version_no_version_match(self):
        """Test checking lemonade server version when no version is found in output."""
        with patch.object(self.client, "execute_lemonade_server_command") as mock_exec:
            mock_result = MagicMock()
            mock_result.stdout = "invalid version output"
            mock_exec.return_value = mock_result

            result = await self.client.check_lemonade_server_version()

            expected = {
                "installed": True,
                "version": "unknown",
                "compatible": False,
                "required_version": LEMONADE_MINIMUM_VERSION,
            }
            self.assertEqual(result, expected)

    async def test_check_lemonade_server_version_command_failed(self):
        """Test checking lemonade server version when command fails."""
        with patch.object(self.client, "execute_lemonade_server_command") as mock_exec:
            mock_exec.return_value = None

            result = await self.client.check_lemonade_server_version()

            expected = {
                "installed": False,
                "version": None,
                "compatible": False,
                "required_version": LEMONADE_MINIMUM_VERSION,
            }
            self.assertEqual(result, expected)

    async def test_check_lemonade_server_running_true(self):
        """Test checking if lemonade server is running - returns True."""
        with patch.object(self.client, "execute_lemonade_server_command") as mock_exec:
            mock_result = MagicMock()
            mock_result.stdout = "Server is running on port 8000"
            mock_exec.return_value = mock_result

            result = await self.client.check_lemonade_server_running()

            self.assertTrue(result)

    async def test_check_lemonade_server_running_false(self):
        """Test checking if lemonade server is running - returns False."""
        with patch.object(self.client, "execute_lemonade_server_command") as mock_exec:
            mock_result = MagicMock()
            mock_result.stdout = "Server is not running"
            mock_exec.return_value = mock_result

            result = await self.client.check_lemonade_server_running()

            self.assertFalse(result)

    async def test_check_lemonade_server_running_command_failed(self):
        """Test checking if lemonade server is running when command fails."""
        with patch.object(self.client, "execute_lemonade_server_command") as mock_exec:
            mock_exec.return_value = None

            result = await self.client.check_lemonade_server_running()

            self.assertFalse(result)

    async def test_start_lemonade_server_already_running(self):
        """Test starting lemonade server when it's already running."""
        mock_process = MagicMock()
        mock_process.poll.return_value = None  # Process is running
        self.client.server_process = mock_process

        result = await self.client.start_lemonade_server()

        expected = {"success": True, "message": "Server is already running"}
        self.assertEqual(result, expected)

    @patch("tempfile.NamedTemporaryFile")
    @patch("time.sleep")
    @patch("os.unlink")
    async def test_start_lemonade_server_success(
        self, mock_unlink, mock_sleep, mock_temp_file
    ):
        """Test starting lemonade server successfully."""
        # Mock temp files
        mock_stdout_file = MagicMock()
        mock_stderr_file = MagicMock()
        mock_stdout_file.name = "stdout.log"
        mock_stderr_file.name = "stderr.log"
        mock_temp_file.side_effect = [mock_stdout_file, mock_stderr_file]

        # Mock process
        mock_process = MagicMock()
        mock_process.poll.return_value = None  # Process is running
        mock_process.pid = 12345

        with patch.object(self.client, "execute_lemonade_server_command") as mock_exec:
            mock_exec.return_value = mock_process

            result = await self.client.start_lemonade_server()

            expected = {"success": True, "message": "Server start command issued"}
            self.assertEqual(result, expected)
            self.assertEqual(self.client.server_process, mock_process)

    @patch("tempfile.NamedTemporaryFile")
    async def test_start_lemonade_server_command_failed(self, mock_temp_file):
        """Test starting lemonade server when command fails."""
        mock_stdout_file = MagicMock()
        mock_stderr_file = MagicMock()
        mock_temp_file.side_effect = [mock_stdout_file, mock_stderr_file]

        with patch.object(self.client, "execute_lemonade_server_command") as mock_exec:
            mock_exec.return_value = None

            result = await self.client.start_lemonade_server()

            expected = {
                "success": False,
                "message": "Failed to start server: all commands failed",
            }
            self.assertEqual(result, expected)

    @patch("tempfile.NamedTemporaryFile")
    @patch("time.sleep")
    @patch("builtins.open", new_callable=mock_open, read_data="Error message")
    @patch("os.unlink")
    async def test_start_lemonade_server_process_dies(
        self, mock_unlink, mock_file, mock_sleep, mock_temp_file
    ):
        """Test starting lemonade server when process dies immediately."""
        mock_stdout_file = MagicMock()
        mock_stderr_file = MagicMock()
        mock_stdout_file.name = "stdout.log"
        mock_stderr_file.name = "stderr.log"
        mock_temp_file.side_effect = [mock_stdout_file, mock_stderr_file]

        mock_process = MagicMock()
        mock_process.poll.return_value = 1  # Process has died
        mock_process.returncode = 1

        with patch.object(self.client, "execute_lemonade_server_command") as mock_exec:
            mock_exec.return_value = mock_process

            result = await self.client.start_lemonade_server()

            expected = {"success": False, "message": "Server process died immediately"}
            self.assertEqual(result, expected)

    async def test_install_lemonade_sdk_package_success(self):
        """Test installing lemonade-sdk package successfully."""
        with patch("subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_run.return_value = mock_result

            result = await self.client.install_lemonade_sdk_package()

            expected = {
                "success": True,
                "message": "lemonade-sdk package installed successfully. You can now use 'lemonade-server-dev' command.",
            }
            self.assertEqual(result, expected)

    async def test_install_lemonade_sdk_package_failure(self):
        """Test installing lemonade-sdk package with failure."""
        with patch("subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 1
            mock_result.stderr = "Installation failed"
            mock_run.return_value = mock_result

            result = await self.client.install_lemonade_sdk_package()

            self.assertFalse(result["success"])
            self.assertIn("pip install failed", result["message"])

    async def test_install_lemonade_sdk_package_exception(self):
        """Test installing lemonade-sdk package with exception."""
        with patch("subprocess.run", side_effect=Exception("Test error")):
            result = await self.client.install_lemonade_sdk_package()

            self.assertFalse(result["success"])
            self.assertIn("Failed to install", result["message"])

    @patch.object(LemonadeClient, "reset_server_state")
    @patch.object(LemonadeClient, "is_pyinstaller_environment")
    @patch.object(LemonadeClient, "install_lemonade_sdk_package")
    async def test_download_and_install_lemonade_server_pip_success(
        self, mock_install, mock_pyinstaller, mock_reset
    ):
        """Test downloading and installing lemonade server via pip successfully."""
        mock_pyinstaller.return_value = False
        mock_install.return_value = {"success": True, "message": "Success"}

        result = await self.client.download_and_install_lemonade_server()

        self.assertTrue(result["success"])
        mock_reset.assert_called_once()
        mock_install.assert_called_once()

    @patch.object(LemonadeClient, "reset_server_state")
    @patch.object(LemonadeClient, "is_pyinstaller_environment")
    @patch.object(LemonadeClient, "install_lemonade_sdk_package")
    async def test_download_and_install_lemonade_server_pip_failure(
        self, mock_install, mock_pyinstaller, mock_reset
    ):
        """Test downloading and installing lemonade server when pip fails."""
        mock_pyinstaller.return_value = False
        mock_install.return_value = {"success": False, "message": "Pip failed"}

        result = await self.client.download_and_install_lemonade_server()

        self.assertFalse(result["success"])
        self.assertIn("github.com", result["message"])

    @patch("tempfile.mkdtemp")
    @patch("subprocess.Popen")
    @patch("httpx.AsyncClient")
    @patch.object(LemonadeClient, "reset_server_state")
    @patch.object(LemonadeClient, "is_pyinstaller_environment")
    async def test_download_and_install_lemonade_server_installer(
        self, mock_pyinstaller, mock_reset, mock_httpx, mock_popen, mock_mkdtemp
    ):
        """Test downloading and installing lemonade server via installer."""
        mock_pyinstaller.return_value = True
        mock_mkdtemp.return_value = "/tmp/test"

        # Mock HTTP client and response properly
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200

        # Mock aiter_bytes as an async generator
        async def mock_aiter_bytes(chunk_size=8192):
            yield b"test data"

        mock_response.aiter_bytes = mock_aiter_bytes

        # Mock the stream context manager
        mock_stream_context = MagicMock()
        mock_stream_context.__aenter__ = AsyncMock(return_value=mock_response)
        mock_stream_context.__aexit__ = AsyncMock(return_value=None)
        mock_client.stream.return_value = mock_stream_context

        # Mock the client context manager
        mock_client_context = MagicMock()
        mock_client_context.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_context.__aexit__ = AsyncMock(return_value=None)
        mock_httpx.return_value = mock_client_context

        mock_process = MagicMock()
        mock_popen.return_value = mock_process

        with patch("builtins.open", mock_open()):
            result = await self.client.download_and_install_lemonade_server()

        self.assertTrue(result["success"])
        self.assertTrue(result["interactive"])
        mock_reset.assert_called_once()

    async def test_check_lemonade_server_api_success(self):
        """Test checking lemonade server API successfully."""
        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get.return_value = (
                mock_response
            )

            result = await self.client.check_lemonade_server_api()

            self.assertTrue(result)

    async def test_check_lemonade_server_api_health_endpoint(self):
        """Test checking lemonade server API using health endpoint."""
        mock_models_response = MagicMock()
        mock_models_response.status_code = 404
        mock_health_response = MagicMock()
        mock_health_response.status_code = 200

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get.side_effect = [
                mock_models_response,
                mock_health_response,
            ]

            result = await self.client.check_lemonade_server_api()

            self.assertTrue(result)

    async def test_check_lemonade_server_api_timeout(self):
        """Test checking lemonade server API with timeout."""
        with patch("httpx.AsyncClient") as mock_client, patch("asyncio.sleep"):
            mock_client.return_value.__aenter__.return_value.get.side_effect = (
                httpx.TimeoutException("Timeout")
            )

            result = await self.client.check_lemonade_server_api()

            self.assertFalse(result)

    async def test_check_lemonade_server_api_connection_error(self):
        """Test checking lemonade server API with connection error."""
        with patch("httpx.AsyncClient") as mock_client, patch("asyncio.sleep"):
            mock_client.return_value.__aenter__.return_value.get.side_effect = (
                httpx.ConnectError("Connection failed")
            )

            result = await self.client.check_lemonade_server_api()

            self.assertFalse(result)

    async def test_get_available_models_success(self):
        """Test getting available models successfully."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": [{"id": "model1"}, {"id": "model2"}]}

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get.return_value = (
                mock_response
            )

            result = await self.client.get_available_models()

            self.assertEqual(result, ["model1", "model2"])

    async def test_get_available_models_failure(self):
        """Test getting available models with API failure."""
        mock_response = MagicMock()
        mock_response.status_code = 500

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get.return_value = (
                mock_response
            )

            result = await self.client.get_available_models()

            self.assertEqual(result, [])

    async def test_get_available_models_exception(self):
        """Test getting available models with exception."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get.side_effect = (
                Exception("Test error")
            )

            result = await self.client.get_available_models()

            self.assertEqual(result, [])

    async def test_check_model_installed_true(self):
        """Test checking if model is installed - returns True."""
        with patch.object(self.client, "get_available_models") as mock_get_models:
            mock_get_models.return_value = ["model1", "model2", "test_model"]

            result = await self.client.check_model_installed("test_model")

            expected = {"installed": True, "model_name": "test_model"}
            self.assertEqual(result, expected)

    async def test_check_model_installed_false(self):
        """Test checking if model is installed - returns False."""
        with patch.object(self.client, "get_available_models") as mock_get_models:
            mock_get_models.return_value = ["model1", "model2"]

            result = await self.client.check_model_installed("test_model")

            expected = {"installed": False, "model_name": "test_model"}
            self.assertEqual(result, expected)

    async def test_check_model_installed_exception(self):
        """Test checking if model is installed with exception."""
        with patch.object(self.client, "get_available_models") as mock_get_models:
            mock_get_models.side_effect = Exception("Test error")

            result = await self.client.check_model_installed("test_model")

            expected = {"installed": False, "model_name": "test_model"}
            self.assertEqual(result, expected)

    async def test_check_model_loaded_true(self):
        """Test checking if model is loaded - returns True."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"model_loaded": "test_model"}

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get.return_value = (
                mock_response
            )

            result = await self.client.check_model_loaded("test_model")

            expected = {
                "loaded": True,
                "model_name": "test_model",
                "current_model": "test_model",
            }
            self.assertEqual(result, expected)

    async def test_check_model_loaded_false(self):
        """Test checking if model is loaded - returns False."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"model_loaded": "other_model"}

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get.return_value = (
                mock_response
            )

            result = await self.client.check_model_loaded("test_model")

            expected = {
                "loaded": False,
                "model_name": "test_model",
                "current_model": "other_model",
            }
            self.assertEqual(result, expected)

    async def test_check_model_loaded_api_failure(self):
        """Test checking if model is loaded with API failure."""
        mock_response = MagicMock()
        mock_response.status_code = 500

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get.return_value = (
                mock_response
            )

            result = await self.client.check_model_loaded("test_model")

            expected = {
                "loaded": False,
                "model_name": "test_model",
                "current_model": None,
            }
            self.assertEqual(result, expected)

    async def test_check_model_loaded_exception(self):
        """Test checking if model is loaded with exception."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get.side_effect = (
                Exception("Test error")
            )

            result = await self.client.check_model_loaded("test_model")

            expected = {
                "loaded": False,
                "model_name": "test_model",
                "current_model": None,
            }
            self.assertEqual(result, expected)

    async def test_install_model_success(self):
        """Test installing model successfully."""
        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post.return_value = (
                mock_response
            )

            result = await self.client.install_model("test_model")

            expected = {
                "success": True,
                "message": "Model test_model installed successfully",
            }
            self.assertEqual(result, expected)

    async def test_install_model_failure(self):
        """Test installing model with API failure."""
        mock_response = MagicMock()
        mock_response.status_code = 500

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post.return_value = (
                mock_response
            )

            result = await self.client.install_model("test_model")

            self.assertFalse(result["success"])
            self.assertIn("Failed to install model", result["message"])

    async def test_install_model_timeout(self):
        """Test installing model with timeout."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post.side_effect = (
                httpx.TimeoutException("Timeout")
            )

            result = await self.client.install_model("test_model")

            self.assertFalse(result["success"])
            self.assertIn("timed out", result["message"])

    async def test_install_model_exception(self):
        """Test installing model with exception."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post.side_effect = (
                Exception("Test error")
            )

            result = await self.client.install_model("test_model")

            self.assertFalse(result["success"])
            self.assertIn("Error installing model", result["message"])

    async def test_load_model_success(self):
        """Test loading model successfully."""
        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post.return_value = (
                mock_response
            )

            result = await self.client.load_model("test_model")

            expected = {
                "success": True,
                "message": "Model test_model loaded successfully",
            }
            self.assertEqual(result, expected)

    async def test_load_model_failure(self):
        """Test loading model with API failure."""
        mock_response = MagicMock()
        mock_response.status_code = 500

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post.return_value = (
                mock_response
            )

            result = await self.client.load_model("test_model")

            self.assertFalse(result["success"])
            self.assertIn("Failed to load model", result["message"])

    async def test_load_model_timeout(self):
        """Test loading model with timeout."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post.side_effect = (
                httpx.TimeoutException("Timeout")
            )

            result = await self.client.load_model("test_model")

            self.assertFalse(result["success"])
            self.assertIn("timed out", result["message"])

    async def test_load_model_exception(self):
        """Test loading model with exception."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post.side_effect = (
                Exception("Test error")
            )

            result = await self.client.load_model("test_model")

            self.assertFalse(result["success"])
            self.assertIn("Error loading model", result["message"])

    async def test_get_system_info_success(self):
        """Test getting system info successfully."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "OS Version": "Windows-10-10.0.26100-SP0",
            "Processor": "AMD Ryzen AI 9 HX 370 w/ Radeon 890M",
            "Physical Memory": "32.0 GB",
            "devices": {
                "cpu": {"name": "AMD Ryzen AI 9 HX 370", "available": True},
                "amd_igpu": {"name": "AMD Radeon 890M Graphics", "available": True},
                "amd_dgpu": [
                    {"available": False, "error": "No AMD discrete GPU found"}
                ],
                "npu": {"name": "AMD NPU", "available": True},
            },
        }

        with patch("httpx.AsyncClient") as mock_client, patch(
            "builtins.open", mock_open()
        ) as mock_file, patch("os.path.exists", return_value=False), patch(
            "os.makedirs"
        ):

            mock_client.return_value.__aenter__.return_value.get.return_value = (
                mock_response
            )

            with patch("tempfile.mkdtemp") as mock_mkdtemp:
                mock_mkdtemp.return_value = "/tmp/test"
                result = await self.client.get_system_info()

            self.assertIsInstance(result, dict)
            self.assertEqual(result["OS Version"], "Windows-10-10.0.26100-SP0")
            self.assertIn("devices", result)

    async def test_get_system_info_cached(self):
        """Test getting system info from cache."""
        system_info_data = {
            "OS Version": "Linux-Ubuntu-22.04",
            "Physical Memory": "16.0 GB",
            "devices": {"cpu": {"available": True}},
        }

        # The actual cache structure includes timestamp and system_info wrapper
        cached_data = {
            "timestamp": "2024-01-01T12:00:00",
            "system_info": system_info_data,
        }

        with patch(
            "builtins.open", mock_open(read_data=json.dumps(cached_data))
        ), patch(
            "lemonade_arcade.lemonade_client.datetime"
        ) as mock_datetime_module, patch(
            "pathlib.Path.exists", return_value=True
        ), patch(
            "pathlib.Path.mkdir"
        ):

            # Mock datetime objects for cache expiry logic
            mock_cache_time = datetime(2024, 1, 1, 12, 0, 0)
            mock_current_time = datetime(2024, 1, 1, 13, 0, 0)  # 1 hour later

            # Mock the datetime.fromisoformat and datetime.now methods
            mock_datetime_module.fromisoformat.return_value = mock_cache_time
            mock_datetime_module.now.return_value = mock_current_time

            result = await self.client.get_system_info(cache_duration_hours=24)

            self.assertEqual(result, system_info_data)

    async def test_get_system_info_api_failure(self):
        """Test getting system info when API fails."""
        mock_response = MagicMock()
        mock_response.status_code = 500

        with patch("httpx.AsyncClient") as mock_client, patch(
            "os.path.exists", return_value=False
        ):

            mock_client.return_value.__aenter__.return_value.get.return_value = (
                mock_response
            )

            result = await self.client.get_system_info()
            self.assertIsNone(result)

    def test_parse_memory_size(self):
        """Test parsing memory size strings."""
        self.assertEqual(self.client._parse_memory_size("32.0 GB"), 32.0)
        self.assertEqual(self.client._parse_memory_size("16 GB"), 16.0)
        self.assertEqual(self.client._parse_memory_size("8.5 GB"), 8.5)
        self.assertEqual(self.client._parse_memory_size("invalid"), 0.0)

    def test_check_discrete_gpu_vram(self):
        """Test checking discrete GPU VRAM."""
        # Test with NVIDIA GPU having enough VRAM
        devices_nvidia_good = {"nvidia_dgpu": [{"available": True, "vram": "20.0 GB"}]}
        self.assertTrue(self.client._check_discrete_gpu_vram(devices_nvidia_good))

        # Test with NVIDIA GPU not having enough VRAM
        devices_nvidia_bad = {"nvidia_dgpu": [{"available": True, "vram": "8.0 GB"}]}
        self.assertFalse(self.client._check_discrete_gpu_vram(devices_nvidia_bad))

        # Test with AMD GPU having enough VRAM
        devices_amd_good = {"amd_dgpu": [{"available": True, "vram": "18.0 GB"}]}
        self.assertTrue(self.client._check_discrete_gpu_vram(devices_amd_good))

        # Test with no discrete GPU
        devices_no_dgpu = {
            "nvidia_dgpu": [{"available": False}],
            "amd_dgpu": [{"available": False}],
        }
        self.assertFalse(self.client._check_discrete_gpu_vram(devices_no_dgpu))

    def test_is_npu_available(self):
        """Test checking NPU availability."""
        # Test with available NPU
        devices_with_npu = {"npu": {"available": True, "name": "AMD NPU"}}
        self.assertTrue(self.client._is_npu_available(devices_with_npu))

        # Test with unavailable NPU
        devices_no_npu = {"npu": {"available": False}}
        self.assertFalse(self.client._is_npu_available(devices_no_npu))

        # Test with missing NPU key
        devices_missing_npu = {"cpu": {"available": True}}
        self.assertFalse(self.client._is_npu_available(devices_missing_npu))

    async def test_select_model_for_hardware_high_end(self):
        """Test model selection for high-end hardware (64GB+ RAM)."""
        system_info = {
            "Physical Memory": "64.0 GB",
            "devices": {
                "nvidia_dgpu": [{"available": False}],
                "amd_dgpu": [{"available": False}],
                "npu": {"available": False},
            },
        }

        with patch.object(self.client, "get_system_info", return_value=system_info):
            model_name, size_gb = await self.client.select_model_for_hardware()

            self.assertEqual(model_name, "Qwen3-Coder-30B-A3B-Instruct-GGUF")
            self.assertEqual(size_gb, 18.6)

    async def test_select_model_for_hardware_high_end_gpu(self):
        """Test model selection for high-end hardware (16GB+ VRAM)."""
        system_info = {
            "Physical Memory": "32.0 GB",
            "devices": {
                "nvidia_dgpu": [{"available": True, "vram": "20.0 GB"}],
                "amd_dgpu": [{"available": False}],
                "npu": {"available": False},
            },
        }

        with patch.object(self.client, "get_system_info", return_value=system_info):
            model_name, size_gb = await self.client.select_model_for_hardware()

            self.assertEqual(model_name, "Qwen3-Coder-30B-A3B-Instruct-GGUF")
            self.assertEqual(size_gb, 18.6)

    async def test_select_model_for_hardware_npu(self):
        """Test model selection for NPU hardware."""
        system_info = {
            "Physical Memory": "32.0 GB",
            "devices": {
                "nvidia_dgpu": [{"available": False}],
                "amd_dgpu": [{"available": False}],
                "npu": {"available": True, "name": "AMD NPU"},
            },
        }

        with patch.object(self.client, "get_system_info", return_value=system_info):
            model_name, size_gb = await self.client.select_model_for_hardware()

            self.assertEqual(model_name, "Qwen-2.5-7B-Instruct-Hybrid")
            self.assertEqual(size_gb, 8.4)

    async def test_select_model_for_hardware_default(self):
        """Test model selection for default hardware."""
        system_info = {
            "Physical Memory": "16.0 GB",
            "devices": {
                "nvidia_dgpu": [{"available": False}],
                "amd_dgpu": [{"available": False}],
                "npu": {"available": False},
            },
        }

        with patch.object(self.client, "get_system_info", return_value=system_info):
            model_name, size_gb = await self.client.select_model_for_hardware()

            self.assertEqual(model_name, "Qwen3-4B-Instruct-2507-GGUF")
            self.assertEqual(size_gb, 2.5)

    async def test_select_model_for_hardware_system_info_failure(self):
        """Test model selection when system info fails."""
        with patch.object(self.client, "get_system_info", return_value=None):
            model_name, size_gb = await self.client.select_model_for_hardware()

            # Should return default model
            self.assertEqual(model_name, "Qwen3-4B-Instruct-2507-GGUF")
            self.assertEqual(size_gb, 2.5)


def run_async_test(coro):
    """Helper function to run async tests."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    try:
        return loop.run_until_complete(coro)
    finally:
        # Clean up any pending tasks
        pending = asyncio.all_tasks(loop)
        for task in pending:
            task.cancel()
        if pending:
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))


# Convert async test methods to sync for unittest
async_test_methods = []
for attr_name in dir(TestLemonadeClient):
    attr = getattr(TestLemonadeClient, attr_name)
    if (
        callable(attr)
        and attr_name.startswith("test_")
        and asyncio.iscoroutinefunction(attr)
    ):
        async_test_methods.append((attr_name, attr))

# Apply the conversion with proper closure handling
for attr_name, original_method in async_test_methods:

    def make_sync_test(method):
        def sync_test(self):
            return run_async_test(method(self))

        return sync_test

    setattr(TestLemonadeClient, attr_name, make_sync_test(original_method))


if __name__ == "__main__":
    unittest.main()
