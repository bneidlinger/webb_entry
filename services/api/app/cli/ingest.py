"""`python -m app ingest ...` commands."""
from __future__ import annotations

import json

import typer
from rich.console import Console
from rich.table import Table as RichTable

from app.clients.mast import MastClient
from app.db import session_scope
from app.services.ingest import ingest_observations

app = typer.Typer(no_args_is_help=True)
console = Console()


@app.command("mast")
def ingest_mast(
    instrument: str | None = typer.Option(
        None,
        "--instrument",
        "-i",
        help="JWST instrument prefix (NIRCAM, NIRSPEC, MIRI, NIRISS, FGS).",
    ),
    program_id: str | None = typer.Option(
        None, "--program-id", "-p", help="Proposal/program ID, e.g. 1234."
    ),
    target_name: str | None = typer.Option(
        None, "--target", "-t", help="Target name (exact match)."
    ),
    limit: int = typer.Option(100, "--limit", "-n", min=1, max=10_000),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Query MAST, print summary, don't write."
    ),
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON summary."),
) -> None:
    """Pull JWST observations + products from MAST and upsert them into the DB."""
    if not (instrument or program_id or target_name):
        raise typer.BadParameter(
            "Provide at least one of --instrument, --program-id, or --target."
        )

    if not json_output:
        console.print(
            f"[bold]Querying MAST[/bold] (instrument={instrument!r}, "
            f"program_id={program_id!r}, target={target_name!r}, limit={limit})"
        )

    client = MastClient()
    observations = client.fetch_jwst(
        instrument=instrument,
        program_id=program_id,
        target_name=target_name,
        limit=limit,
    )

    if not json_output:
        console.print(
            f"  -> {len(observations)} observations, "
            f"{sum(len(o.products) for o in observations)} products"
        )

    if dry_run:
        if json_output:
            typer.echo(json.dumps({"dry_run": True, "observations": len(observations)}))
        else:
            console.print("[yellow]--dry-run: nothing written to the database[/yellow]")
        return

    with session_scope() as session:
        result = ingest_observations(session, observations)

    if json_output:
        typer.echo(json.dumps(result.as_dict()))
        return

    table = RichTable(title="Ingest summary")
    table.add_column("metric")
    table.add_column("count", justify="right")
    for key, value in result.as_dict().items():
        if isinstance(value, list):
            continue
        table.add_row(key, str(value))
    console.print(table)
    if result.errors:
        console.print(f"[red]{len(result.errors)} error(s):[/red]")
        for err in result.errors:
            console.print(f"  - {err}")
