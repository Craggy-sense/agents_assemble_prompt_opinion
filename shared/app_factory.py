"""
A2A application factory — shared by all agents in this repo.

Each agent's app.py calls create_a2a_app() with its own name, description,
URL, and optional FHIR extension URI.  The factory handles the AgentCard
boilerplate, wires up the A2A transport, and optionally attaches API key
middleware.

Security modes
──────────────
  require_api_key=True  (default)
      Agent card advertises X-API-Key as required.
      All requests except /.well-known/agent-card.json are blocked without a
      valid key.  Use this for agents that handle sensitive data (e.g. FHIR).

  require_api_key=False
      Agent card declares no security scheme — any caller can send requests
      without a key.  The agent card itself makes this discoverable so Prompt
      Opinion and other callers know no key is needed.  Use this for public or
      read-only utility agents (e.g. ICD-10 lookups, date/time queries).

Usage:
    from shared.app_factory import create_a2a_app
    from .agent import root_agent

    # Authenticated agent (requires X-API-Key)
    a2a_app = create_a2a_app(
        agent=root_agent,
        name="healthcare_fhir_agent",
        description="Queries patient FHIR data.",
        url="http://localhost:8001",
        port=8001,
        fhir_extension_uri="https://your-workspace/schemas/a2a/v1/fhir-context",
        require_api_key=True,   # default — can be omitted
    )

    # Anonymous agent (no key needed)
    a2a_app = create_a2a_app(
        agent=root_agent,
        name="general_agent",
        description="Public utility agent.",
        url="http://localhost:8002",
        port=8002,
        require_api_key=False,
    )
"""
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentExtension,
    AgentSkill,
    APIKeySecurityScheme,
    In,
    SecurityScheme,
)
from starlette.responses import JSONResponse
from starlette.requests import Request
from starlette.middleware.cors import CORSMiddleware
from google.adk.a2a.utils.agent_to_a2a import to_a2a

from shared.middleware import ApiKeyMiddleware


