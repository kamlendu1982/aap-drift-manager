# AAP Drift Manager

An AI-powered drift management agent for Ansible Automation Platform (AAP) built with the **CrewAI** framework. The agent treats your Git repository as the single source of truth and automatically reconciles any drift — creating missing objects, updating modified ones, and deleting extras — to keep AAP in sync with your Config-as-Code (CaaC) definitions.

---

## How It Works

1. **Clone / pull** the CaaC Git repository (SSH or HTTPS URL supported)
2. **Read** desired state from `group_vars/all/` YAML files
3. **Query** live AAP state via **AAP MCP domain servers** (Model Context Protocol)
4. **Compute** drift per object type: Extra / Missing / Modified
5. **Reconcile** in strict dependency order (organizations first, job templates last)
6. **Report** every action taken with full detail

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                      Git Repository (CaaC)                           │
│                                                                      │
│  git@github.com:user/caac-aap.git                                    │
│  └── group_vars/all/                                                 │
│       ├── organizations.yml      (key: aap_organizations)            │
│       ├── credential_types.yml   (key: controller_credential_types)  │
│       ├── execution_environments.yml (key: controller_execution_...)  │
│       ├── projects.yml           (key: controller_projects)          │
│       ├── inventories.yml        (key: controller_inventories)       │
│       ├── credentials.yml        (key: controller_credentials)       │
│       ├── job_templates.yml      (key: controller_templates)         │
│       └── teams.yml              (key: aap_teams)                    │
└─────────────────────┬────────────────────────────────────────────────┘
                      │  SSH clone/pull (GitPython)
                      ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    CrewAI Orchestrator (Sequential)                  │
│                                                                      │
│  ┌────────────────┐   ┌────────────────┐   ┌──────────────────────┐  │
│  │ Git Reader     │   │ AAP Scanner    │   │ Drift Analyzer       │  │
│  │ Agent          │──▶│ Agent          │──▶│ Agent                │  │
│  │                │   │                │   │                      │  │
│  │ Reads CaaC     │   │ Queries live   │   │ Computes Extra /     │  │
│  │ desired state  │   │ AAP via MCP ★  │   │ Missing / Modified   │  │
│  └────────────────┘   └───────┬────────┘   └──────────────────────┘  │
│                               │                         │             │
│          ┌────────────────────┘                         ▼             │
│          │  AAP MCP Domain Servers                                    │
│          │  ├── /job_management/mcp         (projects, job_templates) │
│          │  ├── /platform_configuration/mcp (orgs, cred_types, EEs)  │
│          │  ├── /inventory_management/mcp   (inventories)            │
│          │  ├── /security_compliance/mcp    (credentials)            │
│          │  └── /user_management/mcp        (teams)                  │
│          │                                              │             │
│          └──────────────────────────────────────────────             │
│                                                         ▼             │
│                                             ┌──────────────────────┐  │
│                                             │ Reconciler Agent     │  │
│                                             │                      │  │
│                                             │ Calls single atomic  │  │
│                                             │ tool (no hallucin.)  │  │
│                                             └──────────┬───────────┘  │
└────────────────────────────────────────────────────────┼─────────────┘
                                                         │
                      ┌──────────────────────────────────┘
                      │  reconcile_aap_with_git() tool
                      │  (uses REST API for write operations)
                      ▼
┌──────────────────────────────────────────────────────────────────────┐
│                   AAP Controller (EC2 / RHEL)                        │
│                   API: /api/controller/v2/                           │
│                                                                      │
│   POST organizations/        POST inventories/                       │
│   POST projects/             POST job_templates/                     │
│   POST credentials/          POST teams/                             │
│   DELETE extra objects        PATCH modified objects                 │
└──────────────────────────────────────────────────────────────────────┘
```

> **★ MCP for Read, REST for Write:** The AAP Scanner agent uses the MCP protocol to
> read current AAP state. All write operations (create / update / delete) during
> reconciliation continue to use the AAP REST API directly.

---

## AAP MCP Domain Servers

The scanner agent routes each object type to the appropriate MCP domain server:

| MCP Domain | Endpoint | Object Types |
|------------|----------|-------------|
| `job_management` | `https://<host>:<port>/job_management/mcp` | `projects`, `job_templates`, `workflow_job_templates` |
| `platform_configuration` | `https://<host>:<port>/platform_configuration/mcp` | `organizations`, `credential_types`, `execution_environments` |
| `inventory_management` | `https://<host>:<port>/inventory_management/mcp` | `inventories` |
| `security_compliance` | `https://<host>:<port>/security_compliance/mcp` | `credentials` |
| `user_management` | `https://<host>:<port>/user_management/mcp` | `teams` |

