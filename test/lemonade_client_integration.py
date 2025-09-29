import unittest
from unittest.mock import patch
import asyncio
import sys
import os
import time
import subprocess
import platform
import tempfile
import signal
from pathlib import Path

# Add the lemonade_arcade package to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from lemonade_arcade.lemonade_client import LemonadeClient
from lemonade_arcade.main import LEMONADE_MINIMUM_VERSION


class TestLemonadeClientIntegration(unittest.TestCase):
    """Integration tests for LemonadeClient that actually interact with a real Lemonade server.

    These tests will:
    1. Install lemonade-sdk if not available
    2. Install lemonade-server if needed
    3. Start the server and test real API interactions
    4. Test model installation and loading
    5. Clean up server processes when done
    """

    @classmethod
    def setUpClass(cls):
        """Set up test fixtures for the entire test class."""
        cls.client = LemonadeClient(minimum_version=LEMONADE_MINIMUM_VERSION)
        cls.server_started = False
        cls.test_model = "Qwen3-0.6B-GGUF"  # Small model for testing
        cls.setup_timeout = 300  # 5 minutes for setup
        cls.test_timeout = 60  # 1 minute for individual tests

    @classmethod
    def tearDownClass(cls):
        """Clean up after all tests."""
        if cls.server_started and cls.client.server_process:
            try:
                cls.client.server_process.terminate()
                cls.client.server_process.wait(timeout=10)
            except Exception as e:
                print(f"Warning: Failed to cleanly stop server: {e}")
                if (
                    cls.client.server_process
                    and cls.client.server_process.poll() is None
                ):
                    try:
                        cls.client.server_process.kill()
                    except Exception:
                        pass

    async def async_setUp(self):
        """Async setup for each test."""
        # Reset client state
        self.client.reset_server_state()

    def setUp(self):
        """Set up for each test."""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self.async_setUp())

    def tearDown(self):
        """Clean up after each test."""
        if self.loop:
            # Clean up any pending tasks
            pending = asyncio.all_tasks(self.loop)
            for task in pending:
                task.cancel()
            if pending:
                self.loop.run_until_complete(
                    asyncio.gather(*pending, return_exceptions=True)
                )
            self.loop.close()

    def run_async(self, coro, timeout=None):
        """Helper to run async functions in tests."""
        if timeout is None:
            timeout = self.test_timeout
        return asyncio.wait_for(coro, timeout=timeout)

    def test_01_install_and_check_lemonade_sdk(self):
        """Test installing lemonade-sdk if needed and checking if it's available."""
        # First check if it's already available
        result = self.loop.run_until_complete(
            self.run_async(self.client.check_lemonade_sdk_available())
        )

        if not result:
            print("Installing lemonade-sdk...")
            # Install lemonade-sdk using pip
            install_result = self.loop.run_until_complete(
                self.run_async(
                    self.client.install_lemonade_sdk_package(),
                    timeout=self.setup_timeout,
                )
            )

            self.assertTrue(
                install_result["success"],
                f"lemonade-sdk installation should succeed: {install_result.get('message', '')}",
            )

            # Reset server state and refresh environment after installation
            print("Refreshing environment after installation...")
            self.client.reset_server_state()
            self.client.refresh_environment()

            # Wait a moment for environment changes to take effect
            import time

            time.sleep(2)

            # Verify it's now available
            result_after = self.loop.run_until_complete(
                self.run_async(self.client.check_lemonade_sdk_available())
            )
            self.assertTrue(
                result_after, "lemonade-sdk should be available after installation"
            )
        else:
            print("lemonade-sdk already available")

        # The final check - either it was already available or we installed it successfully
        final_result = result or result_after if not result else True
        self.assertTrue(final_result, "lemonade-sdk should be available")

    def test_02_check_lemonade_server_version(self):
        """Test checking lemonade server version."""
        result = self.loop.run_until_complete(
            self.run_async(self.client.check_lemonade_server_version())
        )

        self.assertIsInstance(result, dict)
        self.assertIn("installed", result)
        self.assertIn("version", result)
        self.assertIn("compatible", result)
        self.assertIn("required_version", result)

        self.assertTrue(
            result["compatible"],
            f"Server version {result['version']} should be compatible with minimum {result['required_version']}",
        )

    def test_03_start_lemonade_server(self):
        """Test starting lemonade server."""
        # Check if server is already running
        running = self.loop.run_until_complete(
            self.run_async(self.client.check_lemonade_server_running())
        )

        if not running:
            print("Starting lemonade server...")
            result = self.loop.run_until_complete(
                self.run_async(
                    self.client.start_lemonade_server(), timeout=self.setup_timeout
                )
            )

            self.assertTrue(
                result["success"],
                f"Server start should succeed: {result.get('message', '')}",
            )

            if result["success"]:
                self.__class__.server_started = True

                # Wait for server to be fully up
                print("Waiting for server to be ready...")
                max_wait = 120  # 2 minutes
                wait_start = time.time()

                while time.time() - wait_start < max_wait:
                    try:
                        api_online = self.loop.run_until_complete(
                            self.run_async(
                                self.client.check_lemonade_server_api(), timeout=10
                            )
                        )
                        if api_online:
                            print("Server API is ready!")
                            break
                    except Exception as e:
                        print(f"Waiting for server... ({e})")

                    time.sleep(5)
                else:
                    self.fail("Server did not become ready within timeout")

    def test_04_check_lemonade_server_api(self):
        """Test checking if lemonade server API is responding."""
        result = self.loop.run_until_complete(
            self.run_async(self.client.check_lemonade_server_api())
        )
        self.assertTrue(result, "Server API should be responding")

    def test_05_get_available_models(self):
        """Test getting available models from server."""
        models = self.loop.run_until_complete(
            self.run_async(self.client.get_available_models())
        )
        self.assertIsInstance(models, list, "Should return a list of models")
        # Note: List might be empty if no models are installed yet

    def test_06_install_model(self):
        """Test installing a model."""
        # First check if model is already installed
        check_result = self.loop.run_until_complete(
            self.run_async(self.client.check_model_installed(self.test_model))
        )

        if not check_result["installed"]:
            print(f"Installing test model: {self.test_model}")
            result = self.loop.run_until_complete(
                self.run_async(
                    self.client.install_model(self.test_model),
                    timeout=self.setup_timeout,
                )
            )

            self.assertTrue(
                result["success"],
                f"Model installation should succeed: {result.get('message', '')}",
            )

            # Verify model is now installed
            check_result_after = self.loop.run_until_complete(
                self.run_async(self.client.check_model_installed(self.test_model))
            )
            self.assertTrue(
                check_result_after["installed"],
                "Model should be installed after installation",
            )
        else:
            print(f"Test model {self.test_model} already installed")

    def test_07_check_model_installed(self):
        """Test checking if a model is installed."""
        result = self.loop.run_until_complete(
            self.run_async(self.client.check_model_installed(self.test_model))
        )

        self.assertIsInstance(result, dict)
        self.assertIn("installed", result)
        self.assertIn("model_name", result)
        self.assertEqual(result["model_name"], self.test_model)

    def test_08_load_model(self):
        """Test loading a model."""
        # Ensure model is installed first
        check_result = self.loop.run_until_complete(
            self.run_async(self.client.check_model_installed(self.test_model))
        )

        if check_result["installed"]:
            print(f"Loading test model: {self.test_model}")
            result = self.loop.run_until_complete(
                self.run_async(
                    self.client.load_model(self.test_model), timeout=self.setup_timeout
                )
            )

            self.assertTrue(
                result["success"],
                f"Model loading should succeed: {result.get('message', '')}",
            )
        else:
            self.skipTest(f"Test model {self.test_model} not installed")

    def test_09_check_model_loaded(self):
        """Test checking if a model is loaded."""
        result = self.loop.run_until_complete(
            self.run_async(self.client.check_model_loaded(self.test_model))
        )

        self.assertIsInstance(result, dict)
        self.assertIn("loaded", result)
        self.assertIn("model_name", result)
        self.assertIn("current_model", result)
        self.assertEqual(result["model_name"], self.test_model)

    def test_10_get_system_info(self):
        """Test getting system info from real server."""
        result = self.loop.run_until_complete(
            self.run_async(self.client.get_system_info())
        )

        if result is not None:
            self.assertIsInstance(result, dict)
            self.assertIn("OS Version", result)
            self.assertIn("Physical Memory", result)
            self.assertIn("devices", result)

            # Verify devices structure
            devices = result["devices"]
            self.assertIsInstance(devices, dict)

            # Should have at least CPU info
            if "cpu" in devices:
                self.assertIn("available", devices["cpu"])
        else:
            self.skipTest("System info API not available")

    def test_11_select_model_for_hardware(self):
        """Test hardware-based model selection with real system info."""
        result = self.loop.run_until_complete(
            self.run_async(self.client.select_model_for_hardware())
        )

        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)

        model_name, size_gb = result
        self.assertIsInstance(model_name, str)
        self.assertIsInstance(size_gb, (int, float))
        self.assertGreater(size_gb, 0)

        # Should be one of the known models from the MODELS dictionary
        from lemonade_arcade.lemonade_client import MODELS

        known_models = [model_info[0] for model_info in MODELS.values()]
        self.assertIn(model_name, known_models)

    def test_12_system_info_caching(self):
        """Test that system info caching works correctly."""
        import tempfile
        import os

        with tempfile.TemporaryDirectory() as temp_dir:
            # First call should fetch from API and cache
            result1 = self.loop.run_until_complete(
                self.run_async(self.client.get_system_info(cache_dir=temp_dir))
            )

            if result1 is not None:
                # Check that cache file was created
                cache_file = os.path.join(temp_dir, "lemonade_system_info_cache.json")
                self.assertTrue(os.path.exists(cache_file))

                # Second call should use cache - verify by checking API wasn't called again
                with patch("httpx.AsyncClient") as mock_client:
                    result2 = self.loop.run_until_complete(
                        self.run_async(self.client.get_system_info(cache_dir=temp_dir))
                    )

                    # API should not have been called since we're using cache
                    mock_client.assert_not_called()

                # Results should be identical
                self.assertEqual(result1, result2)
            else:
                self.skipTest("System info API not available")


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
for attr_name in dir(TestLemonadeClientIntegration):
    attr = getattr(TestLemonadeClientIntegration, attr_name)
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

    setattr(TestLemonadeClientIntegration, attr_name, make_sync_test(original_method))


if __name__ == "__main__":
    # Set up logging to see what's happening
    import logging

    logging.basicConfig(
        level=logging.DEBUG
    )  # Enable DEBUG level to see command details

    # Suppress noisy httpcore debug messages
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    # Run with verbose output
    unittest.main(verbosity=2)
