"""Service layer — orchestration and optimisation.

Deliberately does NOT re-export submodules. ``app.graph.nodes`` imports
``app.services.allocator`` while ``app.services.orchestrator`` imports
``app.graph.builder``; eager re-exports here would close that loop into a
circular import. Import the submodule you need directly.
"""