Tool discovery is **dynamic** — on first use the agent calls `list_tools()` on each MCP server and caches the available tool names, so the mapping stays valid even if tool names change between MCP server versions.

---

## GitOps Flow: Git as Single Source of Truth

A push to the CaaC repository automatically triggers AAP to reconcile itself
against Git — no manual intervention required.

```
  Developer / CI·CD
  ─────────────────
  git push  (commit CaaC changes to main)
        │
        │  on: push
        ▼
┌───────────────────────────────────────────────────────────────────┐
│  GitHub — caac-aap-2.5  (Single Source of Truth)                  │
│                                                                   │
│  group_vars/all/                                                  │
│  ├── organizations.yml      key: aap_organizations                │
│  ├── credential_types.yml   key: controller_credential_types      │
│  ├── execution_environments.yml                                   │
│  ├── projects.yml           key: controller_projects              │
│  ├── inventories.yml        key: controller_inventories           │
│  ├── credentials.yml        key: controller_credentials           │
│  ├── job_templates.yml      key: controller_templates             │
│  └── teams.yml              key: aap_teams                        │
└───────────────────────────────┬───────────────────────────────────┘
                                │
                                │  GitHub Webhook  (on push to main)
                                │  POST /api/controller/v2/
                                │       job_templates/{id}/launch/
                                ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  AAP Controller                                                          │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────────┐ │
│  │  Job Template: aap_drift_manager                                    │ │
│  │                                                                     │ │
│  │  Project    : drift_manager  ← git@github.com/…/aap-drift-manager  │ │
│  │  Playbook   : aap-drift-manager.yaml                                │ │
│  │  EE         : aap-drift-manager-ee                                  │ │
│  │  Credential : aap_drift_manager_secrets (Custom Credential Type)    │ │
│  │               → injects MAAS_API_KEY and AAP_API_TOKEN as env vars  │ │
│  │  Extra Vars : endpoints, git_repo_path, guardrails, drift_apply …   │ │
│  └────────────────────────────────┬────────────────────────────────────┘ │
│                                   │  ansible-playbook aap-drift-manager.yaml
│                                   ▼                                      │
│  ┌─────────────────────────────────────────────────────────────────────┐ │
│  │  Execution Environment: aap-drift-manager-ee                        │ │
│  │  Image: quay.io/kashekha/aap-drift-manager-ee:latest                │ │
│  │                                                                     │ │
│  │  Runtime deps: Python 3.12, crewai[litellm], mcp, httpx, …         │ │
│  │  Source code:  mounted at /runner/project/ from Git Project         │ │
│  │                                                                     │ │
│  │  Playbook tasks:                                                    │ │
│  │    1. Write /runner/project/.env                                    │ │
│  │       (secrets from credential + endpoints from extra_vars)         │ │
│  │    2. python3.12 run_drift.py                                       │ │
│  │                                                                     │ │
│  │  ┌───────────────────────────────────────────────────────────────┐  │ │
│  │  │  CrewAI Agent  ←── MaaS LLM  (Llama 4 Scout 17B via litellm) │  │ │
│  │  │                                                               │  │ │
│  │  │  Step 1  Clone / pull  caac-aap-2.5                          │  │ │
│  │  │  Step 2  Read desired state from group_vars/all/             │  │ │
│  │  │  Step 3  Query AAP MCP servers for current state  ★          │  │ │
│  │  │            job_management / platform_configuration /          │  │ │
│  │  │            inventory_management / security_compliance /        │  │ │
│  │  │            user_management                                    │  │ │
│  │  │  Step 4  Compute drift per object type                       │  │ │
│  │  │            MISSING  → schedule CREATE                         │  │ │
│  │  │            EXTRA    → schedule DELETE  (guardrails apply)     │  │ │
│  │  │            MODIFIED → schedule UPDATE                         │  │ │
│  │  │  Step 5  Apply in dependency order (REST API):               │  │ │
│  │  │            organizations → credential_types →                 │  │ │
│  │  │            execution_environments →                           │  │ │
│  │  │            projects / inventories →                           │  │ │
│  │  │            credentials → job_templates → teams                │  │ │
│  │  └───────────────────────────────┬───────────────────────────────┘  │ │
│  └─────────────────────────────────  ┼ ──────────────────────────────┘ │
│                                      │  AAP REST API calls              │
│                                      │  /api/controller/v2/…/           │
│  ┌───────────────────────────────────▼──────────────────────────────┐   │
│  │  AAP Objects  (guaranteed to match Git after every run)          │   │
│  │                                                                  │   │
│  │   ✓ Created  — objects defined in Git but absent from AAP        │   │
│  │   ✓ Updated  — objects that differ from their Git definition      │   │
│  │   ✓ Deleted  — objects in AAP with no corresponding Git entry    │   │
│  │   ⚠ Skipped  — protected types / names (credentials, Default …) │   │
│  └──────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────────┘
```

