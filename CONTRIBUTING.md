# Contributing to Remote OpenCode MCP Server

Thank you for your interest in contributing!

## How to Contribute

### Reporting Issues

- Search existing issues before creating a new one
- Use issue templates if available
- Include reproduction steps and expected behavior

### Pull Requests

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Make your changes
4. Run tests and linting
5. Commit with clear messages: `git commit -m 'Add feature: description'`
6. Push to your fork: `git push origin feature/your-feature`
7. Open a Pull Request

### Code Style

- Follow PEP 8
- Run `ruff check .` for linting
- Run `mypy .` for type checking

### Development Setup

```bash
# Install dependencies
uv sync

# Install dev dependencies
uv sync --extra dev

# Run linting
uv run ruff check .

# Run type checking
uv run mypy .
```

## Questions?

Feel free to open an issue for questions.
