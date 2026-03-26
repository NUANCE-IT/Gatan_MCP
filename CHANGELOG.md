# Changelog

All notable changes to GMS-MCP are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Planned
- GMS plug-in installer for the ZeroMQ bridge
- EELS Spectrum Image (SI) acquisition via DigiScan + GIF synchronized scan
- ncempy / HyperSpy integration for DM4 file parsing and provenance tagging
- Multi-agent architecture for complex experimental workflows
- MicroscopyBench evaluation suite

---

## [0.1.1] — 2026-03-26

### Fixed
- Corrected the published package author email metadata
- Added local CI virtual environment ignores to keep release commits clean

---

## [0.1.0] — 2025-03-23

### Added
- **12 MCP tools** covering TEM/HRTEM, STEM (HAADF/BF/ABF), 4D-STEM/NBED,
  EELS, electron diffraction, stage control, beam/optics, detector
  configuration, tilt series, and 4D-STEM virtual detector analysis
- **DMSimulator** — physics-plausible digital twin of the DigitalMicrograph
  Python API with synthetic data generators for all five modalities
- **Pydantic v2 input validation** with physical bounds for all 12 tools
- **FastMCP 3.x server** supporting both stdio and Streamable HTTP transports
- **Ollama ReAct agent** (`client.py`) using LangChain + LangGraph with
  multi-turn conversation history
- **49-test pytest regression suite** (55 total, 6 Ollama-only)
- Local LLM benchmarks for qwen2.5:7b, qwen2.5:14b, llama3.1:8b,
  llama3.2:3b, mistral-nemo
- ZeroMQ two-process bridge architecture for GMS integration
- Automated ring detection and d-spacing extraction in diffraction tool
- CoM, DPC, and virtual annular detector analysis in 4D-STEM tool
- arXiv preprint: dos Reis & Dravid (2025), arXiv:2025.XXXXX
- MIT License
- GitHub Actions CI: lint (ruff), type-check (mypy), test matrix
  (Python 3.9–3.12, Ubuntu/Windows/macOS)

---

[Unreleased]: https://github.com/NUANCE-IT/Gatan_MCP/compare/v0.1.1...HEAD
[0.1.1]: https://github.com/NUANCE-IT/Gatan_MCP/releases/tag/v0.1.1
[0.1.0]: https://github.com/NUANCE-IT/Gatan_MCP/releases/tag/v0.1.0