### Setting Up the Webhook

1. In AAP — create a **Webhook Credential** (type: GitHub) and attach it to the `aap_drift_manager` Job Template with **Webhook Service: GitHub**. AAP generates a unique Webhook URL and key.

2. In GitHub — go to `caac-aap-2.5` → **Settings → Webhooks → Add webhook**:
   - **Payload URL**: the AAP webhook URL from step 1
   - **Content type**: `application/json`
   - **Secret**: the webhook key from step 1
   - **Events**: `push` (or filter to specific branches)

3. Every `git push` to `main` will now automatically trigger a drift reconciliation run.

### Anti-Hallucination Design

The Reconciler agent calls a **single atomic Python tool** (`reconcile_aap_with_git`) that handles the entire workflow internally: read Git, read AAP, compute drift, apply changes. This eliminates any possibility of the LLM fabricating actions or skipping steps — the tool either runs end-to-end or raises an exception.

---

## Dependency-Aware Reconciliation Order

Objects are always processed in this order to satisfy AAP's foreign-key requirements:

| Order | Object Type | Depends On |
|-------|-------------|------------|
| 1 | `organizations` | — |
| 2 | `credential_types` | — |
| 3 | `execution_environments` | credentials (optional) |
| 4 | `projects` | organizations |
| 4 | `inventories` | organizations |
| 5 | `credentials` | organizations, credential_types |
| 6 | `job_templates` | projects, inventories, credentials, EEs |
| 7 | `teams` | organizations |

Name-to-ID resolution is automatic — e.g. `organization: "config_as_code"` in YAML is resolved to the correct integer ID before the API call.

---

## Project Structure

```
aap-drift-manager/
├── .env                          # Environment variables (see below)
├── run_drift.py                  # Direct entry point script
├── pyproject.toml
├── requirements.txt
│
└── src/
    ├── main.py                   # CLI entry point (typer + rich)
    ├── config.py                 # Settings (pydantic-settings, loads .env)
    │
    ├── agents/
    │   ├── git_reader.py         # Reads CaaC from Git
    │   ├── aap_scanner.py        # Queries live AAP state via MCP ★
    │   ├── drift_analyzer.py     # Compares desired vs actual
    │   └── reconciler.py         # Applies changes (uses reconcile_aap_with_git)
    │
    ├── tools/
    │   ├── git_tools.py          # Clone/pull Git repo; read group_vars/all/
    │   ├── mcp_tools.py          # MCP client for AAP read operations ★
    │   ├── aap_tools.py          # AAPClient: CRUD via /api/controller/v2/
    │   ├── diff_tools.py         # find_drift() using deepdiff
    │   └── reconcile_tool.py     # Atomic reconcile_aap_with_git() tool
    │
    ├── models/
    │   ├── aap_objects.py        # ObjectType, CAAC_FILE_MAP, DEPENDENCY_FIELD_MAP,
    │   │                         # ASSOCIATION_FIELD_MAP, CAAC_TO_API_FIELD_MAP
    │   └── drift_report.py       # DriftResult, FieldDiff models
    │
    └── crew/
        └── drift_crew.py         # DriftManagementCrew (4 agents, sequential)
```

---

## Installation

```bash
git clone <this-repo>
cd aap-drift-manager

# Python 3.12 required
python3.12 -m venv venv
source venv/bin/activate

pip install -r requirements.txt
```

> **Note:** If your system has multiple Python versions, activate the venv explicitly:
> `venv/bin/python3.12 run_drift.py`

---

## Configuration (.env)

