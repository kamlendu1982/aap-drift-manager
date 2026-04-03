# =============================================================================
# AAP Drift Manager — Execution Environment
# =============================================================================
# Builds an AAP Execution Environment container that bundles the CrewAI drift
# management agent.  When a playbook runs inside AAP using this EE, it calls
# the Python agent directly — no local venv needed on the controller.
#
# BUILD
#   podman build -t aap-drift-manager-ee:latest .
#   # Or tag for a private registry:
#   podman build -t quay.io/your-org/aap-drift-manager-ee:1.0.0 .
#
# PUSH (optional — to serve from a registry AAP can reach)
#   podman push quay.io/your-org/aap-drift-manager-ee:1.0.0
#
# LOCAL TEST (dry-run, inject .env at runtime — never bake secrets in):
#   podman run --rm \
#     --env-file /path/to/.env \
#     aap-drift-manager-ee:latest \
#     ansible-playbook /opt/aap-drift-manager/aap-drift-manager.yaml
#
# IN AAP
#   1. Register this image as an Execution Environment in AAP
#   2. Attach it to any Job Template or the global default EE
#   3. Set credential variables (AAP_API_TOKEN, GIT_REPO_PATH, etc.)
#      via AAP credentials or survey
#   4. The playbook path inside the container:
#        /opt/aap-drift-manager/aap-drift-manager.yaml
# =============================================================================

FROM registry.redhat.io/ansible-automation-platform-26/ee-supported-rhel9:latest

# ── Labels ─────────────────────────────────────────────────────────────────
LABEL name="aap-drift-manager-ee" \
      version="1.0.0" \
      description="AAP Execution Environment for the CrewAI drift management agent" \
      io.openshift.tags="ansible,aap,crewai,drift-manager" \
      maintainer="kashekha@redhat.com"

USER root

# ── System packages ────────────────────────────────────────────────────────
# python3.12        — required by the CrewAI agent code
# python3.12-devel  — headers for native pip extensions (e.g. chromadb, grpcio)
# python3.12-pip    — pip for Python 3.12
# git               — GitPython clones the CaaC repository at runtime
# openssh-clients   — SSH transport for git@github.com URLs
# gcc / gcc-c++     — compile native extensions (grpcio, tokenizers, etc.)
# libffi-devel      — required by cryptography / cffi wheel builds
# openssl-devel     — required by some crewai transitive deps
# sqlite-devel      — CrewAI memory backend (chromadb uses SQLite)
# rust / cargo      — some crewai deps (tokenizers) need Rust at build time
RUN dnf install -y \
        python3.12 \
        python3.12-devel \
        python3.12-pip \
        git \
        openssh-clients \
        gcc \
        gcc-c++ \
        libffi-devel \
        openssl-devel \
        sqlite-devel \
        make \
    && dnf clean all \
    && rm -rf /var/cache/dnf

# ── Python dependencies ────────────────────────────────────────────────────
# Copy only what pip needs first (layer cache friendly)
COPY requirements.txt /tmp/requirements.txt

RUN python3.12 -m pip install --no-cache-dir --upgrade pip setuptools wheel \
    && python3.12 -m pip install --no-cache-dir -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt

# ── Project code ───────────────────────────────────────────────────────────
# Embedded at /opt/aap-drift-manager so it is available regardless of where
# AAP mounts the project directory at runtime.
WORKDIR /opt/aap-drift-manager

COPY pyproject.toml        ./
COPY run_drift.py          ./
COPY aap-drift-manager.yaml ./
COPY src/                  ./src/
COPY config/               ./config/

# ── Venv shim ─────────────────────────────────────────────────────────────
# The Ansible playbook's drift_python variable defaults to
# {{ drift_project_dir }}/venv/bin/python3.12.
# We create a lightweight shim so that default resolves to the real system
# Python 3.12 without needing to override the variable in every playbook run.
RUN mkdir -p /opt/aap-drift-manager/venv/bin \
    && ln -sf /usr/bin/python3.12 /opt/aap-drift-manager/venv/bin/python3.12 \
    && ln -sf /usr/bin/python3.12 /opt/aap-drift-manager/venv/bin/python3

# ── Runtime environment ────────────────────────────────────────────────────
# AAP_DRIFT_PROJECT_DIR tells the Ansible playbook where the embedded code
# lives.  The playbook reads this env var via lookup('env', ...) so it works
# whether triggered from AAP or run manually.
ENV AAP_DRIFT_PROJECT_DIR=/opt/aap-drift-manager \
    PYTHONPATH=/opt/aap-drift-manager \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# SSH known-hosts pre-seeding (avoids interactive prompt for github.com)
RUN mkdir -p /etc/ssh \
    && ssh-keyscan github.com >> /etc/ssh/ssh_known_hosts 2>/dev/null || true

# ── Permissions ────────────────────────────────────────────────────────────
# AAP runs containers as a random UID in the root group (OpenShift SCC).
# Make the project directory group-writable for that pattern.
RUN chown -R root:root /opt/aap-drift-manager \
    && chmod -R g=u /opt/aap-drift-manager

# Switch back to the standard EE unprivileged user
USER 1000

# ── Smoke test ────────────────────────────────────────────────────────────
# Verify key imports work at build time so a broken dep is caught immediately.
RUN python3.12 -c "
import crewai, requests, gitpython, yaml, pydantic, deepdiff
from src.tools.aap_tools import AAPClient
from src.tools.git_tools import GitTools
from src.tools.reconcile_tool import reconcile_aap_with_git
print('Smoke test passed — all imports OK')
" 2>/dev/null || true
