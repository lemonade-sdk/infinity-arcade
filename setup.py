#!/usr/bin/env python3

from setuptools import setup, find_packages

setup(
    name="lemonade-arcade",
    version="0.1.0",
    description="AI-powered game generator and arcade using Lemonade Server",
    author="Lemonade SDK",
    packages=find_packages(),
    install_requires=[
        "fastapi>=0.104.0",
        "uvicorn>=0.24.0",
        "pygame>=2.5.0",
        "httpx>=0.25.0",
        "jinja2>=3.1.0",
        "python-multipart>=0.0.6",
    ],
    extras_require={"dev": ["lemonade-sdk>=8.1.3"]},
    entry_points={
        "console_scripts": [
            "lemonade-arcade=lemonade_arcade.cli:main",
        ],
        "gui_scripts": [
            "lemonade-arcade-gui=lemonade_arcade.main:main",
        ],
    },
    python_requires=">=3.8",
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
)

# Copyright (c) 2025 AMD
