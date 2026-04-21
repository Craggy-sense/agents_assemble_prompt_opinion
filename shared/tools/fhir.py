"""
FHIR tools — query a FHIR R4 server on behalf of the patient in context.

These tools are registered with the agent in agent.py.  At call time, each
tool reads the FHIR credentials (fhir_url, fhir_token, patient_id) from
tool_context.state — values that were injected by fhir_hook.extract_fhir_context
before the LLM was called.  The credentials never appear in the prompt.

─────────────────────────────────────────────────────────────────────────────
Adding your own FHIR tools
─────────────────────────────────────────────────────────────────────────────
1. Write a new function in this file (or create a new file in shared/tools/).
2. Add tool_context: ToolContext as the LAST parameter.
3. Start with  ctx = _get_fhir_context(tool_context); if isinstance(ctx, dict): return ctx
4. Export it from shared/tools/__init__.py.
5. Add it to the tools=[...] list in whichever agent(s) need it.

All FHIR REST calls go through _fhir_get(), which attaches the Bearer token
and sets the Accept header.  httpx is used (already a transitive dependency of
google-adk / a2a-sdk — no extra install required).
"""
import json
import logging
import os

import httpx
from google.adk.tools import ToolContext

logger = logging.getLogger(__name__)

_FHIR_TIMEOUT = 15  # seconds


# ── Private helpers ────────────────────────────────────────────────────────────

def _get_fhir_context(tool_context: ToolContext):
    """
    Read FHIR credentials injected by fhir_hook into the session state.

    Returns (fhir_url, fhir_token, patient_id) on success.
    Returns an error dict if any credential is missing so the caller can
    return it directly as the tool result.
    """
    fhir_url   = tool_context.state.get("fhir_url",   "").rstrip("/")
    fhir_token = tool_context.state.get("fhir_token", "")
    patient_id = tool_context.state.get("patient_id", "")

    missing = [
        name for name, val in [
            ("fhir_url",   fhir_url),
            ("fhir_token", fhir_token),
            ("patient_id", patient_id),
        ]
        if not val
    ]
    if missing:
        return {
            "status": "error",
            "error_message": (
                f"FHIR context is not available — missing: {', '.join(missing)}. "
                "Ensure the caller includes 'fhir-context' in the A2A message metadata."
            ),
        }
    return fhir_url, fhir_token, patient_id


def _fhir_get(fhir_url: str, token: str, path: str, params: dict | None = None) -> dict:
    """Perform an authenticated FHIR GET and return the parsed JSON response."""
    response = httpx.get(
        f"{fhir_url}/{path}",
        params=params,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept":        "application/fhir+json",
        },
        timeout=_FHIR_TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


def _http_error_result(exc: httpx.HTTPStatusError) -> dict:
    return {
        "status":        "error",
        "http_status":   exc.response.status_code,
        "error_message": f"FHIR server returned HTTP {exc.response.status_code}: {exc.response.text[:200]}",
    }


def _connection_error_result(exc: Exception) -> dict:
    return {
        "status":        "error",
        "error_message": f"Could not reach FHIR server: {exc}",
    }


def _coding_display(codings: list) -> str:
    """Return the first human-readable display text from a list of FHIR codings."""
    for c in codings:
        if c.get("display"):
            return c["display"]
    return "Unknown"


# ── Tool: patient demographics ─────────────────────────────────────────────────

def get_patient_demographics(tool_context: ToolContext) -> dict:
    """
    Fetches the demographic information for the current patient from the FHIR server.

    Returns name, date of birth, gender, and primary contact details.
    No arguments required — the patient identity comes from the session context.
    """
    ctx = _get_fhir_context(tool_context)
    if isinstance(ctx, dict):
        return ctx
    fhir_url, fhir_token, patient_id = ctx

    logger.info("tool_get_patient_demographics patient_id=%s", patient_id)
    try:
        patient = _fhir_get(fhir_url, fhir_token, f"Patient/{patient_id}")
    except httpx.HTTPStatusError as e:
        return _http_error_result(e)
    except Exception as e:
        return _connection_error_result(e)

    names    = patient.get("name", [])
    official = next((n for n in names if n.get("use") == "official"), names[0] if names else {})
    given    = " ".join(official.get("given", []))
    family   = official.get("family", "")
    full_name = f"{given} {family}".strip() or "Unknown"

    contacts = [
        {"system": t.get("system"), "value": t.get("value"), "use": t.get("use")}
        for t in patient.get("telecom", [])
    ]

    addrs   = patient.get("address", [])
    address = None
    if addrs:
        a = addrs[0]
        address = ", ".join(filter(None, [
            " ".join(a.get("line", [])),
            a.get("city"), a.get("state"), a.get("postalCode"), a.get("country"),
        ]))

    return {
        "status":         "success",
        "patient_id":     patient_id,
        "name":           full_name,
        "birth_date":     patient.get("birthDate"),
        "gender":         patient.get("gender"),
        "active":         patient.get("active"),
        "contacts":       contacts,
        "address":        address,
        "marital_status": (patient.get("maritalStatus") or {}).get("text"),
    }


