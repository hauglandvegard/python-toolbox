# Default recipe: show available commands
default:
   @just --list

# Install the package in editable mode with dev dependencies
install:
   uv pip install -e ".[dev]"

# Format code using ruff
format:
    uv run ruff format .

# Run linting checks and type checking
lint:
    uv run ruff check .
    uv run mypy src

# Run all tests
test:
    uv run pytest

# Run all quality checks (format, lint, type check, and test)
check: format lint test

# Build the distribution packages (wheel and sdist)
build:
    uv run python -m build

# Clean up build artifacts and caches
clean:
    rm -rf build/ dist/ *.egg-info/ .pytest_cache/ .mypy_cache/ .ruff_cache/
