#!/usr/bin/env python3
"""Setup script for tts-bot"""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="tts-tg-bot",
    version="1.0.1",
    author="TTS Bot Team",
    author_email="dev@example.com",
    description="Telegram bot for text-to-speech and speech-to-text conversion",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/tts-bot",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Topic :: Communications :: Chat",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
    python_requires=">=3.8",
    install_requires=[
        "python-telegram-bot>=20.0",
        "edge-tts>=6.0.0",
        "SpeechRecognition>=3.10.0",
        "pydub>=0.25.0",
    ],
    entry_points={
        "console_scripts": [
            "tts-tg-bot=tts_bot.bot:main",
        ],
    },
)