```bash
# ── LLM (required for CrewAI agents) ──────────────────────────────
# Option A: Red Hat MaaS (Llama 4)
MAAS_API_KEY=your_maas_api_key
MAAS_API_BASE=https://your-maas-endpoint/v1
MAAS_MODEL=llama-4-scout-17b-16e-w4a16

# Option B: OpenAI
OPENAI_API_KEY=your_openai_key
# OPENAI_MODEL_NAME=gpt-4o

# ── AAP Controller ─────────────────────────────────────────────────
AAP_MCP_SERVER_URL=https://your-aap-controller.example.com
# OR: AAP_URL=https://your-aap-controller.example.com

AAP_API_TOKEN=your_aap_api_token
# OR: AAP_TOKEN=your_aap_api_token

AAP_VERIFY_SSL=false          # Set true in production with valid certs

# ── AAP MCP Domain Servers ─────────────────────────────────────────
# Port on which the AAP MCP servers are listening.
# The scanner agent connects to:
#   https://<AAP_MCP_SERVER_URL>:<AAP_MCP_PORT>/job_management/mcp
#   https://<AAP_MCP_SERVER_URL>:<AAP_MCP_PORT>/platform_configuration/mcp
#   https://<AAP_MCP_SERVER_URL>:<AAP_MCP_PORT>/inventory_management/mcp
#   https://<AAP_MCP_SERVER_URL>:<AAP_MCP_PORT>/security_compliance/mcp
#   https://<AAP_MCP_SERVER_URL>:<AAP_MCP_PORT>/user_management/mcp
AAP_MCP_PORT=443              # Default 443; change if MCP runs on a custom port

# ── Git CaaC Repository ────────────────────────────────────────────
GIT_REPO_PATH=git@github.com:your-org/caac-aap.git  # SSH URL
# OR local path: GIT_REPO_PATH=/home/user/caac-aap
GIT_BRANCH=main

# ── Agent Behaviour ────────────────────────────────────────────────
DRY_RUN=true       # true = report only, false = apply changes to AAP
LOG_LEVEL=INFO

# ── Safety Guardrails ──────────────────────────────────────────────
NO_DELETE_TYPES=credentials        # Never delete objects of these types
PROTECTED_OBJECTS=Default          # Never delete objects with these names
```

### SSH for Git

When using an SSH Git URL, the tool clones to `/tmp/aap-drift-caac-<hash>/` automatically. Ensure your SSH key is loaded:

```bash
eval $(ssh-agent -s)
ssh-add ~/.ssh/id_rsa
```

---

## Running

### Recommended: direct Python entry point

```bash
# Dry run — show what would change, apply nothing
DRY_RUN=true venv/bin/python3.12 run_drift.py

# Apply all changes
DRY_RUN=false venv/bin/python3.12 run_drift.py
# or equivalently:
venv/bin/python3.12 run_drift.py --apply

# Reconcile only specific object types
venv/bin/python3.12 run_drift.py --objects organizations,projects,job_templates
```

### Via Python import

```python
from src.main import run_drift_management

run_drift_management()
```

### Via CLI (typer)

```bash
venv/bin/python3.12 -m src.main drift
venv/bin/python3.12 -m src.main drift --dry-run
venv/bin/python3.12 -m src.main drift --objects projects,job_templates
```

---

## CaaC Repository Structure

This tool expects the CaaC repo to follow the `redhat-cop/controller_configuration` collection layout with all files under `group_vars/all/`:

```
caac-aap/
└── group_vars/
    └── all/
        ├── organizations.yml           # key: aap_organizations
        ├── credential_types.yml        # key: controller_credential_types
        ├── execution_environments.yml  # key: controller_execution_environments
        ├── projects.yml                # key: controller_projects
        ├── inventories.yml             # key: controller_inventories
        ├── credentials.yml             # key: controller_credentials
        ├── job_templates.yml           # key: controller_templates
        └── teams.yml                   # key: aap_teams
```

> The inconsistent YAML key prefixes (`aap_` vs `controller_`) are handled automatically by `CAAC_FILE_MAP` in `aap_objects.py`.

Example `job_templates.yml`:
```yaml
controller_templates:
  - name: controller_config
    project: config_as_code
    job_type: run
    playbook: sample_playbooks/access_config_from_git.yml
    inventory: config_as_code
    execution_environment: supported
    concurrent_jobs_enabled: false
    ask_variables_on_launch: true
    verbosity: 0
    credentials:
      - aap_admin
      - vault
```

---

## Supported Object Types

| Object Type | Read (MCP) | Create | Update | Delete | Notes |
|-------------|:----------:|:------:|:------:|:------:|-------|
| `organizations` | ✅ | ✅ | ✅ | ✅ | `galaxy_credentials` associated via sub-endpoint |
| `credential_types` | ✅ | ✅ | ✅ | ✅ | Built-in managed types are never deleted |
| `execution_environments` | ✅ | ⚠️ | ✅ | ⚠️ | Require real image URL (Jinja2 templates stripped) |
| `projects` | ✅ | ✅ | ✅ | ✅ | |
| `inventories` | ✅ | ✅ | ✅ | ✅ | |
| `credentials` | ✅ | ✅ | ✅ | ✅ | `inputs` with Jinja2 stored literally |
| `job_templates` | ✅ | ✅ | ✅ | ✅ | `credentials` associated via sub-endpoint |
| `teams` | ✅ | ✅ | ✅ | ✅ | |

