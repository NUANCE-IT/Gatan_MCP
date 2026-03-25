# Contributing to GMS-MCP

Thank you for contributing to GMS-MCP!
This document explains how to get started, what we welcome, and the
standards we apply.

---

## Ways to Contribute

- **Bug reports** — open an Issue with the label `bug`
- **New modalities** — EFTEM, Lorentz TEM, EELS-SI, EDX mapping
- **New Ollama model benchmarks** — run `TestOllamaIntegration` with
  your model and open a PR updating `README.md` Table 4
- **Live GMS testing** — report which GMS version / microscope hardware
  you tested against in your PR description
- **Documentation** — corrections, tutorials, translation
- **Examples** — new `examples/` scripts demonstrating real workflows

---

## Development Setup

```bash
git clone https://github.com/rmsreis/gms-mcp
cd gms-mcp
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[all]"
```

### Verify the setup

```bash
GMS_SIMULATE=1 pytest tests/ -v -m "not ollama"
# All 49 tests should pass in ~18 s
```

---

## Code Standards

We use **ruff** for linting and formatting, and **mypy** for type checking.

```bash
# Format
ruff format src/ tests/

# Lint (auto-fix safe issues)
ruff check --fix src/ tests/

# Type check
mypy src/gms_mcp/
```

The CI pipeline enforces these on every pull request.

### Key conventions

- **Pydantic v2** for all tool input models — never raw `dict` parameters
- **Physical bounds** must be enforced in every new tool's input model
- **Docstrings** must include parameter descriptions and return structure
- **Tool annotations** (`readOnlyHint`, `destructiveHint`) must be set
- **No hardware calls** in the simulator path — all `DM.*` calls must be
  guarded by the `_SIMULATE` flag or routed through the ZeroMQ bridge

---

## Adding a New Tool

1. Define a Pydantic input model in `server.py`:

```python
class AcquireMyModalityInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    exposure_s: float = Field(
        default=1.0, ge=0.001, le=60.0,
        description="Exposure time in seconds."
    )
```

2. Register the tool with `@mcp.tool` and proper annotations:

```python
@mcp.tool(
    name="gms_acquire_my_modality",
    annotations={"readOnlyHint": False, "destructiveHint": False,
                 "idempotentHint": False, "openWorldHint": False},
)
def gms_acquire_my_modality(params: AcquireMyModalityInput) -> str:
    """
    One-line description.

    Longer description explaining what the tool does, what DM API
    calls it makes, and what the JSON response contains.

    Parameters:
        params.exposure_s (float): ...

    Returns JSON with: ...
    """
    try:
        # implementation
        return json.dumps({"success": True, ...}, indent=2)
    except Exception as e:
        return _build_error(str(e), "Helpful suggestion.")
```

3. Add a corresponding simulation path in `simulator.py` if the tool
   calls any DM functions not already implemented.

4. Write tests in `tests/test_gms_mcp.py`:
   - At least one valid-input test
   - At least one invalid-input test (verifying `pydantic.ValidationError`)
   - One test verifying the returned JSON contains expected keys

---

## Pull Request Checklist

- [ ] All existing tests pass: `pytest tests/ -v -m "not ollama"`
- [ ] New tests cover the new functionality
- [ ] `ruff check` and `ruff format --check` pass
- [ ] Docstrings are complete for new public functions
- [ ] `CHANGELOG.md` updated under `[Unreleased]`
- [ ] `README.md` updated if new tools were added

---

## Reporting a Bug

Please include:
- GMS version (e.g. 3.60, 3.62)
- Microscope make/model if the issue is hardware-specific
- Python version
- GMS-MCP version (`python -c "import gms_mcp; print(gms_mcp.__version__)"`)
- Minimal reproducible example
- Full traceback

---

## Questions

Open a [GitHub Discussion](https://github.com/rmsreis/gms-mcp/discussions)
or email `roberto.dosreis@northwestern.edu`.
