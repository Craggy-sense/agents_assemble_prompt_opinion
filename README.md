# 🧬 Oncology Care Coordinator (OCC) — Judge's Guide

Welcome to the **Oncology Care Coordinator (OCC)**, a precision medicine orchestrator designed for the "Last Mile" of cancer care. This agent leverages the **A2A 1.0 Protocol**, **FHIR R4**, and **mCODE** standards to provide actionable insights for Virtual Tumor Boards.

---

## 🏗️ Architecture Overview

The OCC acts as a specialized specialist agent that can be consulted by general triage bots.

- **Frontend**: Prompt Opinion Platform (BYO Agent + External Agent).
- **Backend**: FastAPI / Python Agent (A2A compliant).
- **Protocol**: JSON-RPC over A2A 1.0.
- **Data Model**: FHIR R4 (mCODE extensions for genomics and staging).

---

## 🌟 Key Features

### 1. 🔬 Precision Molecular Triage
The agent automatically scans a patient's FHIR record for **Genomic Observations** (EGFR, ALK, PD-L1). It doesn't just "read" them; it interprets their clinical significance for the MDT.

### 2. 🎯 Intelligent Trial Matching
Using a built-in precision registry, the agent matches patients to clinical trials based on both their **Disease Stage** and their **Biomarker Profile**.

### 3. 🤝 A2A Orchestration
The OCC can formally delegate tasks to other specialists (Radiology, Pathology) via structured A2A hand-offs, ensuring a collaborative care continuum.

---

## 🧪 Demo Script (How to Test)

Follow these steps to experience the full clinical power of the OCC:

### Step 1: Initialize the Environment
1. In the terminal, run: `./start.sh`
2. This will refresh the tunnel and give you a fresh **Agent Card URL**.
3. Update the **External Agent** in Prompt Opinion with this URL.

### Step 2: The Oncology Patient
1. Import `demo_oncology_patient.json` into the platform.
2. Select **Daniel K. Ochieng** (DOB: 1968-07-04).

### Step 3: The MDT Simulation
1. Start a chat with your **Clinical Triage Assistant**.
2. **Consult Specialist** → Select **Oncology_Care_Coordinator**.
3. Ask: 
   > *"What is the biomarker status for Daniel Ochieng and are there any trial matches?"*

---

## 🛠️ Tech Stack & Compliance
- **A2A v1.0**: Full manifest and security compliance.
- **Google ADK**: Powers the tool-calling and session management.
- **mCODE Implementation**: Specialized FHIR tools for oncology reports and genomic variants.
- **WOW Aesthetics**: Rich markdown tables and clinical alerts for professional readability.

---

> [!NOTE]
> **Developer**: Memusi Robi
> **Affiliation**: Strathmore University / Agents Assemble Hackathon