# ── Tool: active medications ───────────────────────────────────────────────────

def get_active_medications(tool_context: ToolContext) -> dict:
    """
    Retrieves the patient's current active medication list from the FHIR server.

    Queries MedicationRequest resources with status=active and returns medication
    names, dosage instructions, and prescribing dates.
    No arguments required.
    """
    ctx = _get_fhir_context(tool_context)
    if isinstance(ctx, dict):
        return ctx
    fhir_url, fhir_token, patient_id = ctx

    logger.info("tool_get_active_medications patient_id=%s", patient_id)
    try:
        bundle = _fhir_get(
            fhir_url, fhir_token, "MedicationRequest",
            params={"patient": patient_id, "status": "active", "_count": "50"},
        )
    except httpx.HTTPStatusError as e:
        return _http_error_result(e)
    except Exception as e:
        return _connection_error_result(e)

    medications = []
    for entry in bundle.get("entry", []):
        res         = entry.get("resource", {})
        med_concept = res.get("medicationCodeableConcept", {})
        med_name    = (
            med_concept.get("text")
            or _coding_display(med_concept.get("coding", []))
            or res.get("medicationReference", {}).get("display", "Unknown")
        )
        dosage_list = [d.get("text", "No dosage text") for d in res.get("dosageInstruction", [])]
        medications.append({
            "medication":  med_name,
            "status":      res.get("status"),
            "dosage":      dosage_list[0] if dosage_list else "Not specified",
            "authored_on": res.get("authoredOn"),
            "requester":   (res.get("requester") or {}).get("display"),
        })

    return {
        "status":      "success",
        "patient_id":  patient_id,
        "count":       len(medications),
        "medications": medications,
    }


# ── Tool: active conditions (problem list) ─────────────────────────────────────

def get_active_conditions(tool_context: ToolContext) -> dict:
    """
    Retrieves the patient's active conditions and diagnoses from the FHIR server.

    Queries Condition resources with clinical-status=active and returns the
    problem list with condition names, severity, and onset dates.
    No arguments required.
    """
    ctx = _get_fhir_context(tool_context)
    if isinstance(ctx, dict):
        return ctx
    fhir_url, fhir_token, patient_id = ctx

    logger.info("tool_get_active_conditions patient_id=%s", patient_id)
    try:
        bundle = _fhir_get(
            fhir_url, fhir_token, "Condition",
            params={"patient": patient_id, "clinical-status": "active", "_count": "50"},
        )
    except httpx.HTTPStatusError as e:
        return _http_error_result(e)
    except Exception as e:
        return _connection_error_result(e)

    conditions = []
    for entry in bundle.get("entry", []):
        res   = entry.get("resource", {})
        code  = res.get("code", {})
        onset = res.get("onsetDateTime") or (res.get("onsetPeriod") or {}).get("start")
        conditions.append({
            "condition":       code.get("text") or _coding_display(code.get("coding", [])),
            "clinical_status": (
                (res.get("clinicalStatus") or {}).get("coding", [{}])[0].get("code")
            ),
            "severity":        (res.get("severity") or {}).get("text"),
            "onset":           onset,
            "recorded_date":   res.get("recordedDate"),
        })

    return {
        "status":     "success",
        "patient_id": patient_id,
        "count":      len(conditions),
        "conditions": conditions,
    }


# ── Tool: recent observations (vitals / labs) ──────────────────────────────────

