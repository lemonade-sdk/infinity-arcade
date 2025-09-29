#!/usr/bin/env python3

from setuptools import setup

with open("src/infinity_arcade/version.py", encoding="utf-8") as fp:
    version = fp.read().split('"')[1]

setup(
    name="infinity-arcade",
    version=version,
    description="AI-powered game generator and arcade using Lemonade Server",
    author="Lemonade SDK",
    author_email="lemonade@amd.com",
    packages=["infinity_arcade", "infinity_arcade.builtin_games"],
    package_dir={"": "src"},
    install_requires=[
        "fastapi>=0.104.0",
        "uvicorn>=0.24.0",
        "pygame>=2.5.0",
        "httpx>=0.25.0",
        "jinja2>=3.1.0",
        "python-multipart>=0.0.6",
        "openai>=1.0.0",
    ],
    entry_points={
        "console_scripts": [
            "infinity-arcade=infinity_arcade.cli:main",
        ],
        "gui_scripts": [
            "infinity-arcade-gui=infinity_arcade.main:main",
        ],
    },
    python_requires=">=3.8",
    package_data={
        "infinity_arcade": ["static/**/*", "templates/**/*"],
    },
    long_description=open("README.md", "r", encoding="utf-8").read(),
    long_description_content_type="text/markdown",
)

# Copyright (c) 2025 AMD
