"""
Example 01 — Basic state query in simulation mode.

Run:
    GMS_SIMULATE=1 python examples/01_basic_query.py
"""

import asyncio
import os
import sys

sys.path.insert(0, "src")
os.environ.setdefault("GMS_SIMULATE", "1")

from gms_mcp.client import run_agent


async def main():
    result = await run_agent(
        query="What is the current accelerating voltage and stage position?",
        model="qwen2.5:7b",
        verbose=True,
    )
    print("\n─── Agent Response ───")
    print(result["answer"])
    print(f"\nTools called: {[tc['tool'] for tc in result['tool_calls']]}")


if __name__ == "__main__":
    asyncio.run(main())