def get_recent_observations(category: str, tool_context: ToolContext) -> dict:
    """
    Retrieves recent clinical observations for the patient from the FHIR server.

    Args:
        category: FHIR observation category. Common values:
                    'vital-signs'    — blood pressure, heart rate, temperature, SpO2
                    'laboratory'     — lab results (CBC, HbA1c, metabolic panel, etc.)
                    'social-history' — smoking status, alcohol use, etc.
                  Defaults to 'vital-signs' if not specified.

    Returns the 20 most recent observations in the category, newest first.
    """
    ctx = _get_fhir_context(tool_context)
    if isinstance(ctx, dict):
        return ctx
    fhir_url, fhir_token, patient_id = ctx

    category = (category or "vital-signs").strip().lower()
    logger.info("tool_get_recent_observations patient_id=%s category=%s", patient_id, category)
    try:
        bundle = _fhir_get(
            fhir_url, fhir_token, "Observation",
            params={"patient": patient_id, "category": category, "_sort": "-date", "_count": "20"},
        )
    except httpx.HTTPStatusError as e:
        return _http_error_result(e)
    except Exception as e:
        return _connection_error_result(e)

    observations = []
    for entry in bundle.get("entry", []):
        res  = entry.get("resource", {})
        code = res.get("code", {})
        obs_name = code.get("text") or _coding_display(code.get("coding", []))

        value, unit = None, None
        if "valueQuantity" in res:
            vq    = res["valueQuantity"]
            value = vq.get("value")
            unit  = vq.get("unit") or vq.get("code")
        elif "valueCodeableConcept" in res:
            value = (res["valueCodeableConcept"].get("text")
                     or _coding_display(res["valueCodeableConcept"].get("coding", [])))
        elif "valueString" in res:
            value = res["valueString"]

        components = []
        for comp in res.get("component", []):
            comp_code = (comp.get("code") or {})
            comp_name = comp_code.get("text") or _coding_display(comp_code.get("coding", []))
            comp_vq   = comp.get("valueQuantity", {})
            components.append({
                "name":  comp_name,
                "value": comp_vq.get("value"),
                "unit":  comp_vq.get("unit") or comp_vq.get("code"),
            })

        observations.append({
            "observation":    obs_name,
            "value":          value,
            "unit":           unit,
            "components":     components or None,
            "effective_date": res.get("effectiveDateTime") or (res.get("effectivePeriod") or {}).get("start"),
            "status":         res.get("status"),
            "interpretation": (
                (res.get("interpretation") or [{}])[0].get("text")
                or _coding_display((res.get("interpretation") or [{}])[0].get("coding", []))
            ),
        })

    return {
        "status":       "success",
        "patient_id":   patient_id,
        "category":     category,
        "count":        len(observations),
        "observations": observations,
    }
# ── Tool: oncology reports (pathology / biopsy) ───────────────────────────────

def get_oncology_reports(tool_context: ToolContext) -> dict:
    """
    Retrieves oncological diagnostic reports (pathology, biopsy, imaging) from the FHIR server.

    Queries DiagnosticReport resources and filters for oncology-related results.
    No arguments required.
    """
    ctx = _get_fhir_context(tool_context)
    if isinstance(ctx, dict):
        return ctx
    fhir_url, fhir_token, patient_id = ctx

    logger.info("tool_get_oncology_reports patient_id=%s", patient_id)
    try:
        # Search for DiagnosticReports for the patient. 
        # In a real system, we'd filter by category=LAB or pathology-specific codes.
        bundle = _fhir_get(
            fhir_url, fhir_token, "DiagnosticReport",
            params={"patient": patient_id, "_count": "10", "_sort": "-date"},
        )
    except httpx.HTTPStatusError as e:
        return _http_error_result(e)
    except Exception as e:
        return _connection_error_result(e)

    reports = []
    for entry in bundle.get("entry", []):
        res = entry.get("resource", {})
        reports.append({
            "report_type":   (res.get("code") or {}).get("text") or _coding_display((res.get("code") or {}).get("coding", [])),
            "status":        res.get("status"),
            "effective_date": res.get("effectiveDateTime"),
            "issued":        res.get("issued"),
            "conclusion":    res.get("conclusion"),
            "result_summary": [
                {"display": obs.get("display"), "reference": obs.get("reference")}
                for obs in res.get("result", [])
            ]
        })

    return {
        "status":     "success",
        "patient_id": patient_id,
        "count":      len(reports),
        "reports":    reports,
    }


# ── Tool: molecular variants (genomics) ────────────────────────────────────────

