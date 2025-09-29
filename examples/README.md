# LemonadeClient Examples

This directory contains practical examples demonstrating how to use the LemonadeClient class in your applications.

## Available Examples

### [lemonade_client_integration_example.py](lemonade_client_integration_example.py)

A comprehensive example showing the complete workflow for integrating LemonadeClient into an application:

- ✅ **Installation checking** - Verify lemonade-server is installed and compatible
- 🚀 **Server management** - Start and verify server status
- 🤖 **Model operations** - Install, load, and verify model availability
- 🧪 **Inference testing** - Basic API connectivity and inference test
- 📝 **Error handling** - Proper exception handling and user feedback

**Usage:**
```bash
python infinity-arcade/examples/lemonade_client_integration_example.py
```

This example uses the `Qwen3-0.6B-GGUF` model as it's lightweight and good for testing. You can modify the `required_model` variable to use different models as needed.

## Running Examples

All examples are standalone Python scripts that can be run directly. They include proper error handling and progress reporting, making them suitable for:

- Learning how to integrate LemonadeClient
- Testing your lemonade-server setup
- Starting point for your own applications
- CI/CD pipeline validation

## Adding New Examples

When adding new examples:

1. Include comprehensive docstrings and comments
2. Add proper error handling with informative messages
3. Use realistic model names and parameters
4. Include progress reporting for long-running operations
5. Update this README with a description of the new example
