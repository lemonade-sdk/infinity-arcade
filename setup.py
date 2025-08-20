#!/usr/bin/env python3

from setuptools import setup

with open("lemonade_arcade/version.py", encoding="utf-8") as fp:
    version = fp.read().split('"')[1]

setup(
    name="lemonade-arcade",
    version=version,
    description="AI-powered game generator and arcade using Lemonade Server",
    author="Lemonade SDK",
    author_email="lemonade@amd.com",
    packages=["lemonade_arcade", "lemonade_arcade.builtin_games"],
    install_requires=[
        "fastapi>=0.104.0",
        "uvicorn>=0.24.0",
        "pygame>=2.5.0",
        "httpx>=0.25.0",
        "jinja2>=3.1.0",
        "python-multipart>=0.0.6",
    ],
    entry_points={
        "console_scripts": [
            "lemonade-arcade=lemonade_arcade.cli:main",
        ],
        "gui_scripts": [
            "lemonade-arcade-gui=lemonade_arcade.main:main",
        ],
    },
    python_requires=">=3.8",
    package_data={
        "lemonade_arcade": ["static/**/*", "templates/**/*"],
    },
    long_description=open("README.md", "r", encoding="utf-8").read(),
    long_description_content_type="text/markdown",
)

# Copyright (c) 2025 AMD
