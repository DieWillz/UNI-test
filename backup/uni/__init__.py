"""
UNI - Universal AI Platform

Lazy imports to avoid external dependency issues at import time.
"""

__version__ = "0.1.0"
__author__ = "UNI Team"

# Export main public API - these will be loaded on first access
__all__ = ["Agent", "Config", "load_config", "__version__"]


def __getattr__(name: str):
    if name == "Agent":
        from .agent import Agent
        return Agent
    if name == "Config":
        from .config import Config
        return Config
    if name == "load_config":
        from .config import load_config
        return load_config
    raise AttributeError(f"module 'uni' has no attribute '{name}'")