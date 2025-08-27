#!/usr/bin/env python3
"""
LemonadeClient Integration Example

Complete example of integrating LemonadeClient into an application.
"""

import asyncio
from openai import AsyncOpenAI

from lemonade_arcade.lemonade_client import LemonadeClient


# Run everything in an async context
async def main():
    client = LemonadeClient()
    required_model = "Qwen3-0.6B-GGUF"

    # Check installation
    version_info = await client.check_lemonade_server_version()
    if not version_info["installed"] or not version_info["compatible"]:
        print("Installing lemonade-server...")
        result = await client.download_and_install_lemonade_server()
        if not result["success"]:
            raise Exception(f"Installation failed: {result['message']}")
        client.refresh_environment()
        client.reset_server_state()

    # Start server
    if not await client.check_lemonade_server_running():
        print("Starting server...")
        result = await client.start_lemonade_server()
        if not result["success"]:
            raise Exception(f"Server start failed: {result['message']}")
        await asyncio.sleep(3)  # Wait for startup

    # Verify API
    if not await client.check_lemonade_server_api():
        raise Exception("Server API not responding")

    # Setup model
    model_status = await client.check_model_installed(required_model)
    if not model_status["installed"]:
        print(f"Installing model {required_model}...")
        result = await client.install_model(required_model)
        if not result["success"]:
            raise Exception(f"Model installation failed: {result['message']}")

    load_status = await client.check_model_loaded(required_model)
    if not load_status["loaded"]:
        print(f"Loading model {required_model}...")
        result = await client.load_model(required_model)
        if not result["success"]:
            raise Exception(f"Model loading failed: {result['message']}")

    print(f"✅ lemonade-server ready at {client.url}")

    # Make a chat completion request using OpenAI library
    openai_client = AsyncOpenAI(
        base_url=f"{client.url}/api/v1",
        api_key="dummy",  # lemonade-server doesn't require a real API key
    )

    response = await openai_client.chat.completions.create(
        model=required_model,
        messages=[
            {"role": "user", "content": "Hello! Please respond with 'Hello there!'"}
        ],
        max_tokens=50,
        temperature=0.1,
    )

    print(f"Response: {response.choices[0].message.content}")


asyncio.run(main())
