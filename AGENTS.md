# AGENTS.md - TTS Bot Development Guide

## Build, Lint, and Test Commands

### Installation
```bash
pip install -e .
pip install -r requirements.txt
```

### Running Tests
```bash
# Run all tests
pytest tests/ -v

# Run single test file
pytest tests/test_bot.py -v

# Run single test function
pytest tests/test_bot.py::TestTTSBot::test_import -v

# Run with coverage
pytest tests/ --cov=tts_bot --cov-report=term-missing
```

### Running the Bot
```bash
# Via entry point
tts-tg-bot

# Via Python module
python -m tts_bot.bot

# With debug mode
python -m tts_bot.bot --debug

# Run API server
python scripts/bot_api.py

# Run Kiro handler
python scripts/kiro_handler.py
```

### Linting and Formatting
```bash
# Check code style (flake8)
flake8 tts_bot/ tests/ --max-line-length=120

# Format code (black)
black tts_bot/ tests/

# Type checking (mypy)
mypy tts_bot/
```

---

## Code Style Guidelines

### Imports
- Use absolute imports: `from tts_bot import bot`
- Group imports: stdlib, third-party, local
- Alphabetize within groups
- Separate groups with a single blank line

```python
import asyncio
import json
import logging
from pathlib import Path

import aiohttp
import edge_tts
from telegram import Update
from telegram.ext import Application, ContextTypes

from tts_bot.bot import text_to_speech
```

### Formatting
- Line length: 120 characters max
- Indentation: 4 spaces (no tabs)
- Use Black formatter for automatic formatting
- Add blank lines between function definitions (2) and class definitions (2)
- No trailing whitespace

### Types
- Use type hints for function parameters and return values
- Prefer explicit types over `Any`
- Use `Optional[T]` instead of `T | None` for Python 3.8 compatibility

```python
async def text_to_speech(text: str, output_file: str, voice: str) -> None:
    """Convert text to speech using edge-tts."""
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_file)
```

### Naming Conventions
- **Modules**: lowercase with underscores (`bot_api.py`)
- **Classes**: PascalCase (`class MyBot:`)
- **Functions/variables**: snake_case (`def handle_message():`)
- **Constants**: UPPER_SNAKE_CASE (`TOKEN`, `DATA_DIR`)
- **Private methods**: prefix with `_` (`_private_method()`)
- **Instance variables**: snake_case with optional `_` prefix for private

### Docstrings and Comments
- Use triple double quotes for docstrings
- Write docstrings for all public functions and classes
- Use Chinese comments for Chinese context, English otherwise
- Keep comments concise and up-to-date with code

```python
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle text messages and convert to speech."""
    # 处理文字消息，转换为语音
    text = update.message.text
    ...
```

### Error Handling
- Use try/except blocks for operations that may fail
- Catch specific exceptions when possible
- Log errors with `logger.error(..., exc_info=True)` for stack traces
- Provide user-friendly error messages in Telegram responses

```python
try:
    await text_to_speech(text, output_file, voice)
except Exception as e:
    logger.error(f"TTS processing failed: {e}", exc_info=True)
    await msg.edit_text(f"❌ Generation failed: {str(e)}")
```

### Async/Await Patterns
- Use `async def` for functions called within async contexts
- Use `AsyncMock` in tests for async functions
- Avoid blocking calls in async functions; use async alternatives

### Logging
- Use module-level logger: `logger = logging.getLogger(__name__)`
- Log levels: `DEBUG` for details, `INFO` for actions, `WARNING` for issues, `ERROR` for failures
- Include relevant context in log messages (user_id, message_id, etc.)

```python
logger.info(f"Received text message: user_id={user_id}, text='{text[:50]}...'")
logger.debug(f"TTS conversion complete: {output_file}")
```

### File Paths and Configuration
- Use `os.path.expanduser()` for user paths
- Use `os.path.join()` for path concatenation
- Create directories with `os.makedirs(path, exist_ok=True)`
- Read tokens from `~/data/tts-tg-bot/token.txt`

### Project Structure
```
tts-bot/
├── tts_bot/          # Main package
│   ├── __init__.py
│   └── bot.py        # Main bot logic
├── scripts/          # Utility scripts
│   ├── bot_api.py    # HTTP API server
│   ├── kiro_handler.py
│   └── ...
├── tests/            # Test suite
│   ├── test_bot.py
│   └── test_integration.py
├── pyproject.toml    # Project config
├── requirements.txt  # Dependencies
└── README.md
```

### Testing
- Place tests in `tests/` directory
- Test file naming: `test_<module>.py`
- Use `unittest.TestCase` or pytest fixtures
- Mock external services (edge_tts, Telegram API)
- Use `sys.path.insert()` for imports when needed

```python
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
```

### Git Commit Messages
- Use conventional commits format: `feat:`, `fix:`, `docs:`, `refactor:`
- Write in English for consistency
- Reference issues if applicable
