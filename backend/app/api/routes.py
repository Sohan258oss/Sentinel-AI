"""HTTP API.

The interesting endpoint is ``/runs/{run_id}/stream``: a Server-Sent Events
feed of the agent trace. The frontend subscribes to it and animates the command
centre as the graph executes. Everything else is conventional REST.

SSE is chosen over WebSockets deliberately — the traffic is strictly
server-to-client, SSE reconnects automatically, and it survives proxies that
mangle WebSocket upgrades.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from sse_starlette.sse import EventSourceResponse

from app import __version__
from app.api.schemas import (
    IncidentSubmission,
    RunAccepted,
    SubsystemStatus,
    SystemStatus,
)
from app.core.config import settings
from app.core.exceptions import IncidentNotFoundError
from app.core.llm import get_llm_engine
from app.core.logging import get_logger
from app.graph.builder import render_mermaid
from app.memory.store import get_memory
from app.rag.store import get_vector_store
from app.repositories.registry import registry_provenance
from app.schemas.command import OperationalPicture
from app.schemas.common import GeoPoint, Location
from app.schemas.enums import HazardType
from app.schemas.incident import IncidentReport, IncidentSummary, ReportSource
from app.schemas.trace import AgentTrace
from app.services.orchestrator import get_orchestrator
from app.services.scenarios import get_scenario, list_scenarios
from app.vision import analyze_images, get_vision_ensemble

logger = get_logger(__name__)
router = APIRouter(prefix="/api")


# ---------------------------------------------------------------------------
# System
# ---------------------------------------------------------------------------


@router.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name, "version": __version__}


@router.get("/system/status", response_model=SystemStatus, tags=["system"])
async def system_status() -> SystemStatus:
    """Capability report.

    Deliberately honest: the UI uses this to show which subsystems are live and
    which are degraded, so an operator is never misled about whether they are
    looking at model reasoning or rule-based output.
    """
    engine = get_llm_engine()
    ensemble = get_vision_ensemble()
    vision_state = ensemble.status()

    from app.vision.classifier import DamageClassifier

    classifier = DamageClassifier()
    cnn_metadata = classifier.metadata if classifier.available else {}

    store = get_vector_store()
    chunk_count = store.count()

    return SystemStatus(
        app=settings.app_name,
        version=__version__,
        environment=settings.env,
        llm=SubsystemStatus(
            name="Language model",
            available=engine.available,
            detail=engine.descriptor,
            metadata={"provider": settings.llm_provider.value},
        ),
        vision=SubsystemStatus(
            name="Vision ensemble",
            available=any(vision_state.values()),
            detail=", ".join(
                f"{name}={'up' if ok else 'down'}" for name, ok in vision_state.items()
            ),
            metadata={
                "detectors": vision_state,
                "cnn_val_accuracy": cnn_metadata.get("val_accuracy"),
                "cnn_macro_f1": cnn_metadata.get("val_macro_f1"),
                "cnn_architecture": cnn_metadata.get("architecture"),
                "cnn_train_samples": cnn_metadata.get("train_samples"),
            },
        ),
        retrieval=SubsystemStatus(
            name="Doctrine retrieval",
            available=chunk_count > 0,
            detail=f"{chunk_count} indexed passages",
            metadata={"collection": settings.vector_collection, "chunks": chunk_count},
        ),
        registries=SubsystemStatus(
            name="Resource registries",
            available=True,
            detail="hospitals, shelters, depots, river gauges",
            metadata={"synthetic": True},
        ),
        deterministic_mode=not engine.available,
        data_provenance=registry_provenance(),
        mapbox_token=settings.mapbox_token,
    )


@router.get("/system/graph", tags=["system"])
async def graph_diagram() -> dict[str, str]:
    return {"mermaid": render_mermaid()}


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------


@router.get("/scenarios", tags=["scenarios"])
async def scenarios() -> list[dict[str, str]]:
    return list_scenarios()


@router.post(
    "/scenarios/{key}/run",
    response_model=RunAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["scenarios"],
)
async def run_scenario(key: str) -> RunAccepted:
    try:
        scenario = get_scenario(key)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    report = scenario.create()
    record = await get_orchestrator().submit(report)
    return RunAccepted(
        run_id=record.run_id,
        incident_id=record.incident_id,
        stream_url=f"/api/runs/{record.run_id}/stream",
        status_url=f"/api/incidents/{record.incident_id}",
    )


# ---------------------------------------------------------------------------
# Incidents
# ---------------------------------------------------------------------------


@router.post(
    "/incidents",
    response_model=RunAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["incidents"],
)
async def submit_incident(payload: IncidentSubmission) -> RunAccepted:
    report = IncidentReport(
        incident_id=f"INC-{uuid.uuid4().hex[:8].upper()}",
        description=payload.description,
        location=Location(
            name=payload.location_name,
            point=GeoPoint(latitude=payload.latitude, longitude=payload.longitude),
            district=payload.district,
            state=payload.state,
            population=payload.population,
        ),
        source=ReportSource(
            channel=payload.channel,
            reporter_name=payload.reporter_name,
            verified=payload.verified,
            trust_weight=0.9 if payload.verified else 0.5,
        ),
        media_paths=payload.media_paths,
        reported_casualties=payload.reported_casualties,
        people_affected_estimate=payload.people_affected_estimate,
        declared_hazard=payload.declared_hazard,
    )

    record = await get_orchestrator().submit(report)
    return RunAccepted(
        run_id=record.run_id,
        incident_id=record.incident_id,
        stream_url=f"/api/runs/{record.run_id}/stream",
        status_url=f"/api/incidents/{record.incident_id}",
    )


@router.get("/incidents", response_model=list[IncidentSummary], tags=["incidents"])
async def list_incidents() -> list[IncidentSummary]:
    return get_orchestrator().list_runs()


@router.get("/incidents/{incident_id}", tags=["incidents"])
async def get_incident(incident_id: str) -> dict[str, Any]:
    try:
        record = get_orchestrator().get_by_incident(incident_id)
    except IncidentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc

    return {
        "run_id": record.run_id,
        "incident_id": record.incident_id,
        "status": record.status.value,
        "running": record.is_running,
        "error": record.error,
        "picture": record.picture.model_dump(mode="json") if record.picture else None,
        "metrics": record.metrics.model_dump(mode="json") if record.metrics else None,
    }


@router.get("/incidents/{incident_id}/picture", response_model=OperationalPicture, tags=["incidents"])
async def get_picture(incident_id: str) -> OperationalPicture:
    try:
        record = get_orchestrator().get_by_incident(incident_id)
    except IncidentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc

    if record.picture is None:
        raise HTTPException(status_code=409, detail="Run has not completed yet")
    return record.picture


# ---------------------------------------------------------------------------
# Live trace
# ---------------------------------------------------------------------------


@router.get("/runs/{run_id}/traces", response_model=list[AgentTrace], tags=["runs"])
async def run_traces(run_id: str) -> list[AgentTrace]:
    return get_orchestrator().history(run_id)


@router.get("/runs/{run_id}/stream", tags=["runs"])
async def stream_run(run_id: str) -> EventSourceResponse:
    """Server-Sent Events feed of the live agent trace."""
    orchestrator = get_orchestrator()
    try:
        orchestrator.get_run(run_id)
    except IncidentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc

    async def publisher():
        try:
            async for trace in orchestrator.stream(run_id):
                yield {
                    "event": trace.sse_event_name(),
                    "id": str(trace.sequence),
                    "data": trace.model_dump_json(),
                }
        except Exception as exc:  # noqa: BLE001 - stream must close cleanly
            logger.error("api.stream_failed", run_id=run_id, error=str(exc)[:300])
        finally:
            record = orchestrator.get_run(run_id)
            yield {
                "event": "stream_closed",
                "data": (
                    record.picture.model_dump_json()
                    if record.picture
                    else '{"error": "run did not complete"}'
                ),
            }

    return EventSourceResponse(publisher())


# ---------------------------------------------------------------------------
# Vision
# ---------------------------------------------------------------------------


@router.post("/vision/analyze", tags=["vision"])
async def analyze_image(file: UploadFile = File(...)) -> dict[str, Any]:
    """Run the vision ensemble on an uploaded image."""
    suffix = (file.filename or "upload.jpg").split(".")[-1].lower()
    if suffix not in {"jpg", "jpeg", "png", "bmp", "webp"}:
        raise HTTPException(status_code=415, detail=f"Unsupported image type: .{suffix}")

    settings.vision_upload_dir.mkdir(parents=True, exist_ok=True)
    destination = settings.vision_upload_dir / f"{uuid.uuid4().hex[:12]}.{suffix}"
    destination.write_bytes(await file.read())

    assessments = await analyze_images([str(destination)])
    if not assessments:
        raise HTTPException(status_code=500, detail="Vision analysis produced no result")

    assessment = assessments[0]
    return {
        "stored_as": destination.name,
        "path": str(destination),
        "assessment": assessment.model_dump(mode="json"),
    }


@router.get("/vision/status", tags=["vision"])
async def vision_status() -> dict[str, Any]:
    from app.vision.classifier import DamageClassifier

    classifier = DamageClassifier()
    return {
        "detectors": get_vision_ensemble().status(),
        "cnn": classifier.metadata if classifier.available else None,
    }


# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------


@router.get("/memory/lessons", tags=["memory"])
async def lessons() -> list[dict[str, Any]]:
    """Institutional knowledge accumulated across incidents."""
    return [lesson.model_dump(mode="json") for lesson in get_memory().all_lessons()]


@router.get("/memory/lessons/applicable", tags=["memory"])
async def applicable_lessons(
    hazard: HazardType, latitude: float | None = None, longitude: float | None = None
) -> list[dict[str, Any]]:
    point = (
        GeoPoint(latitude=latitude, longitude=longitude)
        if latitude is not None and longitude is not None
        else None
    )
    found = get_memory().recall_lessons(hazard=hazard, point=point)
    return [lesson.model_dump(mode="json") for lesson in found]


# ---------------------------------------------------------------------------
# Registries (map layers)
# ---------------------------------------------------------------------------


@router.get("/registry/{kind}", tags=["registry"])
async def registry(kind: str) -> dict[str, Any]:
    """Raw registry contents, for map layers in the UI."""
    from app.repositories.registry import depots, hospitals, river_gauges, shelters

    sources = {
        "hospitals": hospitals,
        "shelters": shelters,
        "depots": depots,
        "river_gauges": river_gauges,
    }
    if kind not in sources:
        raise HTTPException(
            status_code=404, detail=f"Unknown registry '{kind}'. Try: {sorted(sources)}"
        )

    repository = sources[kind]()
    return {
        "kind": kind,
        "meta": repository.meta,
        "records": [record.model_dump(mode="json") for record in repository.all()],
    }
