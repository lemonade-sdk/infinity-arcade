# LemonadeClient API Reference

The `LemonadeClient` class provides a comprehensive interface for integrating with lemonade-server in your applications. It handles installation, configuration, server management, and model operations with cross-platform compatibility.

## Suggested Workflow

Here's the typical sequence of API calls for setting up a lemonade-server-based application:

### 1. Initial Setup and Environment Check
```python
from lemonade_arcade.lemonade_client import LemonadeClient

client = LemonadeClient()

# Check deployment environment
is_pyinstaller = client.is_pyinstaller_environment()

# Check if SDK is available (for development environments)
sdk_available = await client.check_lemonade_sdk_available()
```

### 2. Installation Status Check
```python
# Check if lemonade-server is installed and compatible
version_info = await client.check_lemonade_server_version()
if not version_info["installed"] or not version_info["compatible"]:
    # Need to install or upgrade
    result = await client.download_and_install_lemonade_server()
    if result["success"]:
        # Refresh environment after installation
        client.refresh_environment()
        client.reset_server_state()
```

### 3. Server Management
```python
# Check if server is running
is_running = await client.check_lemonade_server_running()
if not is_running:
    # Start the server
    start_result = await client.start_lemonade_server()
    
# Verify API connectivity
api_online = await client.check_lemonade_server_api()
```

### 4. Model Management

**Option A: Automatic Hardware-Based Selection**
```python
# Select optimal model based on hardware (optional)
model_name, size_gb = await client.select_model_for_hardware()
print(f"Selected model: {model_name} ({size_gb} GB)")
```

**Option B: Manual Model Selection**
```python
# Or specify your own model directly
model_name = "Qwen3-4B-Instruct-2507-GGUF"  # Your choice
print(f"Using custom model: {model_name}")
```

**Common Steps (regardless of selection method):**
```python
# Check if model is installed
model_status = await client.check_model_installed(model_name)
if not model_status["installed"]:
    # Install the model
    install_result = await client.install_model(model_name)

# Check if model is loaded
load_status = await client.check_model_loaded(model_name)
if not load_status["loaded"]:
    # Load the model
    load_result = await client.load_model(model_name)
```

### 5. Ready for Inference
Once the above steps complete successfully, your application can make inference requests to `client.url` (default: `http://localhost:8000`) using the OpenAI-compatible API.

---

## API Reference

### Environment and System Detection

#### `is_pyinstaller_environment()`
Check if the application is running in a PyInstaller bundle environment.

**When to use:** Determine installation method preferences or adjust behavior based on deployment type. PyInstaller environments typically prefer installer-based server installation over pip.

**Returns:** `bool` - True if running in PyInstaller bundle, False otherwise

**Example:**
```python
if client.is_pyinstaller_environment():
    print("Running as packaged executable")
    # Prefer installer-based installation
else:
    print("Running in development environment") 
    # Can use pip installation
```

---

#### `find_lemonade_server_paths()`
Find lemonade-server installation paths by scanning the system PATH.

**When to use:** Discover where lemonade-server binaries are installed on the system. Helpful for apps that need to verify installation locations or debug path issues.

**Returns:** `List[str]` - List of directory paths containing lemonade-server installations

**Example:**
```python
paths = client.find_lemonade_server_paths()
print(f"Found lemonade-server in: {paths}")
```

---

#### `refresh_environment()`
Refresh environment variables from the system registry (Windows only).

**When to use:** After installing lemonade-server to pick up newly added PATH entries without requiring an application restart. Essential for apps that install lemonade-server programmatically and need immediate access to the commands.

**Example:**
```python
# After installation
await client.download_and_install_lemonade_server()
client.refresh_environment()  # Pick up new PATH entries
client.reset_server_state()   # Clear cached commands
```

---

#### `reset_server_state()`
Reset cached server state after installation changes or configuration updates.

**When to use:** Call this when you've installed/updated lemonade-server or changed system configuration to ensure the client rediscovers server commands and processes. Essential after installation operations to avoid using stale cached paths.

**Example:**
```python
# After any installation or configuration change
client.reset_server_state()
```

---

### Core Server Operations

