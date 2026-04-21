"""
healthcare_agent — A2A application entry point.

Start the server with:
    uvicorn healthcare_agent.app:a2a_app --host 0.0.0.0 --port 8001

The agent card is served publicly at:
    GET http://localhost:8001/.well-known/agent-card.json

All other endpoints require an X-API-Key header (see shared/middleware.py).
"""
import os

from a2a.types import AgentSkill
from shared.app_factory import create_a2a_app

from .agent import root_agent

print(os.getenv('PO_PLATFORM_BASE_URL'))

a2a_app = create_a2a_app(
    agent=root_agent,
    name="oncology_care_coordinator",
    description=(
        "The Oncology Care Coordinator (OCC) - a precision medicine orchestrator designed to "
        "manage the 'Last Mile' of cancer care using mCODE, A2A, and SHARP."
    ),
    url=os.getenv("OCC_AGENT_URL", os.getenv("BASE_URL", "http://localhost:8001")),
    port=8001,
    # This URI is the key under which callers send FHIR credentials in the
    # A2A message metadata.  Update to match your Prompt Opinion workspace URL.
    fhir_extension_uri=f"{os.getenv('PO_PLATFORM_BASE_URL', 'http://localhost:5139')}/schemas/a2a/v1/fhir-context",
    skills=[
        AgentSkill(
            id="biomarker-analysis",
            name="biomarker-analysis",
            description="Analyze genomic variants and biomarkers like EGFR, ALK, KRAS, and PD-L1.",
            tags=["genomics", "oncology", "fhir"],
        ),
        AgentSkill(
            id="clinical-trial-matching",
            name="clinical-trial-matching",
            description="Match patients to precision oncology clinical trials based on biomarker profiles.",
            tags=["trials", "research", "oncology"],
        ),
        AgentSkill(
            id="tumor-board-orchestration",
            name="tumor-board-orchestration",
            description="Synthesize pathology, radiology, and genomic data for MDT (Multi-Disciplinary Team) preparation.",
            tags=["orchestration", "triage", "oncology"],
        ),
        AgentSkill(
            id="patient-demographics",
            name="patient-demographics",
            description="Retrieve patient demographics like name, DOB, and contacts.",
            tags=["demographics", "fhir"],
        ),
        AgentSkill(
            id="active-medications",
            name="active-medications",
            description="Get a list of the patient's active medications and dosages.",
            tags=["medications", "fhir"],
        ),
        AgentSkill(
            id="active-conditions",
            name="active-conditions",
            description="Get the patient's active conditions and diagnoses.",
            tags=["conditions", "fhir"],
        ),
        AgentSkill(
            id="recent-observations",
            name="recent-observations",
            description="Retrieve recent vitals, lab results, and social history.",
            tags=["observations", "fhir"],
        ),
    ],
)
