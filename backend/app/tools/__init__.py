"""Tool package — registration happens exactly once, here.

Importing this module has the side effect of populating the global registry.
Agents then request tools by capability (``registry.for_role(...)``) rather than
importing tool classes directly, which keeps agent code independent of which
integrations happen to exist.
"""

from __future__ import annotations

from app.core.logging import get_logger
from app.tools.base import SentinelTool, ToolRegistry, ToolResult, registry
from app.tools.facilities import HospitalCapacityTool, ShelterAvailabilityTool
from app.tools.logistics import DepotStockTool, RouteEstimateTool
from app.tools.news import NewsIntelTool
from app.tools.weather import RiverLevelTool, WeatherTool

logger = get_logger(__name__)

_LOADED = False


def load_tools() -> ToolRegistry:
    """Idempotently register every tool. Safe to call from multiple entrypoints."""
    global _LOADED
    if _LOADED:
        return registry

    for tool_cls in (
        WeatherTool,
        RiverLevelTool,
        HospitalCapacityTool,
        ShelterAvailabilityTool,
        DepotStockTool,
        RouteEstimateTool,
        NewsIntelTool,
    ):
        registry.register(tool_cls())

    _LOADED = True
    logger.info("tools.registered", count=len(registry.names()), tools=registry.names())
    return registry


__all__ = [
    "SentinelTool",
    "ToolRegistry",
    "ToolResult",
    "load_tools",
    "registry",
]
