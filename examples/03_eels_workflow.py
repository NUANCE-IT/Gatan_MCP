"""
Example 03 — EELS spectrum acquisition workflow.

Demonstrates:
- Switching to EELS mode
- Acquiring a zero-loss spectrum and a core-loss spectrum
- ZLP position and energy calibration reporting

Run:
    GMS_SIMULATE=1 python examples/03_eels_workflow.py
"""

import asyncio
import os
import sys

sys.path.insert(0, "src")
os.environ.setdefault("GMS_SIMULATE", "1")

from gms_mcp.client import run_agent


QUERY = """
Perform the following EELS acquisition workflow:

1. First acquire a zero-loss spectrum (energy offset = 0 eV,
   slit width = 5 eV, 1 s exposure) and report the ZLP position
   in eV and the dispersion in eV/channel.

2. Then acquire a Ti L-edge spectrum (energy offset = 400 eV,
   dispersion index = 1 for 0.25 eV/channel, slit out, 2 s exposure).
   Report the energy range covered and whether the Ti L2,3 edge
   at ~460 eV falls within the window.
"""


async def main():
    result = await run_agent(query=QUERY, model="qwen2.5:7b", verbose=True)
    print("\n─── Agent Response ───")
    print(result["answer"])


if __name__ == "__main__":
    asyncio.run(main())
