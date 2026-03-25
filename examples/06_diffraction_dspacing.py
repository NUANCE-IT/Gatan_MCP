"""
Example 06 — Electron diffraction pattern and d-spacing analysis.

Demonstrates:
- Acquiring a selected-area electron diffraction (SAED) pattern
- Automatic ring detection and d-spacing extraction
- Crystal structure assignment from d-spacings

Run:
    GMS_SIMULATE=1 python examples/06_diffraction_dspacing.py
"""

import asyncio
import os
import sys

sys.path.insert(0, "src")
os.environ.setdefault("GMS_SIMULATE", "1")

from gms_mcp.client import run_agent


QUERY = """
Acquire and analyse an electron diffraction pattern:

1. Set the camera length to 200 mm.
2. Acquire a diffraction pattern with 0.2 s exposure and 1× binning.
3. From the reported d-spacings, identify which of the following
   crystal structures best matches the detected rings:

   - FCC Au: d = {2.355, 2.039, 1.442, 1.230, 1.177} Å
   - FCC Pt: d = {2.265, 1.960, 1.387, 1.183, 1.131} Å
   - BCC Fe: d = {2.027, 1.433, 1.170, 1.013, 0.906} Å
   - NaCl:   d = {2.820, 1.994, 1.628, 1.410, 1.261} Å

   Match each detected d-spacing to the nearest tabulated value
   and report the best-fit structure with residual (Å).
4. Report the pixel scale (1/Å per pixel) used for the calculation.
"""


async def main():
    result = await run_agent(query=QUERY, model="qwen2.5:7b", verbose=True)
    print("\n─── Agent Response ───")
    print(result["answer"])


if __name__ == "__main__":
    asyncio.run(main())
