#!/usr/bin/env python3
"""
UNI - Universal AI Platform

Entry point for `python -m uni`.
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from uni.agent import Agent
from uni.config import load_config


async def main():
    """Main entry point."""
    config_path = None
    initial_command = None

    # Parse args
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] in ("-c", "--config"):
            config_path = args[i + 1]
            i += 2
        elif args[i] in ("-h", "--help"):
            print("UNI - Universal AI Platform")
            print("Usage: python -m uni [options] [command]")
            print("Options:")
            print("  -c, --config PATH   Config file path")
            print("  -h, --help          Show help")
            return
        else:
            initial_command = " ".join(args[i:])
            break

    # Load config
    config = load_config(config_path) if config_path else load_config()

    # Create and run agent
    agent = Agent(config)

    try:
        await agent.initialize()
        await agent.run(initial_command)
    except KeyboardInterrupt:
        print("\n⏹️ Interrupted")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await agent.shutdown()


if __name__ == "__main__":
    asyncio.run(main())