# Repository Policy

## Scope

This policy applies to the entire repository unless a deeper AGENTS.md file explicitly overrides a rule for a subdirectory.

## Mandatory Rules

- Use the Docker tooling container for all development validation.
- On Windows, run `docker compose` commands directly.
- Treat `src/` as application code and `tests/` as the primary verification surface.
- Keep changes small, local, and directly related to the requested task.
- Do not assume GPIO, SPI, or e-paper hardware access works inside the container.
- Do not introduce unrelated refactors, broad cleanup, or style-only changes.

## Validation Requirements

- Always run Ruff after making a change.
- Always run the relevant tests after making a change.
- If a change affects rendering, inspect `test_output.bmp` and verify the rendered output is correct.
- If validation fails, fix the failure in the changed slice before expanding scope.

## Command Policy

- Ruff check: `docker compose run --rm --entrypoint ruff tools check src/ tests/`
- Ruff format: `docker compose run --rm --entrypoint ruff tools format src/ tests/`
- Full tests: `docker compose run --rm tools pytest tests/ -v`
- Single test: `docker compose run --rm tools "pytest tests/test_widgets.py::TestRoomsWidget -v"`

## Change Policy

- Update or add tests when behavior changes.
- Preserve existing module layout and naming unless the task requires a structural change.
- Prefer mock-based tests over hardware-dependent checks.
- Keep the repository documentation and Makefile commands aligned with the workflow described here.

## Exception Handling

- If a rule cannot be followed, state the blocker clearly and choose the closest safe alternative.
- If a rendering change cannot be verified visually, report that explicitly.
- If a command must differ from the policy, explain why in the final response.