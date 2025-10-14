# Pylinac Bulk CBCT Analysis

This project aims to build a toolchain that can discover Cone Beam CT (CBCT) studies, analyse them in bulk with [Pylinac](https://pylinac.readthedocs.io/), and aggregate the outcomes for downstream reporting.

## Current Status

Task 1 focuses on discovering study directories and producing an inventory that can be consumed by later analysis steps.

### Features

- Command line interface for scanning a root directory for CBCT studies.
- Configurable file extensions and optional symlink following.
- JSON inventory output listing discovered studies and metadata (paths, file counts, detected extensions).
- Logging to facilitate troubleshooting missing or malformed datasets.

## Usage

Install the project in editable mode (preferably in a virtual environment) and run the CLI:

```bash
pip install -e .[dev]
pylinac-bulkcbct-scan /path/to/cbct/root --output inventory.json
```

The command will recurse through the supplied root directory and produce a JSON inventory that includes all study directories discovered. If `--output` is omitted, the inventory is printed to standard output.

### Running without installation

For quick experiments you can invoke the CLI module directly without installing the project:

```bash
python src/pylinac_bulkcbct/cli.py /path/to/cbct/root --output inventory.json
```

This mode adjusts `sys.path` automatically so the module imports resolve even when the package has not been installed yet.

## Development

Run the unit tests with:

```bash
pytest
```
