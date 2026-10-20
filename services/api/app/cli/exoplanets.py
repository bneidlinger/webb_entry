"""Export a complete catalog ranking and a reproducible image prompt."""
from __future__ import annotations

import csv
import gzip
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import httpx
import typer

from app.clients.exoplanets import fetch_catalog, validate_catalog
from app.services.exoplanet_catalog import CatalogSnapshot
from app.services.exoplanets import LIMITATION, SCORE_VERSION, build_portrait_brief, rank_catalog

app = typer.Typer(no_args_is_help=True)


@app.command("bundle")
def bundle(
    snapshot_dir: Annotated[Path, typer.Option(help="Saved ranking snapshot directory.")],
    output_dir: Annotated[Path, typer.Option(help="New directory for the API snapshot bundle.")],
    evidence: Annotated[Path | None, typer.Option(help="Appearance JSON object or list.")] = None,
) -> None:
    """Package a verified snapshot for browsing without live archive requests."""
    try:
        payload = (snapshot_dir / "catalog.json").read_bytes()
        manifest = json.loads((snapshot_dir / "manifest.json").read_text(encoding="utf-8"))
        if hashlib.sha256(payload).hexdigest() != manifest.get("catalog_sha256"):
            raise ValueError("Catalog snapshot checksum mismatch.")
        rows = validate_catalog(json.loads(payload))
        if len(rows) != manifest.get("record_count"):
            raise ValueError("Catalog snapshot record count mismatch.")
        appearance = json.loads(evidence.read_text(encoding="utf-8")) if evidence else None
        catalog = CatalogSnapshot(rows, manifest, appearance)
        public_manifest = {key: catalog.metadata[key] for key in (
            "retrieved_at_utc", "catalog_sha256", "coverage", "record_count", "score_version",
        )}
        public_manifest["source"] = catalog.metadata["source"]
        _new_directory(output_dir)
        (output_dir / "catalog.json.gz").write_bytes(gzip.compress(payload, mtime=0))
        if appearance:
            (output_dir / "appearance.json").write_text(_json(appearance), encoding="utf-8")
        (output_dir / "manifest.json").write_text(_json(public_manifest), encoding="utf-8")
        typer.echo(f"Bundled {len(rows)} planets for the web catalog.")
    except (OSError, ValueError) as exc:
        typer.echo(f"Catalog bundle failed: {exc}", err=True)
        raise typer.Exit(1) from exc


def _load(path: Path) -> list[dict]:
    return validate_catalog(json.loads(path.read_text(encoding="utf-8")))


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"


def _new_directory(path: Path) -> None:
    # Each run is a snapshot; never silently replace a previous set of artifacts.
    if path.exists():
        raise ValueError(f"Output directory already exists: {path}. Choose a new snapshot path.")
    path.mkdir(parents=True)


@app.command("rank")
def rank(
    output_dir: Annotated[Path, typer.Option(help="New directory for snapshot and exports.")],
    catalog: Annotated[Path | None, typer.Option(help="Replay a local catalog.json.")] = None,
    live: Annotated[bool, typer.Option(help="Fetch all confirmed planets from NASA.")] = False,
    top: Annotated[int, typer.Option(min=1, max=100)] = 15,
) -> None:
    """Rank catalog evidence availability. Does not download FITS or call AI."""
    if live == (catalog is not None):
        raise typer.BadParameter("Choose exactly one of --live or --catalog.")
    try:
        if output_dir.exists():
            raise ValueError(f"Output directory already exists: {output_dir}")
        if live:
            rows, manifest = fetch_catalog()
        else:
            rows = _load(catalog)
            manifest = {
                "source": str(catalog.resolve()), "record_count": len(rows),
                "coverage": "local_input_only_not_verified_against_live_archive",
            }
        ranked = rank_catalog(rows)
        snapshot = _json(rows)
        manifest.update({
            "generated_at_utc": datetime.now(UTC).isoformat(),
            "catalog_sha256": hashlib.sha256(snapshot.encode("utf-8")).hexdigest(),
            "score_version": SCORE_VERSION, "limitation": LIMITATION,
            "sort": "score descending; shared ranks for ties; planet name for display order",
        })
        _new_directory(output_dir)
        (output_dir / "catalog.json").write_text(snapshot, encoding="utf-8", newline="\n")
        (output_dir / "ranking.json").write_text(_json(ranked), encoding="utf-8")
        columns = ["rank", "planet", "host", "score", "tier", "discovery_facility"]
        with (output_dir / "ranking.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=[*columns, "transmission", "eclipse",
                                                        "direct_imaging", "appearance_assessed"])
            writer.writeheader()
            for row in ranked:
                writer.writerow({**{k: row[k] for k in columns}, **row["spectra_counts"],
                                 "appearance_assessed": False})
        # The manifest is the completion marker; hash bytes exactly as written on Windows too.
        (output_dir / "manifest.json").write_text(_json(manifest), encoding="utf-8")
        typer.echo(f"Ranked {len(ranked)} planets. Score: {SCORE_VERSION} (proxy, not confidence).")
        for row in ranked[:top]:
            typer.echo(f"{row['rank']:>4}  {row['score']:>5.1f}  {row['planet']}  {row['tier']}")
        typer.echo(f"Saved snapshot and exports to {output_dir.resolve()}")
    except (ValueError, OSError, httpx.HTTPError) as exc:
        typer.echo(f"Exoplanet ranking failed: {exc}", err=True)
        raise typer.Exit(1) from exc


@app.command("prompt")
def prompt(
    catalog: Annotated[Path, typer.Option(help="Saved catalog.json from a ranking run.")],
    planet: Annotated[str, typer.Option(help="Exact planet name, case insensitive.")],
    output_dir: Annotated[Path, typer.Option(help="New directory for prompt.txt and brief.json.")],
    evidence: Annotated[Path | None, typer.Option(help="Optional sourced appearance JSON.")] = None,
) -> None:
    """Export a sourced, hypothetical portrait brief; image generation remains on demand."""
    try:
        rows = _load(catalog)
        row = next((r for r in rows if r["pl_name"].casefold() == planet.strip().casefold()), None)
        if row is None:
            raise ValueError(f"Planet not found in this snapshot: {planet}")
        appearance = json.loads(evidence.read_text(encoding="utf-8")) if evidence else None
        brief = build_portrait_brief(row, appearance)
        brief["catalog_sha256"] = hashlib.sha256(catalog.read_bytes()).hexdigest()
        brief["catalog_path"] = str(catalog.resolve())
        _new_directory(output_dir)
        (output_dir / "brief.json").write_text(_json(brief), encoding="utf-8")
        (output_dir / "prompt.txt").write_text(brief["prompt"] + "\n", encoding="utf-8")
        typer.echo(f"Saved {brief['status']} prompt to {output_dir.resolve()}")
    except (ValueError, OSError) as exc:
        typer.echo(f"Portrait prompt failed: {exc}", err=True)
        raise typer.Exit(1) from exc
