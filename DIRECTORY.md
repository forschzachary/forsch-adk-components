# Components directory note

Purpose: shared Python package for code that should be available to every ADK agent without coupling the agent repos together.

Structure:

- `pyproject.toml` - package metadata for `forsch-adk-components` and dev dependencies.
- `src/forsch/adk_components/tools/` - reusable integration clients and tool wrappers. Current work includes Authsome-backed HTTP and Frappe CRM clients.
- `src/forsch/adk_components/models/` - shared Pydantic/data contracts, currently a namespace placeholder.
- `src/forsch/adk_components/testing/` - shared test harness/eval helpers, currently a namespace placeholder.
- `tests/` - component-level tests for shared clients and utilities.
- `.venv/` - local virtual environment for this package; ADK 2.3.0 is installed here.

Current status: this repo has uncommitted Authsome/Frappe client work and tests. Treat this as the integration foundation before wiring any specific agent graph.
