"""AAP API tools for interacting with Ansible Automation Platform."""

from typing import Any, Dict, List, Optional

import requests
from crewai.tools import tool

from src.config import get_settings
from src.models import OBJECT_TYPE_ENDPOINTS, ObjectType


class AAPClient:
    """Client for interacting with the AAP API."""

    def __init__(
        self,
        url: Optional[str] = None,
        token: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        verify_ssl: bool = True,
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
        """Get or create a requests session with authentication."""
        if self._session is None:
            self._session = requests.Session()
            self._session.verify = self.verify_ssl
            
            if self.token:
                self._session.headers["Authorization"] = f"Bearer {self.token}"
            elif self.username and self.password:
                self._session.auth = (self.username, self.password)
            
            self._session.headers["Content-Type"] = "application/json"
        
        return self._session

    def _get_endpoint(self, object_type: str) -> str:
        """Get the API endpoint for an object type."""
        try:
            obj_type = ObjectType(object_type)
            return OBJECT_TYPE_ENDPOINTS[obj_type]
        except (ValueError, KeyError):
            return f"/api/v2/{object_type}/"

    def _request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict] = None,
        params: Optional[Dict] = None,
    ) -> requests.Response:
        """Make an API request."""
        url = f"{self.base_url}{endpoint}"
        response = self.session.request(
            method=method,
            url=url,
            json=data,
            params=params,
        )
        response.raise_for_status()
        return response

    def list_objects(self, object_type: str) -> List[Dict[str, Any]]:
        """List all objects of a given type."""
        endpoint = self._get_endpoint(object_type)
        objects = []
        next_url = endpoint
        
        while next_url:
            if next_url.startswith("http"):
                # Full URL from pagination
                response = self.session.get(next_url)
            else:
                response = self._request("GET", next_url)
            
            response.raise_for_status()
            data = response.json()
            
            objects.extend(data.get("results", []))
            next_url = data.get("next")
        
        return objects

    def get_object(self, object_type: str, object_id: int) -> Dict[str, Any]:
        """Get a specific object by ID."""
        endpoint = f"{self._get_endpoint(object_type)}{object_id}/"
        response = self._request("GET", endpoint)
        return response.json()

    def get_object_by_name(self, object_type: str, name: str) -> Optional[Dict[str, Any]]:
        """Get an object by name."""
        endpoint = self._get_endpoint(object_type)
        response = self._request("GET", endpoint, params={"name": name})
        data = response.json()
        results = data.get("results", [])
        return results[0] if results else None

    def create_object(self, object_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new object."""
        endpoint = self._get_endpoint(object_type)
        response = self._request("POST", endpoint, data=data)
        return response.json()

    def update_object(
        self, object_type: str, object_id: int, data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Update an existing object."""
        endpoint = f"{self._get_endpoint(object_type)}{object_id}/"
        response = self._request("PATCH", endpoint, data=data)
        return response.json()

    def delete_object(self, object_type: str, object_id: int) -> bool:
        """Delete an object."""
        endpoint = f"{self._get_endpoint(object_type)}{object_id}/"
        response = self._request("DELETE", endpoint)
        return response.status_code in (200, 202, 204)

    def get_current_state(self, object_types: List[str]) -> Dict[str, Dict[str, Dict[str, Any]]]:
        """Get the current state for all specified object types.
        
        Returns a nested dict: {object_type: {object_name: object_data}}
        """
        current_state = {}
        for obj_type in object_types:
            objects = self.list_objects(obj_type)
            current_state[obj_type] = {obj["name"]: obj for obj in objects}
        return current_state

    def resolve_name_to_id(self, object_type: str, name: str) -> Optional[int]:
        """Resolve an object name to its ID."""
        obj = self.get_object_by_name(object_type, name)
        return obj["id"] if obj else None


# CrewAI Tool Functions
@tool("List AAP objects")
def list_aap_objects(object_type: str) -> str:
    """List all objects of a specific type from AAP.
    
    Args:
        object_type: The type of AAP object (e.g., 'projects', 'job_templates')
    
    Returns:
        A list of objects with their names and IDs.
    """
    client = AAPClient()
    try:
        objects = client.list_objects(object_type)
        if not objects:
            return f"No {object_type} found in AAP"
        
        summary = [f"Found {len(objects)} {object_type}:"]
        for obj in objects:
            name = obj.get("name", "Unknown")
            obj_id = obj.get("id", "?")
            summary.append(f"  - {name} (ID: {obj_id})")
        
        return "\n".join(summary)
    except Exception as e:
        return f"Error listing {object_type}: {e}"


@tool("Get AAP object details")
def get_aap_object(object_type: str, name: str) -> str:
    """Get detailed information about a specific AAP object.
    
    Args:
        object_type: The type of AAP object
        name: The name of the object
    
    Returns:
        Detailed object information as YAML.
    """
    import yaml
    client = AAPClient()
    try:
        obj = client.get_object_by_name(object_type, name)
        if not obj:
            return f"Object not found: {object_type}/{name}"
        
        return yaml.dump(obj, default_flow_style=False)
    except Exception as e:
        return f"Error getting object: {e}"


@tool("Get AAP current state")
def get_aap_current_state(object_types: str) -> str:
    """Get the current state of AAP for specified object types.
    
    Args:
        object_types: Comma-separated list of object types.
    
    Returns:
        Summary of current state in AAP.
    """
    client = AAPClient()
    types_list = [t.strip() for t in object_types.split(",")]
    
    try:
        current_state = client.get_current_state(types_list)
        
        summary = ["Current AAP State:"]
        for obj_type, objects in current_state.items():
            summary.append(f"\n{obj_type}: {len(objects)} objects")
            for name in objects:
                summary.append(f"  - {name}")
        
        return "\n".join(summary)
    except Exception as e:
        return f"Error getting current state: {e}"


@tool("Create AAP object")
def create_aap_object(object_type: str, definition: str) -> str:
    """Create a new object in AAP.
    
    Args:
        object_type: The type of AAP object to create
        definition: YAML string of the object definition
    
    Returns:
        Result of the creation operation.
    """
    import yaml
    client = AAPClient()
    settings = get_settings()
    
    if settings.dry_run:
        return f"[DRY RUN] Would create {object_type} with definition:\n{definition}"
    
    try:
        data = yaml.safe_load(definition)
        result = client.create_object(object_type, data)
        return f"Created {object_type}: {result.get('name')} (ID: {result.get('id')})"
    except Exception as e:
        return f"Error creating object: {e}"


@tool("Update AAP object")
def update_aap_object(object_type: str, name: str, updates: str) -> str:
    """Update an existing object in AAP.
    
    Args:
        object_type: The type of AAP object
        name: The name of the object to update
        updates: YAML string of fields to update
    
    Returns:
        Result of the update operation.
    """
    import yaml
    client = AAPClient()
    settings = get_settings()
    
    if settings.dry_run:
        return f"[DRY RUN] Would update {object_type}/{name} with:\n{updates}"
    
    try:
        obj = client.get_object_by_name(object_type, name)
        if not obj:
            return f"Object not found: {object_type}/{name}"
        
        data = yaml.safe_load(updates)
        result = client.update_object(object_type, obj["id"], data)
        return f"Updated {object_type}: {result.get('name')}"
    except Exception as e:
        return f"Error updating object: {e}"


@tool("Delete AAP object")
def delete_aap_object(object_type: str, name: str) -> str:
    """Delete an object from AAP.
    
    Args:
        object_type: The type of AAP object
        name: The name of the object to delete
    
    Returns:
        Result of the deletion operation.
    """
    client = AAPClient()
    settings = get_settings()
    
    # Check if object is protected
    if name in settings.protected_object_names:
        return f"Cannot delete protected object: {name}"
    
    if settings.dry_run:
        return f"[DRY RUN] Would delete {object_type}/{name}"
    
    try:
        obj = client.get_object_by_name(object_type, name)
        if not obj:
            return f"Object not found: {object_type}/{name}"
        
        success = client.delete_object(object_type, obj["id"])
        if success:
            return f"Deleted {object_type}: {name}"
        else:
            return f"Failed to delete {object_type}: {name}"
    except Exception as e:
        return f"Error deleting object: {e}"
