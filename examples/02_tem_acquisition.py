"""
Example 02 — TEM image acquisition and analysis.

Demonstrates:
- Checking microscope state before acquisition
- Acquiring a TEM image with custom parameters
- Interpreting the returned statistics

Run:
    GMS_SIMULATE=1 python examples/02_tem_acquisition.py
"""

import asyncio
import os
import sys

sys.path.insert(0, "src")
os.environ.setdefault("GMS_SIMULATE", "1")

from gms_mcp.client import run_agent


QUERY = """
1. Check the current microscope state.
2. Set the spot size to 3 if it isn't already.
3. Acquire a TEM image with 0.5 s exposure and 2× binning.
4. Report the image dimensions, pixel calibration in nm/pixel,
   and mean electron count.
"""


async def main():
    result = await run_agent(query=QUERY, model="qwen2.5:7b", verbose=True)
    print("\n─── Agent Response ───")
    print(result["answer"])


if __name__ == "__main__":
    asyncio.run(main())
