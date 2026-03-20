# AAP Drift Manager

An AI-powered drift management agent for Ansible Automation Platform (AAP) using CrewAI. This agent ensures your AAP instance stays in sync with your Git-based Config-as-Code definitions by detecting and automatically reconciling configuration drift.

## Overview

When teams manage AAP through both Config-as-Code (CaC) and the UI/API directly, configuration drift inevitably occurs. Someone edits a Job Template through the UI, adds a credential manually, or tweaks a project setting — and suddenly your Git repository no longer reflects reality.

This agent solves that problem by:
1. Reading your desired state from Git (YAML/JSON config files)
2. Scanning the live AAP instance via API
3. Detecting differences (drift) between desired and actual state
4. Reconciling drift by modifying or deleting objects to match Git

## Architecture

```
┌─────────────────────┐                    ┌─────────────────────┐
│   Git Repository    │                    │    AAP Instance     │
│  (Config as Code)   │                    │   (Live State)      │
│                     │                    │                     │
│  - organizations/   │                    │  URL + Token from   │
│  - projects/        │                    │  .env file          │
│  - job_templates/   │                    │                     │
│  - credentials/     │                    │                     │
│  - inventories/     │                    │                     │
└─────────┬───────────┘                    └──────────┬──────────┘
          │                                           │
          │                                           │
          ▼                                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                     CrewAI Orchestrator                         │
│                                                                 │
│  ┌─────────────────┐          ┌─────────────────┐              │
│  │ Git Reader      │          │ AAP Scanner     │              │
│  │ Agent           │          │ Agent           │              │
│  │                 │          │                 │              │
│  │ Parse CaC YAML  │          │ Fetch live      │              │
│  │ files           │          │ objects via API │              │
│  └────────┬────────┘          └────────┬────────┘              │
│           │                            │                        │
│           └──────────┬─────────────────┘                        │
│                      ▼                                          │
│           ┌─────────────────┐                                   │
│           │ Drift Analyzer  │                                   │
│           │ Agent           │                                   │
│           │                 │                                   │
│           │ Compare states, │                                   │
│           │ identify drift  │                                   │
│           └────────┬────────┘                                   │
│                    │                                            │
│                    ▼                                            │
│           ┌─────────────────┐                                   │
│           │ Reconciler      │───────────────────────────────────┼──► AAP API
│           │ Agent           │         PATCH / DELETE            │
│           │                 │                                   │
│           │ Fix drift       │                                   │
│           └─────────────────┘                                   │
│                                                                 │
│  Tools: git_tools.py | aap_tools.py | diff_tools.py            │
└─────────────────────────────────────────────────────────────────┘
```

## Features

- **Multi-object support**: Projects, Job Templates, Workflow Job Templates, Inventories, Credentials, Organizations, Teams, Settings
- **Three drift types detected**:
  - **Extra objects**: Exist in AAP but not in Git (can be deleted)
  - **Missing objects**: Exist in Git but not in AAP (can be created)
  - **Modified objects**: Exist in both but with different configurations (can be updated)
- **Dry-run mode**: Preview changes before applying
- **Selective reconciliation**: Choose which object types to sync
- **Detailed reporting**: See exactly what changed and why

## Project Structure

```
aap_drift_manager/
├── .env.example              # Template for environment variables
├── .gitignore
├── README.md
├── requirements.txt
├── pyproject.toml
│
├── src/
│   ├── __init__.py
│   ├── main.py               # Entry point
│   ├── config.py             # Configuration loader
│   │
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── git_reader.py     # Git Reader Agent
│   │   ├── aap_scanner.py    # AAP Scanner Agent
│   │   ├── drift_analyzer.py # Drift Analyzer Agent
│   │   └── reconciler.py     # Reconciler Agent
│   │
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── git_tools.py      # Git/file operations
│   │   ├── aap_tools.py      # AAP API operations
│   │   └── diff_tools.py     # Comparison utilities
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── aap_objects.py    # Pydantic models for AAP objects
│   │   └── drift_report.py   # Drift report models
│   │
│   └── crew/
│       ├── __init__.py
│       └── drift_crew.py     # CrewAI crew definition
│
├── config/
│   └── objects.yaml          # Object type configurations
│
└── tests/
    ├── __init__.py
    ├── test_git_tools.py
    ├── test_aap_tools.py
    └── test_drift_analyzer.py
```

## Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/aap_drift_manager.git
cd aap_drift_manager

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or
.\venv\Scripts\activate   # Windows

# Install dependencies
pip install -r requirements.txt

# Copy and configure environment variables
cp .env.example .env
# Edit .env with your AAP credentials and Git repo path
```

## Configuration

### Environment Variables (.env)

```bash
# AAP Configuration
AAP_URL=https://your-aap-controller.example.com
AAP_TOKEN=your_api_token_here
# OR use username/password
# AAP_USERNAME=admin
# AAP_PASSWORD=your_password

# Git Configuration
GIT_REPO_PATH=/path/to/your/config-as-code/repo
GIT_BRANCH=main

# Optional: OpenAI API Key for CrewAI
OPENAI_API_KEY=your_openai_key
# OR use local models
# OPENAI_API_BASE=http://localhost:11434/v1
# OPENAI_MODEL_NAME=llama3

