# Arcturus Session 16 Backend Share

This directory contains the backend code for the Arcturus platform, snapshot for Session 16.

## Contents

- `app.py`: Main FastAPI application entry point.
- `api.py`: API routes definition.
- `core/`: Core logic including the `Loop`, `AgentRunner`, `Memory`, and `CircuitBreaker`.
- `agents/`: Agent definitions (`Planner`, `Coder`, `Distiller`, etc.).
- `remme/`: The REMME (Re-Member-Me) user modeling and personalization system (5-Hub Architecture).
- `config/`: Configuration files (settings, defaults).
- `mcp_servers/`: Model Context Protocol servers.
- `routers/`: FastAPI routers for different endpoints.
- `tools/`: Utility tools and sandbox implementation.
- `prompts/`: System prompts for agents.
- `benchmarks/`: GAIA benchmarks and runners.
- `scripts/`: Utility scripts.
- `shared/`: Shared state and utilities.
- `memory/`: Memory context and store implementations.
- `ui/`: Backend visualization utilities (e.g., `visualizer.py` using Rich).
- `tests/`: Unit and integration tests.

## Setup

1.  Ensure Python 3.10+ is installed.
2.  Install dependencies using `uv` or `pip`:
    ```bash
    pip install -r pyproject.toml  # or closest equivalent
    # OR
    uv sync
    ```
    (Note: `pyproject.toml` and `uv.lock` are included in the root of this share).

## Usage

Run the backend server:

```bash
uv run app.py
```

## Notes

- This package excludes UI frontend code (`platform-frontend`) and user data (`data/`, `Notes/`).
- `config/settings.json` serves as the primary configuration.
