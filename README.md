# About This Project

This project is a scalable, retry-resilient multi-agent AI system designed to drastically optimize reading and extraction times in IT recruitment. Built on a hub-and-spoke architecture, it processes both unstructured IT resumes and job postings to establish a unified taxonomy. The system extracts technical skills, soft skills, certifications, and languages in parallel while inferring seniority and experience, ultimately consolidating standardized profiles into a Redis database to eliminate manual review and power downstream automation.

## Core Workflow

The architecture executes through five automated phases:

*   **1. Async Intake & Triage:** Automatically ingests and classifies resumes and job postings without manual formatting, assigning tracking IDs and preparing the context for asynchronous processing.
*   **2. Parallel Skill Extraction:** A central coordinator dispatches sub-agents in parallel to concurrently extract technical skills, soft skills, languages, and certifications, while automatically inferring the candidate's seniority level and years of experience.
*   **3. Common Language Alignment:** Translates every profile and vacancy from its raw source into a unified taxonomy of competencies and proficiency levels, eliminating wording ambiguities to guarantee standardized data.
*   **4. Quality Guardrails & Observability:** Automated checks audit each extraction to catch incomplete data and execute intelligent retries before proceeding, all while emitting real-time telemetry on the execution flow.
*   **5. Consolidation & Persistence:** A consolidation agent merges the validated outputs into a structured database profile, providing immediate visibility to recruiters and enabling direct consumption by downstream automation systems.

## Tech Stack Highlights

*   **Routing & Orchestration:** Asynchronous REST API with FastAPI, initial routing via Claude Agent SDK, and a Coordinator Guardrails module.
*   **Validation:** Orchestration prompts enforced by a single reference dictionary and strict data contract validation using Pydantic.
*   **State & Persistence:** Consolidator agent state management in Redis coupled with robust database persistence.

## Project Repositories

This project consists of three GitHub repositories, each with specific responsibilities and reusable libraries:

*   **[Talent Distiller Agent](https://github.com/albertbolanoss/talent_distiller_agent)**: The main application responsible for exposing the document upload endpoint and initiating the coordinator agent workflow (Hub-and-Spoke architecture).
*   **[mcp_skills_extractor_agents](https://github.com/albertbolanoss/mcp_skills_extractor_agents)**: The MCP server that grants access to the specialized agent workflow for competency extraction (technical skills, soft skills, certifications, and languages).
*   **[labs-agent-lib](https://github.com/albertbolanoss/labs-agent-lib)**: A shared library containing common utilities and shared code for managing projects built with Claude agents.

**Clone or download the repositories listed above into a specific folder**:

```sh
# Command to clone from github the repositories:

git clone https://github.com/albertbolanoss/talent_distiller_agent.git
git clone https://github.com/albertbolanoss/mcp_skills_extractor_agents.git
git clone https://github.com/albertbolanoss/labs-agent-lib
```

### How to run it based on the selected mode

There are three ways to run it

1. [Development mode](./doc/how_run_as_development_mode.md): Install the tools on the machine and in the virtual environment to run the services using Python 3.14
1. [Deployment mode](./helm/talent-distiller-agent/README.md): Use Kubernetes cluster or Minikube or Rancher Desktop with kubernetes plugin to deploy and scale the application. 


## How to Start Uploading Documents

After running the application in a specific mode, you can start using it to upload your documents in the following formats: (pdf, docx, md, txt).

The API exposes one upload endpoint per document type. Both accept a multipart `POST` request with the file in the `file` field, and store it in the directory the background process polls for extraction. You can try them with the sample files under [`document_samples/`](./document_samples):

*   **Resumes** — `POST /resume`, saved into `resume_dir`:

    ```sh
    curl -X POST http://localhost:8080/resume \
      -F "file=@document_samples/resume_sample.txt"
    ```

*   **Job postings** — `POST /job_posting`, saved into `job_posting_dir`:

    ```sh
    curl -X POST http://localhost:8080/job_posting \
      -F "file=@document_samples/job_posting_sample.txt"
    ```