#### `execute_lemonade_server_command(args, timeout=10, use_popen=False, stdout_file=None, stderr_file=None)`
Execute lemonade-server commands using the best available method for the system.

**When to use:** As the primary interface for running any lemonade-server command. The method automatically tries different installation methods (pip, installer, dev) and caches the successful command for future use. Essential for cross-platform compatibility.

**Parameters:**
- `args: List[str]` - Command arguments to pass to lemonade-server (e.g., `["--version"]`, `["serve"]`)
- `timeout: int` - Maximum seconds to wait for command completion (ignored for background processes)
- `use_popen: bool` - True for background processes that shouldn't block, False for commands with output
- `stdout_file` - File handle to redirect standard output (only with use_popen=True)
- `stderr_file` - File handle to redirect error output (only with use_popen=True)

**Returns:** `subprocess.CompletedProcess` for regular commands, `subprocess.Popen` for background processes, or `None` if all command attempts failed

**Example:**
```python
# Check version
result = await client.execute_lemonade_server_command(["--version"])
if result:
    print(f"Version: {result.stdout}")

# Start server in background
process = await client.execute_lemonade_server_command(
    ["serve"], 
    use_popen=True
)
```

---

### Installation and Setup

#### `check_lemonade_sdk_available()`
Check if the lemonade-sdk Python package is installed and importable.

**When to use:** Determine if pip-based installation is available before attempting SDK-based operations. Helpful for showing installation options to users or choosing between different installation methods.

**Returns:** `bool` - True if lemonade-sdk package can be imported, False otherwise

**Example:**
```python
if await client.check_lemonade_sdk_available():
    print("Can use lemonade-server-dev command")
else:
    print("Need to install via pip or use installer")
```

---

#### `check_lemonade_server_version()`
Check lemonade-server installation status and version compatibility.

**When to use:** Verify that lemonade-server is installed and meets minimum version requirements before attempting to use server features. Essential for displaying installation status and guiding users through setup.

**Returns:** `dict` with keys:
- `installed: bool` - Whether lemonade-server is found
- `version: str` - Version string or None
- `compatible: bool` - Whether version meets minimum requirements  
- `required_version: str` - Minimum required version

**Example:**
```python
version_info = await client.check_lemonade_server_version()
if version_info["installed"] and version_info["compatible"]:
    print(f"lemonade-server {version_info['version']} is ready")
else:
    print(f"Need version {version_info['required_version']} or higher")
```

---

#### `install_lemonade_sdk_package()`
Install the lemonade-sdk Python package using pip.

**When to use:** Install lemonade-server via pip when in development environments or when the SDK approach is preferred. Provides access to lemonade-server-dev command after successful installation.

**Returns:** `dict` with keys:
- `success: bool` - Whether installation succeeded
- `message: str` - Success message or error details

**Example:**
```python
result = await client.install_lemonade_sdk_package()
if result["success"]:
    print("SDK installed successfully")
    client.refresh_environment()
else:
    print(f"Installation failed: {result['message']}")
```

---

#### `download_and_install_lemonade_server()`
Download and install lemonade-server using the best method for the environment.

**When to use:** As the primary installation method. Automatically chooses between pip installation (development environments) or executable installer (PyInstaller bundles). Handles the complete installation process including download and setup.

**Returns:** `dict` with keys:
- `success: bool` - Whether installation succeeded
- `message: str` - Status message or error details
- `interactive: bool` (optional) - Whether installer requires user interaction
- `github_link: str` (optional) - Link for manual installation if automated fails

**Example:**
```python
result = await client.download_and_install_lemonade_server()
if result["success"]:
    print("Installation completed")
    if result.get("interactive"):
        print("Please complete the installer UI")
    client.refresh_environment()
    client.reset_server_state()
else:
    print(f"Installation failed: {result['message']}")
    if "github_link" in result:
        print(f"Manual installation: {result['github_link']}")
```

---

### Server Status and Management

#### `check_lemonade_server_running()`
Check if the lemonade-server process is currently running.

**When to use:** Determine server status before attempting operations that require a running server. Helps decide whether to start the server or proceed with API calls.

**Returns:** `bool` - True if server process is running, False otherwise

