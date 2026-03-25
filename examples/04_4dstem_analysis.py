"""
Example 04 — 4D-STEM acquisition and virtual detector analysis.

Demonstrates:
- Acquiring a 4D-STEM dataset
- Computing a virtual HAADF image (annular dark-field)
- Computing a differential phase contrast (DPC) map
- Comparing contrast in both outputs

Run:
    GMS_SIMULATE=1 python examples/04_4dstem_analysis.py
"""

import asyncio
import os
import sys

sys.path.insert(0, "src")
os.environ.setdefault("GMS_SIMULATE", "1")

from gms_mcp.client import run_agent


QUERY = """
Perform a complete 4D-STEM acquisition and analysis workflow:

1. Set the camera length to 150 mm.
2. Acquire a 32×32 4D-STEM dataset with 500 µs dwell time.
   Report the dataset dimensions and estimated file size.
3. Compute a virtual HAADF image using an annular detector
   with inner angle 20 mrad and outer angle 80 mrad.
   Report the mean intensity and dynamic range.
4. Compute a differential phase contrast (DPC) map from the
   same dataset (inner=0 mrad, outer=30 mrad).
   Report whether the DPC signal shows measurable contrast
   compared to the virtual HAADF.
"""


async def main():
    result = await run_agent(query=QUERY, model="qwen2.5:7b", verbose=True)
    print("\n─── Agent Response ───")
    print(result["answer"])


if __name__ == "__main__":
    asyncio.run(main())