def create_a2a_app(
    agent,
    name: str,
    description: str,
    url: str,
    port: int = 8001,
    version: str = "1.0.0",
    fhir_extension_uri: str | None = None,
    require_api_key: bool = True,
    skills: list[AgentSkill] | None = None,
):
    """
    Build and return an A2A ASGI application for the given ADK agent.

    Args:
        agent:               The ADK Agent instance (root_agent from agent.py).
        name:                Agent name — shown in the agent card and Prompt Opinion UI.
        description:         Short description of what this agent does.
        url:                 Public base URL where this agent is reachable.
        port:                Port the agent listens on (used by to_a2a).
        version:             Semver string, e.g. "1.0.0".
        fhir_extension_uri:  If provided, advertises FHIR context support in the
                             agent card.  Callers use this URI as the metadata key
                             when sending FHIR credentials.  Omit for non-FHIR agents.
        require_api_key:     If True (default), the agent card declares X-API-Key as
                             required and ApiKeyMiddleware is attached — all requests
                             without a valid key are rejected with 401/403.
                             If False, no security scheme is declared and no middleware
                             is attached — the agent is publicly accessible.

    Returns:
        A Starlette ASGI application ready to be served with uvicorn.
    """
    # Optional FHIR extension — only included when the agent supports it.
    extensions = []
    if fhir_extension_uri:
        extensions = [
            AgentExtension(
                uri=fhir_extension_uri,
                description="FHIR R4 context — allows the agent to query the patient's FHIR server.",
                required=True,
            )
        ]

    # Security scheme — advertised in the agent card so callers know what to send.
    if require_api_key:
        security_schemes = {
            "apiKey": SecurityScheme(
                root=APIKeySecurityScheme(
                    type="apiKey",
                    name="X-API-Key",
                    in_=In.header,
                    description="API key required to access this agent.",
                )
            )
        }
        security = [{"apiKey": []}]
    else:
        # No security scheme — agent is publicly accessible.
        # The empty values tell callers (including Prompt Opinion) that no
        # authentication is required.
        security_schemes = None 
        security = None

    # --- PROFESSIONAL A2A 1.0 MANIFEST ---
    import time
    unique_suffix = int(time.time())
    
    agent_card = AgentCard(
        name=f"Oncology_Care_Coordinator_{unique_suffix}",
        description="Precision Medicine orchestrator for NSCLC. Reconciles biomarkers and matches clinical trials.",
        url=url,
        version="1.0.0",
        defaultInputModes=["text/plain"],
        defaultOutputModes=["text/plain"],
        capabilities=AgentCapabilities(
            streaming=True,
            pushNotifications=False,
            stateTransitionHistory=True,
            extensions=[
                AgentExtension(
                    uri=fhir_extension_uri,
                    description="FHIR R4 context — allows the agent to query the patient's FHIR server.",
                    required=True,
                )
            ] if fhir_extension_uri else [],
        ),
        skills=skills or [],
        securitySchemes=security_schemes,
        security=security,
    )

    app = to_a2a(agent, port=port, agent_card=agent_card)

    # Add CORS support in case the browser UI is doing the fetching
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # --- HACKATHON FIX: Inject 'supportedInterfaces' required by Prompt Opinion platform ---
    @app.route("/.well-known/agent-card.json")
    async def get_agent_card_fixed(request: Request):
        # ---- A2A v1.0 SPEC-COMPLIANT AGENT CARD ----
        # Built from https://a2a-protocol.org/latest/specification/#441-agentcard
        # and https://docs.promptopinion.ai/a2a-v1-migration
        card_data = {
            "name": "Oncology_Care_Coordinator",
            "description": "Precision medicine orchestrator for Oncology.",
            "version": "1.0.0",
            "iconUrl": "https://img.icons8.com/fluency/96/cancer.png",
            "contact": {
                "name": "Memusi Robi",
                "email": "mrobi@strathmore.edu",
                "organization": "Strathmore University"
            },
            "defaultInputModes": ["text/plain"],
            "defaultOutputModes": ["text/plain"],
            "supportedInterfaces": [
                {
                    "url": url.rstrip("/"),
                    "protocolBinding": "JSONRPC",
                    "protocolVersion": "1.0"
                }
            ],
            "capabilities": {
                "streaming": True,
                "pushNotifications": False,
                "extensions": [
                    {
                        "uri": "https://app.promptopinion.ai/schemas/a2a/v1/fhir-context",
                        "description": "FHIR context allowing the agent to query a FHIR server securely",
                        "required": False
                    }
                ]
            },
            "skills": [
                {
                    "id": "biomarker-analysis",
                    "name": "Biomarker Analysis",
                    "description": "Analyze genomic variants and biomarkers like EGFR, ALK, KRAS, and PD-L1.",
                    "tags": ["genomics", "oncology", "fhir"]
                },
                {
                    "id": "clinical-trial-matching",
                    "name": "Clinical Trial Matching",
                    "description": "Match patients to precision oncology clinical trials based on biomarker profiles.",
                    "tags": ["trials", "research", "oncology"]
                },
                {
                    "id": "tumor-board-orchestration",
                    "name": "Tumor Board Orchestration",
                    "description": "Synthesize pathology, radiology, and genomic data for MDT preparation.",
                    "tags": ["orchestration", "triage", "oncology"]
                },
                {
                    "id": "patient-demographics",
                    "name": "Patient Demographics",
                    "description": "Retrieve patient demographics like name, DOB, and contacts.",
                    "tags": ["demographics", "fhir"]
                },
                {
                    "id": "active-medications",
                    "name": "Active Medications",
                    "description": "Get a list of the patient's active medications and dosages.",
                    "tags": ["medications", "fhir"]
                },
                {
                    "id": "active-conditions",
                    "name": "Active Conditions",
                    "description": "Get the patient's active conditions and diagnoses.",
                    "tags": ["conditions", "fhir"]
                },
                {
                    "id": "recent-observations",
                    "name": "Recent Observations",
                    "description": "Retrieve recent vitals, lab results, and social history.",
                    "tags": ["observations", "fhir"]
                }
            ],
            "securitySchemes": {
                "apiKey": {
                    "apiKeySecurityScheme": {
                        "name": "X-API-Key",
                        "location": "header",
                        "description": "API key required to access this agent."
                    }
                }
            },
            "securityRequirements": [
                {"apiKey": []}
            ]
        }

        
        return JSONResponse(card_data)


    # Only attach the key-enforcement middleware for authenticated agents.
    if require_api_key:
        app.add_middleware(ApiKeyMiddleware)

    return app
