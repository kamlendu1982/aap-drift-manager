"""Main entry point for AAP Drift Manager."""

import logging
import sys
from typing import List, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from src.config import get_settings
from src.crew import DriftManagementCrew, run_drift_management

# CLI App
app = typer.Typer(
    name="aap-drift",
    help="AI-powered drift management for Ansible Automation Platform",
    add_completion=False,
)

console = Console()


def setup_logging(verbose: bool = False) -> None:
    """Configure logging based on settings."""
    settings = get_settings()
    level = logging.DEBUG if verbose else getattr(logging, settings.log_level.upper())
    
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def print_header() -> None:
    """Print application header."""
    console.print(Panel.fit(
        "[bold blue]AAP Drift Manager[/bold blue]\n"
        "[dim]AI-powered drift management for Ansible Automation Platform[/dim]",
        border_style="blue",
    ))


def print_settings_summary(settings, object_types: List[str], dry_run: bool) -> None:
    """Print current settings summary."""
    table = Table(title="Configuration", show_header=False, border_style="dim")
    table.add_column("Setting", style="cyan")
    table.add_column("Value", style="green")
    
    table.add_row("AAP URL", settings.aap_url)
    table.add_row("Git Repo", settings.git_repo_path)
    table.add_row("Git Branch", settings.git_branch)
    table.add_row("Object Types", ", ".join(object_types))
    table.add_row("Mode", "[yellow]DRY RUN[/yellow]" if dry_run else "[red]APPLY CHANGES[/red]")
    
    console.print(table)
    console.print()


@app.command()
def run(
    dry_run: bool = typer.Option(
        None,
        "--dry-run/--apply",
        help="Run in dry-run mode (no changes) or apply mode",
    ),
    objects: Optional[str] = typer.Option(
        None,
        "--objects", "-o",
        help="Comma-separated list of object types to manage",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose", "-v",
        help="Enable verbose output",
    ),
) -> None:
    """Run drift detection and reconciliation."""
    setup_logging(verbose)
    print_header()
    
    try:
        settings = get_settings()
    except Exception as e:
        console.print(f"[red]Configuration error: {e}[/red]")
        console.print("[dim]Make sure you have a .env file with required settings[/dim]")
        raise typer.Exit(1)
    
    # Determine settings
    object_types = objects.split(",") if objects else settings.managed_object_types
    is_dry_run = dry_run if dry_run is not None else settings.dry_run
    
    print_settings_summary(settings, object_types, is_dry_run)
    
    # Confirmation for apply mode
    if not is_dry_run and settings.require_confirmation:
        confirmed = typer.confirm(
            "⚠️  You are about to apply changes to AAP. Continue?",
            default=False,
        )
        if not confirmed:
            console.print("[yellow]Aborted.[/yellow]")
            raise typer.Exit(0)
    
    # Run the drift management crew
    console.print("[bold]Starting drift management...[/bold]\n")
    
    try:
        result = run_drift_management(
            object_types=object_types,
            dry_run=is_dry_run,
        )
        
        console.print("\n[bold green]✓ Drift management complete![/bold green]")
        console.print(f"\nResult:\n{result['result']}")
        
    except Exception as e:
        console.print(f"\n[red]Error during drift management: {e}[/red]")
        if verbose:
            console.print_exception()
        raise typer.Exit(1)


