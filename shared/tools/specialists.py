"""
Specialist Delegation Tools — formal A2A orchestration tools.

These tools allow the Oncology Care Coordinator (OCC) to formally delegate tasks 
to other specialized agents (Radiology, Pathology, Clinical Trials) within the 
A2A ecosystem.
"""
import logging
from google.adk.tools import ToolContext

logger = logging.getLogger(__name__)

def request_specialist_consultation(
    specialty: str, 
    reason: str, 
    urgency: str = "routine", 
    tool_context: ToolContext = None
) -> dict:
    """
    Formally requests a specialist consultation or 'Second Opinion' via the A2A protocol.

    Args:
        specialty: The type of specialist needed. Options: 
                   'Radiology' (for staging recalibration),
                   'Pathology' (for molecular second opinions),
                   'Clinical Trials' (for deep-dive enrollment verification).
        reason:    Specific clinical question or objective for the consultation.
        urgency:   'routine', 'urgent', or 'stat'.

    Returns:
        A structured delegation request confirmation.
    """
    logger.info("request_specialist_consultation specialty=%s reason=%s", specialty, reason)

    # In a production A2A environment, this tool would trigger a cross-agent call.
    # For the hackathon, we return a formal delegation object that the platform 
    # can use to route the next turn.

    specialties = {
        "Radiology": "agent://specialist-radiology",
        "Pathology": "agent://specialist-pathology",
        "Clinical Trials": "agent://specialist-trials"
    }

    target_agent = specialties.get(specialty, "agent://general-consultant")

    narratives = {
        "Radiology": (
            f"Handing off to the Radiology Board for staging verification. "
            f"Clinical objective: {reason}. All imaging context bridged."
        ),
        "Pathology": (
            f"Engaging Pathology Specialist for a molecular second opinion. "
            f"Query: {reason}. mCODE pathology context attached."
        ),
        "Clinical Trials": (
            f"Consulting the Clinical Trials Enrollment Specialist. "
            f"Objective: {reason}. Screening criteria transferred."
        )
    }

    narrative = narratives.get(specialty, f"Requesting {specialty} consultation for: {reason}.")

    return {
        "status": "delegation_requested",
        "delegation": {
            "target_specialty": specialty,
            "target_agent_uri": target_agent,
            "clinical_reason": reason,
            "urgency": urgency,
            "context_bridged": ["fhir-context", "patient-id"]
        },
        "message": f"✅ {narrative}"
    }

