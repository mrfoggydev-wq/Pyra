"""Runtime support for importing Python-compatible .pyra modules."""

import importlib.machinery
import sys

_SUFFIXES = (".fm", ".pyra")


def install_importer() -> None:
    """Teach Python's normal import system to load .fm and .pyra source files."""
    missing_suffixes = [
        suffix for suffix in _SUFFIXES if suffix not in importlib.machinery.SOURCE_SUFFIXES
    ]
    if not missing_suffixes:
        return

    importlib.machinery.SOURCE_SUFFIXES.extend(missing_suffixes)
    finder = importlib.machinery.FileFinder.path_hook(
        (importlib.machinery.ExtensionFileLoader, importlib.machinery.EXTENSION_SUFFIXES),
        (importlib.machinery.SourceFileLoader, importlib.machinery.SOURCE_SUFFIXES),
        (importlib.machinery.SourcelessFileLoader, importlib.machinery.BYTECODE_SUFFIXES),
    )
    sys.path_hooks.insert(0, finder)
    sys.path_importer_cache.clear()