---

## Known Limitations

### Jinja2 Templates in CaaC
If your CaaC uses Ansible variable references like `{{ ah_hostname }}` inside field values (common in `execution_environments.yml` for image URLs and `credentials.yml` for input fields), those values are **automatically stripped** before the API call. This prevents API errors but means:

- **Execution Environments** with templated `image:` URLs cannot be auto-created. Add the actual image URL to your CaaC or pre-create EEs manually in AAP.
- **Credential inputs** with templated secrets are sent literally (stored as-is in AAP). They can be updated later via the AAP UI.

### System / Protected Objects
Objects protected by AAP (e.g. `Control Plane Execution Environment`, `Ansible Galaxy` credential) return `403 Forbidden` on DELETE and are automatically marked as **skipped** (not errors).

### Second-pass Dependencies
When `organizations.default_environment` references an EE that doesn't exist yet, the field is silently dropped on first run. Run the agent again after EEs are created to populate this field.

### MCP Server Availability
The scanner agent requires the AAP MCP domain servers to be reachable at `AAP_MCP_PORT`. If a domain server is down, the agent will report an error for those object types but the reconciler will still attempt to proceed with any data already gathered.

---

## Safety Features

| Feature | Behaviour |
|---------|-----------|
| **Dry-run mode** | `DRY_RUN=true` reports all planned changes without touching AAP |
| **MCP read / REST write separation** | AAP state is read via MCP (read-only); writes go through the REST API with full validation |
| **System object protection** | 403 responses on DELETE are treated as "skipped", not errors |
| **Jinja2 stripping** | Fields with `{{ ... }}` are removed before API calls to prevent rejections |
| **Protected names list** | Set `PROTECTED_OBJECTS` in `.env` to prevent deletion of specific objects |
| **No-delete types** | Set `NO_DELETE_TYPES` in `.env` to skip deletion for entire object categories |
| **Dependency ordering** | Objects are always created in foreign-key safe order |
| **SSL control** | `AAP_VERIFY_SSL=false` for self-signed certs (set `true` in production) |

---

## Example Output

```
Reconciling 8 object types …

── organizations ──
  Git: 2 objects
  AAP: 0 objects  (queried via MCP: platform_configuration)
  Drift → 0 extra, 2 missing, 0 modified
  ✓ Created organizations/config_as_code (ID: 3)
  ✓ Created organizations/windows_usecase (ID: 4)

── execution_environments ──
  Git: 2 objects
  AAP: 0 objects  (queried via MCP: platform_configuration)
  Drift → 0 extra, 2 missing, 0 modified
  [warn] Removing field 'image' — contains unresolved Jinja2 template
  ✗ Failed to create execution_environments/supported: 400 - {'image': ['This field may not be blank.']}

── projects ──
  Git: 2 objects
  AAP: 0 objects  (queried via MCP: job_management)
  Drift → 0 extra, 2 missing, 0 modified
  ✓ Created projects/config_as_code (ID: 8)
  ✓ Created projects/windows_usecases (ID: 9)

── inventories ──
  Git: 2 objects
  AAP: 0 objects  (queried via MCP: inventory_management)
  Drift → 0 extra, 2 missing, 0 modified
  ✓ Created inventories/config_as_code (ID: 5)
  ✓ Created inventories/windows (ID: 6)

============================================================
Reconciliation Complete [APPLIED]
============================================================
  Created : 6
  Updated : 0
  Deleted : 0
  Skipped : 0
  Errors  : 2
```

---

## Related Projects

- [redhat-cop/controller_configuration](https://github.com/redhat-cop/controller_configuration) — AAP Config-as-Code Ansible collection (CaaC format this tool reads)
- [crewAI](https://github.com/joaomdmoura/crewAI) — Multi-agent orchestration framework
- [modelcontextprotocol/python-sdk](https://github.com/modelcontextprotocol/python-sdk) — MCP Python SDK used for AAP state queries
- [ansible/awx](https://github.com/ansible/awx) — Open-source AWX (upstream of AAP)

---

Built for Red Hat Ansible Automation Platform drift management using the CrewAI agentic framework.
