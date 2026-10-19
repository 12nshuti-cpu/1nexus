"""NEXUS local model metadata and helpers."""

from pathlib import Path

BASE_MODEL = "llama3.1:8b"
NEXUS_MODEL = "nexus:latest"
MODELFILE_NAME = "Modelfile"
MODELFILE_PATH = Path(__file__).resolve().parent / MODELFILE_NAME

__all__ = [
    "BASE_MODEL",
    "NEXUS_MODEL",
    "MODELFILE_NAME",
    "MODELFILE_PATH",
]
