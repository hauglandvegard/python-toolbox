# python-toolbox

Personal Python utility library: scraping, string manipulation, IO, datetime, and other general-purpose helpers. Designed to be imported into other projects as a single, lightweight dependency.

Python 3.14+ • MIT license • src layout • hatchling build backend

## Install

From GitHub (recommended for downstream projects):

```bash
pip install "git+https://github.com/hauglandvegard/python-toolbox.git"
```

Or pin to a tag/commit:

```bash
pip install "git+https://github.com/hauglandvegard/python-toolbox.git@v0.0.1"
```

In a `pyproject.toml`:

```toml
dependencies = [
    "python-toolbox @ git+https://github.com/hauglandvegard/python-toolbox.git",
]
```

## Usage

Each utility area is a flat subpackage under `toolbox.*`. Public API is hoisted in each subpackage's `__init__.py`:

```python
from toolbox.scraper import scrape_links     # web scraping helpers
from toolbox.strings import slugify          # string utilities
from toolbox.io import read_json             # IO helpers
```

The library does not configure logging. Attach handlers in your application — `toolbox` modules log via `logging.getLogger(__name__)` and ship a `NullHandler` at the package root.

## Development

Requires [`uv`](https://github.com/astral-sh/uv) and [`just`](https://github.com/casey/just).

```bash
just install   # editable install with dev extras
just check     # format, lint (ruff + mypy), test
just test      # pytest only
just build     # wheel + sdist
```

## License

MIT — see [LICENSE](LICENSE).