**Example:**
```python
if await client.check_lemonade_server_running():
    print("Server is running")
else:
    print("Need to start server")
    await client.start_lemonade_server()
```

---

#### `start_lemonade_server()`
Start the lemonade-server process in the background.

**When to use:** Launch the server when it's not running and your app needs server functionality. The server runs in a separate process and the method tracks the process to avoid multiple instances.

**Returns:** `dict` with keys:
- `success: bool` - Whether server started successfully
- `message: str` - Status message or error details

**Example:**
```python
result = await client.start_lemonade_server()
if result["success"]:
    print("Server started successfully")
    # Wait a moment for startup
    await asyncio.sleep(2)
else:
    print(f"Failed to start server: {result['message']}")
```

---

#### `check_lemonade_server_api()`
Check if the lemonade-server API is responding to requests.

**When to use:** Verify that the server is not only running but also accepting API connections. More reliable than process checks for determining if the server is ready to handle requests.

**Returns:** `bool` - True if server API is responding, False otherwise

**Example:**
```python
if await client.check_lemonade_server_api():
    print("API is ready for requests")
    # Can now make inference calls
else:
    print("API not responding, check server status")
```

---

### Model Management

#### `get_available_models()`
Retrieve the list of models available on the lemonade-server.

**When to use:** Discover which models are installed and available for use. Helpful for displaying model options to users or verifying that required models are available before attempting to use them.

**Returns:** `List[str]` - List of model names/IDs available on the server, empty list if none found

**Example:**
```python
models = await client.get_available_models()
print(f"Available models: {models}")
for model in models:
    print(f"  - {model}")
```

---

#### `check_model_installed(model)`
Check if a specific model is installed on the server.

**When to use:** Verify model availability before attempting to load or use a model. Essential for apps that depend on specific models to function properly.

**Parameters:**
- `model: str` - The model name/ID to check for (e.g., "Qwen3-0.6B-GGUF")

**Returns:** `dict` with keys:
- `installed: bool` - Whether the model is available
- `model_name: str` - The requested model name

**Example:**
```python
required_model = "Qwen3-0.6B-GGUF"
status = await client.check_model_installed(required_model)
if status["installed"]:
    print(f"Model {required_model} is available")
else:
    print(f"Need to install {required_model}")
    await client.install_model(required_model)
```

---

#### `check_model_loaded(model)`
Check if a specific model is currently loaded and ready for inference.

**When to use:** Verify that a model is loaded before making inference requests. Models must be loaded before they can be used for chat completions or other inference operations.

**Parameters:**
- `model: str` - The model name/ID to check (e.g., "Qwen3-0.6B-GGUF")

**Returns:** `dict` with keys:
- `loaded: bool` - Whether the model is currently loaded
- `model_name: str` - The requested model name
- `current_model: str` - Name of currently loaded model (may be different)

**Example:**
```python
required_model = "Qwen3-0.6B-GGUF"
status = await client.check_model_loaded(required_model)
if status["loaded"]:
    print(f"Model {required_model} is ready for inference")
else:
    current = status["current_model"]
    print(f"Current model: {current}, need to load {required_model}")
    await client.load_model(required_model)
```

---

#### `install_model(model)`
Download and install a model on the lemonade-server.

**When to use:** Install models that your app requires but aren't currently available on the server. The installation process may take several minutes for large models and requires an active internet connection.

**Parameters:**
- `model: str` - The model name/ID to install (e.g., "Qwen3-0.6B-GGUF")

**Returns:** `dict` with keys:
- `success: bool` - Whether installation succeeded
- `message: str` - Success message or error details

**Example:**
```python
model_name = "Qwen3-0.6B-GGUF"
print(f"Installing {model_name}...")
result = await client.install_model(model_name)
if result["success"]:
    print("Model installed successfully")
else:
    print(f"Installation failed: {result['message']}")
```

---

#### `load_model(model)`
Load a model into memory for inference operations.

**When to use:** Prepare an installed model for use. Models must be loaded before they can handle chat completions or other inference requests. Only one model can be loaded at a time.

**Parameters:**
- `model: str` - The model name/ID to load (e.g., "Qwen3-0.6B-GGUF")