# Agent Configuration
DRY_RUN=true                    # Set to false to apply changes
LOG_LEVEL=INFO
```

### Config-as-Code Structure (Git Repo)

Your Git repository should follow this structure:

```
aap-config/
├── organizations/
│   └── default.yaml
├── projects/
│   ├── demo_project.yaml
│   └── network_automation.yaml
├── job_templates/
│   ├── patch_servers.yaml
│   └── backup_configs.yaml
├── workflow_job_templates/
│   └── full_deployment.yaml
├── inventories/
│   ├── production.yaml
│   └── development.yaml
├── credentials/
│   └── machine_creds.yaml      # Note: secrets not stored here
└── settings/
    └── jobs.yaml
```

Example `job_templates/patch_servers.yaml`:

```yaml
name: Patch Servers
description: Apply security patches to all servers
project: Demo Project
playbook: playbooks/patch.yml
inventory: Production
credential: Machine Credentials
job_type: run
verbosity: 1
extra_vars:
  reboot_allowed: true
```

## Usage

### Basic Usage

```bash
# Dry run - show what would change
python -m src.main --dry-run

# Apply changes
python -m src.main

# Specific object types only
python -m src.main --objects projects,job_templates

# Verbose output
python -m src.main --verbose
```

### Python API

```python
from src.crew.drift_crew import DriftManagementCrew

# Initialize the crew
crew = DriftManagementCrew(
    git_repo_path="/path/to/config",
    aap_url="https://aap.example.com",
    aap_token="your_token",
    dry_run=True
)

# Run drift detection and reconciliation
result = crew.run()

# Access the report
print(result.drift_report)
print(f"Objects with drift: {len(result.drifted_objects)}")
print(f"Actions taken: {len(result.actions_taken)}")
```

## Agents

### 1. Git Reader Agent

**Role**: Parse and understand Config-as-Code definitions

**Responsibilities**:
- Clone/pull the Git repository
- Parse YAML/JSON configuration files
- Normalize object definitions to a standard format
- Build a desired state dictionary

**Tools**:
- `read_git_directory`: List files in the config repo
- `parse_yaml_file`: Parse a single YAML file
- `get_all_definitions`: Get all object definitions by type

### 2. AAP Scanner Agent

**Role**: Discover the current state of the AAP instance

**Responsibilities**:
- Authenticate with AAP API
- Fetch all objects of each type
- Normalize API responses to match Git format
- Build a current state dictionary

**Tools**:
- `list_aap_objects`: List all objects of a given type
- `get_aap_object`: Get details of a specific object
- `get_aap_settings`: Get AAP settings

### 3. Drift Analyzer Agent

**Role**: Compare desired vs actual state and identify drift

**Responsibilities**:
- Compare Git definitions with AAP objects
- Identify extra objects (in AAP, not in Git)
- Identify missing objects (in Git, not in AAP)
- Identify modified objects (different configurations)
- Generate a detailed drift report

**Tools**:
- `compare_objects`: Deep compare two object definitions
- `generate_diff`: Generate human-readable diff
- `classify_drift`: Categorize drift by severity

### 4. Reconciler Agent

**Role**: Apply changes to bring AAP in sync with Git

**Responsibilities**:
- Review drift report
- Decide on appropriate actions
- Apply changes via AAP API
- Verify changes were successful
- Generate reconciliation report

**Tools**:
- `create_aap_object`: Create a new object
- `update_aap_object`: Update an existing object
- `delete_aap_object`: Delete an extra object
- `verify_object_state`: Confirm object matches expected state

## Object Types Supported

| Object Type | Create | Update | Delete | Notes |
|-------------|--------|--------|--------|-------|
| Organizations | ✅ | ✅ | ✅ | |
| Projects | ✅ | ✅ | ✅ | |
| Inventories | ✅ | ✅ | ✅ | Hosts managed separately |
| Credentials | ✅ | ✅ | ⚠️ | Secrets not compared |
| Job Templates | ✅ | ✅ | ✅ | |
| Workflow Job Templates | ✅ | ✅ | ✅ | |
| Teams | ✅ | ✅ | ✅ | |
| Settings | N/A | ✅ | N/A | Update only |

## Safety Features

1. **Dry-run by default**: No changes applied unless explicitly requested
2. **Object protection**: Mark objects as protected in Git to prevent deletion
3. **Confirmation prompts**: Interactive mode asks before destructive actions
4. **Rollback support**: Keep track of changes for potential rollback
5. **Audit logging**: All actions logged with timestamps

## Example Output

```
$ python -m src.main --dry-run

🔍 AAP Drift Manager - Starting drift detection...

📂 Reading Git repository: /home/user/aap-config
   Found 12 object definitions across 5 types

🔗 Connecting to AAP: https://aap.example.com
   Found 15 objects across 5 types

📊 Drift Analysis Results:
   ══════════════════════════════════════════════════

   EXTRA OBJECTS (in AAP, not in Git):
   ├── job_templates/test_template (will be deleted)
   └── projects/old_project (will be deleted)

   MISSING OBJECTS (in Git, not in AAP):
   └── job_templates/new_deployment (will be created)

   MODIFIED OBJECTS:
   └── job_templates/patch_servers
       ├── verbosity: 0 → 1
       └── extra_vars.reboot_allowed: false → true

   ══════════════════════════════════════════════════
   Summary: 2 extra, 1 missing, 1 modified

⚠️  DRY RUN MODE - No changes applied
   Run with --apply to execute changes
```

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

MIT License - see LICENSE file for details

## Related Projects

- [ansible/awx](https://github.com/ansible/awx) - AWX Project
- [redhat-cop/controller_configuration](https://github.com/redhat-cop/controller_configuration) - AAP Config as Code collection
- [crewAI](https://github.com/joaomdmoura/crewAI) - CrewAI Framework

## Author

Built for Red Hat Ansible Automation Platform drift management.
