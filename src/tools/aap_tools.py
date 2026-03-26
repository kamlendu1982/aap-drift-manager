"""AAP API tools for interacting with Ansible Automation Platform."""

import re
from typing import Any, Dict, List, Optional

import requests
from crewai.tools import tool

_JINJA2_RE = re.compile(r'\{\{.*?\}\}')

from src.config import get_settings
from src.models import (
    ASSOCIATION_FIELD_MAP,
    CAAC_STRIP_FIELDS,
    CAAC_TO_API_FIELD_MAP,
    DEPENDENCY_FIELD_MAP,
    OBJECT_TYPE_ENDPOINTS,
    ObjectType,
)


class AAPClient:
    """Client for interacting with the AAP Controller API."""

    def __init__(
        self,
        url: Optional[str] = None,
        token: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        verify_ssl: Optional[bool] = None,   # None → fall back to settings
    ):
        settings = get_settings()
        self.base_url = (url or settings.aap_url).rstrip("/")
        self.token = token or settings.aap_token
        self.username = username or settings.aap_username
        self.password = password or settings.aap_password
        self.verify_ssl = verify_ssl if verify_ssl is not None else settings.aap_verify_ssl
        self._session: Optional[requests.Session] = None

    @property
    def session(self) -> requests.Session:
        if self._session is None:
            s = requests.Session()
            s.verify = self.verify_ssl
            if self.token:
                s.headers["Authorization"] = f"Bearer {self.token}"
            elif self.username and self.password:
                s.auth = (self.username, self.password)
            s.headers["Content-Type"] = "application/json"
            self._session = s
        return self._session

    def _get_endpoint(self, object_type: str) -> str:
        return OBJECT_TYPE_ENDPOINTS.get(object_type, f"/api/v2/{object_type}/")

    def _request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict] = None,
        params: Optional[Dict] = None,
    ) -> requests.Response:
        url = f"{self.base_url}{endpoint}"
        response = self.session.request(method=method, url=url, json=data, params=params)
        response.raise_for_status()
        return response

    # ── Basic CRUD ─────────────────────────────────────────────────────────────

    def list_objects(self, object_type: str, page_size: int = 200) -> List[Dict[str, Any]]:
        """List all objects of a given type (handles pagination)."""
        endpoint = self._get_endpoint(object_type)
        objects: List[Dict[str, Any]] = []
        next_url: Optional[str] = endpoint

        while next_url:
            if next_url.startswith("http"):
                resp = self.session.get(next_url, params={"page_size": page_size})
            else:
                resp = self._request("GET", next_url, params={"page_size": page_size})
            resp.raise_for_status()
            body = resp.json()
            objects.extend(body.get("results", []))
            next_url = body.get("next")

        # For credential_types, filter out built-in (managed) entries
        if object_type == ObjectType.CREDENTIAL_TYPE:
            objects = [o for o in objects if not o.get("managed", False)]

        return objects

    def get_object_by_name(self, object_type: str, name: str) -> Optional[Dict[str, Any]]:
        endpoint = self._get_endpoint(object_type)
        resp = self._request("GET", endpoint, params={"name": name})
        results = resp.json().get("results", [])
        return results[0] if results else None

    def resolve_name_to_id(self, object_type: str, name: str) -> Optional[int]:
        obj = self.get_object_by_name(object_type, name)
        return obj["id"] if obj else None

    def get_current_state(self, object_types: List[str]) -> Dict[str, Dict[str, Dict[str, Any]]]:
        return {t: {o["name"]: o for o in self.list_objects(t)} for t in object_types}

    # ── Dependency resolution ──────────────────────────────────────────────────

    def _resolve_dependencies(
        self, object_type: str, data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Replace name-valued dependency fields with their integer IDs.

        Also applies CaaC→API field renames and strips CaaC-only fields.
        """
        result = dict(data)

        # 1. Strip CaaC-only metadata fields
        strip = set(CAAC_STRIP_FIELDS.get("_all", []))
        strip |= set(CAAC_STRIP_FIELDS.get(object_type, []))
        for field in strip:
            result.pop(field, None)

        # 2. Rename CaaC fields to API field names
        for caac_name, api_name in CAAC_TO_API_FIELD_MAP.get(object_type, {}).items():
            if caac_name in result:
                result[api_name] = result.pop(caac_name)

        # 3. Resolve name → ID for dependency fields
        dep_map = DEPENDENCY_FIELD_MAP.get(object_type, {})
        for field, dep_type in dep_map.items():
            value = result.get(field)
            if value and isinstance(value, str):
                obj_id = self.resolve_name_to_id(dep_type, value)
                if obj_id is not None:
                    result[field] = obj_id
                else:
                    print(f"[warn] Could not resolve {dep_type} named '{value}' for field '{field}'")
                    result.pop(field, None)

        # 4. Remove association fields (they are handled via sub-endpoints)
        for field in ASSOCIATION_FIELD_MAP.get(object_type, {}):
            result.pop(field, None)

        # 5. Strip fields containing unresolved Jinja2 templates ({{ var }})
        for key in list(result.keys()):
            value = result[key]
            if isinstance(value, str) and _JINJA2_RE.search(value):
                print(
                    f"[warn] Removing field '{key}' — contains unresolved "
                    f"Jinja2 template: {value!r}"
                )
                result.pop(key)

        # 6. Strip None values (API rejects null for required fields)
        result = {k: v for k, v in result.items() if v is not None and v != ""}

        return result

    def _associate_objects(
        self,
        object_type: str,
        object_id: int,
        data: Dict[str, Any],
    ) -> None:
        """Call sub-endpoints to associate list-valued fields (e.g. credentials)."""
        assoc_map = ASSOCIATION_FIELD_MAP.get(object_type, {})
        for field, (dep_type, endpoint_template) in assoc_map.items():
            names = data.get(field, [])
            if not names:
                continue
            endpoint = endpoint_template.format(id=object_id)
            for name in names:
                if not isinstance(name, str):
                    continue
                dep_id = self.resolve_name_to_id(dep_type, name)
                if dep_id is not None:
                    try:
                        self._request("POST", endpoint, data={"id": dep_id})
                    except Exception as exc:
                        print(f"[warn] Could not associate {dep_type} '{name}': {exc}")
                else:
                    print(f"[warn] Could not find {dep_type} named '{name}' for association")

    # ── Write operations ───────────────────────────────────────────────────────

    def create_object(self, object_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new object, resolving all name→ID dependencies first."""
        api_data = self._resolve_dependencies(object_type, data)
        endpoint = self._get_endpoint(object_type)
        resp = self._request("POST", endpoint, data=api_data)
        created = resp.json()
        # Associate list-valued fields (e.g. credentials on job_templates)
        self._associate_objects(object_type, created["id"], data)
        return created

    def update_object(
        self, object_type: str, object_id: int, data: Dict[str, Any]
    ) -> Dict[str, Any]:
        api_data = self._resolve_dependencies(object_type, data)
        endpoint = f"{self._get_endpoint(object_type)}{object_id}/"
        resp = self._request("PATCH", endpoint, data=api_data)
        return resp.json()

    def delete_object(self, object_type: str, object_id: int) -> bool:
        endpoint = f"{self._get_endpoint(object_type)}{object_id}/"
        resp = self._request("DELETE", endpoint)
        return resp.status_code in (200, 202, 204)


# ── CrewAI Tool Functions ──────────────────────────────────────────────────────

@tool("List AAP objects")
def list_aap_objects(object_type: str) -> str:
    """List all objects of a specific type from AAP.

    For credential_types, only custom (non-built-in) types are listed.

    Args:
        object_type: e.g. 'projects', 'job_templates', 'organizations', 'credentials'
    """
    client = AAPClient()
    try:
        objects = client.list_objects(object_type)
        if not objects:
            return f"No {object_type} found in AAP"
        lines = [f"Found {len(objects)} {object_type} in AAP:"]
        for obj in objects:
            name = obj.get("name", "Unknown")
            oid = obj.get("id", "?")
            lines.append(f"  - {name} (ID: {oid})")
        return "\n".join(lines)
    except Exception as exc:
        return f"Error listing {object_type}: {exc}"


@tool("Get AAP object details")
def get_aap_object(object_type: str, name: str) -> str:
    """Get detailed information about a specific AAP object.

    Args:
        object_type: The type of AAP object
        name: The name of the object
    """
    import yaml as _yaml
    client = AAPClient()
    try:
        obj = client.get_object_by_name(object_type, name)
        if not obj:
            return f"Object not found: {object_type}/{name}"
        return _yaml.dump(obj, default_flow_style=False)
    except Exception as exc:
        return f"Error getting object: {exc}"


@tool("Get AAP current state")
def get_aap_current_state(object_types: str) -> str:
    """Get the current state of AAP for comma-separated object types.

    Args:
        object_types: Comma-separated list, e.g. 'organizations,projects,job_templates'
    """
    client = AAPClient()
    types_list = [t.strip() for t in object_types.split(",")]
    try:
        state = client.get_current_state(types_list)
        lines = ["Current AAP State:"]
        for obj_type, objects in state.items():
            lines.append(f"\n{obj_type}: {len(objects)} objects")
            for name in objects:
                lines.append(f"  - {name}")
        return "\n".join(lines)
    except Exception as exc:
        return f"Error getting current state: {exc}"


@tool("Create AAP object")
def create_aap_object(object_type: str, definition: str) -> str:
    """Create a new object in AAP from a YAML definition.

    Automatically resolves dependency fields (organization, project, inventory,
    execution_environment, credential_type) from names to IDs. Also handles
    post-creation association of credentials and galaxy_credentials.

    Args:
        object_type: The type of AAP object to create
        definition: YAML string of the object definition (from Git CaaC)
    """
    import yaml as _yaml
    client = AAPClient()
    settings = get_settings()

    if settings.dry_run:
        return f"[DRY RUN] Would create {object_type} with definition:\n{definition}"

    try:
        data = _yaml.safe_load(definition)
        result = client.create_object(object_type, data)
        return f"Created {object_type}: {result.get('name')} (ID: {result.get('id')})"
    except Exception as exc:
        return f"Error creating {object_type}: {exc}"


@tool("Update AAP object")
def update_aap_object(object_type: str, name: str, updates: str) -> str:
    """Update an existing AAP object to match the Git definition.

    Automatically resolves dependency fields from names to IDs.

    Args:
        object_type: The type of AAP object
        name: The name of the object to update
        updates: YAML string of fields to update
    """
    import yaml as _yaml
    client = AAPClient()
    settings = get_settings()

    if settings.dry_run:
        return f"[DRY RUN] Would update {object_type}/{name} with:\n{updates}"

    try:
        obj = client.get_object_by_name(object_type, name)
        if not obj:
            return f"Object not found: {object_type}/{name}"
        data = _yaml.safe_load(updates)
        result = client.update_object(object_type, obj["id"], data)
        return f"Updated {object_type}: {result.get('name')}"
    except Exception as exc:
        return f"Error updating {object_type}: {exc}"


@tool("Delete AAP object")
def delete_aap_object(object_type: str, name: str) -> str:
    """Delete an object from AAP (only if not protected).

    Args:
        object_type: The type of AAP object
        name: The name of the object to delete
    """
    client = AAPClient()
    settings = get_settings()

    if name in settings.protected_object_names:
        return f"Skipped: '{name}' is a protected object"

    if settings.dry_run:
        return f"[DRY RUN] Would delete {object_type}/{name}"

    try:
        obj = client.get_object_by_name(object_type, name)
        if not obj:
            return f"Object not found: {object_type}/{name}"
        success = client.delete_object(object_type, obj["id"])
        return f"Deleted {object_type}: {name}" if success else f"Failed to delete {object_type}: {name}"
    except Exception as exc:
        return f"Error deleting {object_type}/{name}: {exc}"