**Returns:** `dict` with keys:
- `success: bool` - Whether model loaded successfully
- `message: str` - Success message or error details

**Example:**
```python
model_name = "Qwen3-0.6B-GGUF"
print(f"Loading {model_name}...")
result = await client.load_model(model_name)
if result["success"]:
    print("Model loaded and ready for inference")
    # Can now make API calls to client.url
else:
    print(f"Loading failed: {result['message']}")
```

---

### Hardware-Based Model Selection

#### `get_system_info(cache_dir=None, cache_duration_hours=None)`
Get system information from lemonade-server with caching support.

**When to use:** Retrieve detailed hardware information including CPU, GPU, NPU, and memory specs. The system-info endpoint is slow, so results are cached by default. Cache never expires unless cache_duration_hours is explicitly set.

**Parameters:**
- `cache_dir: Optional[str]` - Directory to store cache file (defaults to ~/.cache/lemonade)
- `cache_duration_hours: Optional[int]` - Hours to keep cached data (None = never expire, default)

**Returns:** `dict` - System information from server, or None if unavailable

**Example:**
```python
# Get system info with default caching (never expires)
system_info = await client.get_system_info()
if system_info:
    print(f"RAM: {system_info['Physical Memory']}")
    print(f"CPU: {system_info['Processor']}")

# Get system info with 24-hour cache expiry
system_info = await client.get_system_info(cache_duration_hours=24)

# Use custom cache directory
system_info = await client.get_system_info(cache_dir="/path/to/cache")
```

---

#### `select_model_for_hardware(system_info=None, cache_dir=None)` *(Optional)*
Select the optimal model based on hardware capabilities.

**When to use:** This method is **optional** - use it when you want automatic hardware-based model selection. The selection logic prioritizes larger models for high-end hardware and falls back to smaller models for resource-constrained systems. Developers can skip this method entirely and specify their own model names directly in other LemonadeClient methods.

**Selection Logic:**
- **64GB+ RAM or discrete GPU with 16GB+ VRAM**: `Qwen3-Coder-30B-A3B-Instruct-GGUF`
- **AMD NPU available**: `Qwen-2.5-7B-Instruct-Hybrid`
- **Default/fallback**: `Qwen3-4B-Instruct-2507-GGUF`

**Parameters:**
- `system_info: Optional[Dict]` - Pre-fetched system info (if None, will fetch automatically)
- `cache_dir: Optional[str]` - Directory for caching system info (passed to get_system_info)

**Returns:** `tuple[str, float]` - (model_name, size_gb) based on hardware capabilities

**Example:**
```python
# Automatic model selection (optional)
model_name, size_gb = await client.select_model_for_hardware()
print(f"Recommended model: {model_name} ({size_gb} GB)")

# Use pre-fetched system info
system_info = await client.get_system_info()
model_name, size_gb = await client.select_model_for_hardware(system_info=system_info)

# Use custom cache directory
model_name, size_gb = await client.select_model_for_hardware(cache_dir="/path/to/cache")

# Alternative: Skip hardware detection and use your own model
model_name = "My-Custom-Model"
# Then proceed with check_model_installed(), install_model(), etc.
```

---

## Error Handling

Most methods return dictionaries with `success` and `message` keys for operations, or boolean values for status checks. Always check return values:

```python
# For operations
result = await client.start_lemonade_server()
if not result["success"]:
    print(f"Operation failed: {result['message']}")
    return

# For status checks  
if not await client.check_lemonade_server_api():
    print("Server API is not responding")
    return
```

## Integration Example

For a complete, runnable example of integrating LemonadeClient into an application, see:

**[examples/lemonade_client_integration_example.py](../examples/lemonade_client_integration_example.py)**

This example demonstrates:
- Complete setup workflow from installation to ready-for-inference
- Error handling and status checking
- Model installation and loading
- Basic inference testing
- Proper logging and user feedback

You can run the example directly to test your LemonadeClient setup:

```bash
python lemonade-arcade/examples/lemonade_client_integration_example.py
```

The example includes comprehensive error handling and step-by-step progress reporting, making it suitable for both learning and as a starting point for your own integration.