def get_molecular_variants(tool_context: ToolContext) -> dict:
    """
    Retrieves structured genomic variants and biomarkers (e.g., EGFR, ALK, PD-L1) for the patient.

    Queries Observation resources with category 'genomic' and returns molecular findings.
    No arguments required.
    """
    ctx = _get_fhir_context(tool_context)
    if isinstance(ctx, dict):
        return ctx
    fhir_url, fhir_token, patient_id = ctx

    logger.info("tool_get_molecular_variants patient_id=%s", patient_id)
    try:
        # Search for genomic observations.
        bundle = _fhir_get(
            fhir_url, fhir_token, "Observation",
            params={"patient": patient_id, "category": "genomic", "_count": "20"},
        )
    except httpx.HTTPStatusError as e:
        return _http_error_result(e)
    except Exception as e:
        return _connection_error_result(e)

    variants = []
    for entry in bundle.get("entry", []):
        res = entry.get("resource", {})
        code = res.get("code", {})
        
        # Extract variant/biomarker name
        name = code.get("text") or _coding_display(code.get("coding", []))
        
        # Extract value (e.g., 'Detected', 'Positive', 'TPS 60%')
        value = None
        if "valueCodeableConcept" in res:
            value = res["valueCodeableConcept"].get("text") or _coding_display(res["valueCodeableConcept"].get("coding", []))
        elif "valueString" in res:
            value = res["valueString"]
        elif "valueQuantity" in res:
            value = f"{res['valueQuantity'].get('value')} {res['valueQuantity'].get('unit')}"

        variants.append({
            "biomarker":      name,
            "value":          value,
            "status":         res.get("status"),
            "effective_date": res.get("effectiveDateTime"),
        })

    return {
        "status":     "success",
        "patient_id": patient_id,
        "count":      len(variants),
        "variants":   variants,
    }


# ── Tool: clinical trial matching ─────────────────────────────────────────────

def match_clinical_trials(tool_context: ToolContext) -> dict:
    """
    Matches the current patient against a database of available oncology clinical trials.

    Analyzes the patient's conditions and molecular markers to identify eligible trials.
    No arguments required.
    """
    # 1. Get molecular markers
    variants_res = get_molecular_variants(tool_context)
    if variants_res.get("status") != "success":
        return variants_res
    
    variants = variants_res.get("variants", [])
    
    # 2. Get active conditions
    conditions_res = get_active_conditions(tool_context)
    if conditions_res.get("status") != "success":
        return conditions_res
    
    conditions = [c.get("condition", "").lower() for c in conditions_res.get("conditions", [])]

    # 3. Load trials from our high-impact registry
    try:
        trials_path = os.path.join(os.path.dirname(__file__), "trials.json")
        with open(trials_path, "r") as f:
            all_trials = json.load(f)
    except Exception as e:
        return {"status": "error", "error_message": f"Failed to load trial database: {e}"}

    # 4. Perform matching logic
    matches = []
    for trial in all_trials:
        trial_cond = trial.get("condition", "").lower()
        # Simple match: Does the patient have this condition?
        if any(trial_cond in c for c in conditions):
            # Check biomarker compatibility
            criteria = trial.get("criteria", {})
            target_biomarker = criteria.get("biomarker")
            
            # Find if patient has this biomarker
            patient_marker = next((v for v in variants if target_biomarker.lower() in v["biomarker"].lower()), None)
            
            if patient_marker:
                match_score = 0.5  # Base match for condition
                
                # Refine match based on mutation status
                if criteria.get("mutation_status") == "positive" and "detected" in (patient_marker.get("value") or "").lower():
                    match_score = 1.0
                elif criteria.get("min_expression"):
                    # Handle PD-L1 TPS scoring
                    try:
                        # Extract number from string like 'TPS 60%' or '60'
                        import re
                        match = re.search(r'\d+', patient_marker.get("value", ""))
                        if match:
                            val_num = int(match.group())
                            if val_num >= criteria.get("min_expression"):
                                match_score = 1.0
                    except:
                        pass
                
                if match_score >= 0.5:
                    matches.append({
                        "trial_id":     trial["id"],
                        "name":         trial["name"],
                        "description":  trial["description"],
                        "match_reason": f"Patient matches {trial_cond} and {target_biomarker} ({patient_marker['value']}) criteria.",
                        "confidence":   match_score,
                        "contact":      trial["contact"]
                    })

    return {
        "status":      "success",
        "patient_id":  variants_res["patient_id"],
        "match_count": len(matches),
        "trials":      sorted(matches, key=lambda x: x["confidence"], reverse=True),
    }