@app.command()
def detect(
    objects: Optional[str] = typer.Option(
        None,
        "--objects", "-o",
        help="Comma-separated list of object types to check",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose", "-v",
        help="Enable verbose output",
    ),
) -> None:
    """Detect drift without making any changes (report only)."""
    setup_logging(verbose)
    print_header()
    
    try:
        settings = get_settings()
    except Exception as e:
        console.print(f"[red]Configuration error: {e}[/red]")
        raise typer.Exit(1)
    
    object_types = objects.split(",") if objects else settings.managed_object_types
    
    console.print(f"[bold]Checking drift for: {', '.join(object_types)}[/bold]\n")
    
    # Use the diff tools directly for quick detection
    from src.tools import GitTools, AAPClient, DiffTools
    
    try:
        git_tools = GitTools()
        aap_client = AAPClient()
        diff_tools = DiffTools()
        
        total_extra = 0
        total_missing = 0
        total_modified = 0
        
        for obj_type in object_types:
            console.print(f"[dim]Checking {obj_type}...[/dim]")
            
            git_state = git_tools.get_all_definitions(obj_type)
            aap_objects = aap_client.list_objects(obj_type)
            aap_state = {obj["name"]: obj for obj in aap_objects}
            
            extra, missing, modified = diff_tools.find_drift(
                git_state, aap_state, obj_type
            )
            
            total_extra += len(extra)
            total_missing += len(missing)
            total_modified += len(modified)
            
            if extra or missing or modified:
                console.print(f"\n[bold]{obj_type}:[/bold]")
                
                for obj in extra:
                    console.print(f"  [red]✗ EXTRA:[/red] {obj.object_name}")
                
                for obj in missing:
                    console.print(f"  [yellow]+ MISSING:[/yellow] {obj.object_name}")
                
                for obj in modified:
                    console.print(f"  [cyan]~ MODIFIED:[/cyan] {obj.object_name}")
                    for diff in obj.field_diffs:
                        console.print(f"    [dim]{diff}[/dim]")
        
        # Summary
        console.print("\n" + "=" * 50)
        total = total_extra + total_missing + total_modified
        
        if total == 0:
            console.print("[bold green]✓ No drift detected! AAP is in sync with Git.[/bold green]")
        else:
            console.print(f"[bold]Drift Summary:[/bold]")
            console.print(f"  Extra (to delete):  {total_extra}")
            console.print(f"  Missing (to create): {total_missing}")
            console.print(f"  Modified (to update): {total_modified}")
            console.print(f"  [bold]Total: {total}[/bold]")
            console.print("\n[dim]Run 'aap-drift run' to reconcile drift[/dim]")
        
    except Exception as e:
        console.print(f"\n[red]Error during detection: {e}[/red]")
        if verbose:
            console.print_exception()
        raise typer.Exit(1)


@app.command()
def status() -> None:
    """Show current configuration and connection status."""
    print_header()
    
    try:
        settings = get_settings()
        
        table = Table(title="Current Configuration", border_style="blue")
        table.add_column("Setting", style="cyan")
        table.add_column("Value", style="white")
        table.add_column("Status", style="green")
        
        # AAP Settings
        table.add_row("AAP URL", settings.aap_url, "")
        auth_status = "✓ Token" if settings.aap_token else (
            "✓ User/Pass" if settings.has_valid_auth else "✗ Not configured"
        )
        table.add_row("AAP Auth", "[dim]***[/dim]", auth_status)
        table.add_row("SSL Verify", str(settings.aap_verify_ssl), "")
        
        # Git Settings
        table.add_row("Git Repo", settings.git_repo_path, "")
        table.add_row("Git Branch", settings.git_branch, "")
        
        # Managed Objects
        table.add_row("Managed Objects", ", ".join(settings.managed_object_types), "")
        
        # Mode
        mode = "[yellow]Dry Run[/yellow]" if settings.dry_run else "[red]Apply[/red]"
        table.add_row("Default Mode", mode, "")
        
        console.print(table)
        
        # Test connections
        console.print("\n[bold]Testing connections...[/bold]")
        
        # Test AAP
        from src.tools import AAPClient
        try:
            client = AAPClient()
            client.session.get(f"{settings.aap_url}/api/v2/ping/")
            console.print("  [green]✓[/green] AAP connection successful")
        except Exception as e:
            console.print(f"  [red]✗[/red] AAP connection failed: {e}")
        
        # Test Git
        from src.tools import GitTools
        try:
            git = GitTools()
            git.ensure_branch()
            console.print(f"  [green]✓[/green] Git repo accessible (branch: {git.branch})")
        except Exception as e:
            console.print(f"  [red]✗[/red] Git repo error: {e}")
        
    except Exception as e:
        console.print(f"[red]Error loading configuration: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def version() -> None:
    """Show version information."""
    console.print("[bold]AAP Drift Manager[/bold]")
    console.print("Version: 0.1.0")
    console.print("Framework: CrewAI")


def main() -> None:
    """Main entry point."""
    app()


if __name__ == "__main__":
    main()
