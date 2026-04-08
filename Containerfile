# =============================================================================
# AAP Drift Manager - Execution Environment
# =============================================================================
# This image contains ONLY runtime dependencies.
# The agent source code (src/, run_drift.py, aap-drift-manager.yaml) is NOT
# embedded here - it is checked out from Git by AAP when the Job Template runs.
#
# BUILD
#   podman login registry.redhat.io        # required for the base image
#   podman build -t aap-drift-manager-ee:latest .
#
# PUSH to a registry that AAP can reach:
#   podman push <registry>/aap-drift-manager-ee:latest
#
# IN AAP
#   1. Create a Git "Project" pointing at your aap-drift-manager repo
#   2. Register this image as an Execution Environment
#   3. Create a Job Template:
#        - Project   : the Git project above
#        - Playbook  : aap-drift-manager.yaml
#        - EE        : aap-drift-manager-ee
#   4. Set secrets (AAP_API_TOKEN, MAAS_API_KEY, GIT_REPO_PATH, etc.)
#      via AAP Credentials or extra_vars - never bake them into the image.
# =============================================================================

FROM registry.redhat.io/ansible-automation-platform-26/ee-supported-rhel9:latest

LABEL name="aap-drift-manager-ee" \
      version="1.0.0" \
      description="Runtime EE for the AAP drift management agent (source comes from Git)" \
      maintainer="kamlendu.shekhar@gmail.com"

USER root

# ---------------------------------------------------------
# System packages
# ---------------------------------------------------------
# python3.12 / python3.12-devel / python3.12-pip
#   The agent code targets Python 3.12.
# git / openssh-clients
#   GitPython clones the CaaC repo at runtime; SSH needed for git@ URLs.
# gcc / gcc-c++ / libffi-devel / openssl-devel / make
#   Required to compile native Python extension wheels (crewai transitive deps).
# sqlite-devel
#   CrewAI uses SQLite for its internal task-output storage.
# ---------------------------------------------------------
RUN microdnf install -y \
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
    && microdnf clean all \
    && rm -rf /var/cache/dnf

# ---------------------------------------------------------
# Python dependencies
# ---------------------------------------------------------
# Copy only requirements.txt (not source code) to keep image lean.
# The file is removed after pip install so it is not shipped in the image.
# ---------------------------------------------------------
COPY requirements.txt /tmp/requirements.txt

RUN python3.12 -m pip install --no-cache-dir --upgrade pip setuptools wheel \
    && python3.12 -m pip install --no-cache-dir -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt

# ---------------------------------------------------------
# SQLite compatibility patch (sitecustomize.py)
# ---------------------------------------------------------
# RHEL9 ships with SQLite 3.34.x, but ChromaDB (pulled in by crewai) requires
# SQLite >= 3.35.0.  pysqlite3-binary bundles its own modern SQLite and is
# already installed via requirements.txt.
#
# sitecustomize.py is executed automatically by Python before any other code,
# so replacing sys.modules['sqlite3'] here ensures every import of sqlite3
# (including chromadb's) gets the bundled 3.35+ version.
# ---------------------------------------------------------
RUN python3.12 -c "\
import site, pathlib; \
sitedir = site.getsitepackages()[0]; \
pathlib.Path(sitedir + '/sitecustomize.py').write_text(\
'# Auto-generated: patch sqlite3 with pysqlite3-binary for ChromaDB compatibility.\n'\
'try:\n'\
'    import pysqlite3 as _pysqlite3\n'\
'    import sys\n'\
'    sys.modules[\"sqlite3\"] = _pysqlite3\n'\
'except ImportError:\n'\
'    pass\n'\
)"

# ---------------------------------------------------------
# SSH known hosts
# ---------------------------------------------------------
# Pre-seed github.com fingerprint so runtime git clones do not hang
# waiting for an interactive host-key prompt.
# ---------------------------------------------------------
RUN mkdir -p /etc/ssh \
    && ssh-keyscan github.com >> /etc/ssh/ssh_known_hosts 2>/dev/null || true

# ---------------------------------------------------------
# Runtime environment
# ---------------------------------------------------------
# PYTHONPATH is left empty here intentionally.
# AAP mounts the checked-out project at /runner/project and sets the working
# directory there, so "import src.xxx" works without any path tricks.
# ---------------------------------------------------------
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Switch to the standard EE unprivileged user
USER 1000

# ---------------------------------------------------------
# Smoke test
# ---------------------------------------------------------
# Verify all installed packages (including the sqlite3 patch) work correctly.
# No || true - a real import failure breaks the build immediately.
# ---------------------------------------------------------
RUN python3.12 -c "\
import crewai, requests, git, yaml, pydantic, deepdiff, pydantic_settings; \
import sqlite3; \
assert sqlite3.sqlite_version_info >= (3, 35, 0), \
    'SQLite too old: ' + sqlite3.sqlite_version + ' (need >= 3.35.0)'; \
print('EE smoke test passed - sqlite3 ' + sqlite3.sqlite_version + ' - all deps OK')"
