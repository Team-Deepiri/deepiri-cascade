import click
from pathlib import Path

from rich.console import Console

from .ci_logging import compute_dependency_waves, emit_cascade_plan_for_ci

console = Console()


@click.group()
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
@click.pass_context
def main(ctx, verbose):
    """Deepiri Cascade - Cascade version updates across Deepiri repos."""
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose


@main.command()
@click.option("--repo", help="Repository name (auto-detected from tag event)")
@click.option("--tag", help="Version tag to cascade (auto-detected)")
@click.option("--org", default="team-deepiri", help="GitHub organization name")
@click.option("--token", help="GitHub token (defaults to GITHUB_TOKEN env)")
@click.option("--bump-type", type=click.Choice(["patch", "minor", "major"]), default="patch")
@click.option("--dry-run", is_flag=True, help="Preview changes without making updates")
@click.option("--no-confirm", is_flag=True, help="Skip confirmation prompt")
@click.option("--work-dir", default="/tmp/deepiri-cascade", help="Working directory for git operations")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
@click.pass_context
def cascade(ctx, repo, tag, org, token, bump_type, dry_run, no_confirm, work_dir, verbose):
    """Run cascade update for a tagged release."""
    from .auto_detect import detect_repo_and_tag
    from .github_auth import get_token
    from .discovery import Discovery
    from .cascade import CascadeProcessor

    verbose = ctx.obj.get("verbose") or verbose

    if not token:
        token = get_token()
    if not token:
        console.print("[red]Error: GitHub token required. Set GITHUB_TOKEN env var or use --token[/red]")
        raise click.Abort()

    repo, tag = detect_repo_and_tag(repo, tag, token, org)

    console.print(f"[cyan]Cascading {repo} {tag} to dependent repos...[/cyan]")

    discovery = Discovery(token, org, verbose=verbose)
    graph = discovery.build_dependency_graph(repo, tag)

    waves = compute_dependency_waves(graph, repo)
    emit_cascade_plan_for_ci(org, repo, tag, graph, waves)

    processor = CascadeProcessor(
        token=token,
        org=org,
        bump_type=bump_type,
        dry_run=dry_run,
        work_dir=work_dir,
        verbose=verbose,
    )

    results = processor.run(graph, source_repo=repo, source_tag=tag, confirm=not no_confirm)

    console.print(f"\n[green]✓ Updated {len(results.get('updated', []))} repos[/green]")
    if results.get("skipped"):
        console.print(f"[yellow]- Skipped: {len(results['skipped'])}[/yellow]")
    if results.get("failed"):
        console.print(f"[red]✗ Failed: {len(results['failed'])}[/red]")
        raise click.ClickException("Cascade failed for one or more repositories")


@main.command()
@click.option("--path", "project_path", default=".", help="Local repo/package path to release")
@click.option("--bump-type", type=click.Choice(["patch", "minor", "major"]), default="patch")
@click.option("--dry-run", is_flag=True, help="Preview the version/tag without committing")
@click.option("--no-push", is_flag=True, help="Create the local commit/tag without pushing")
@click.option("--message", help="Annotated tag message")
def release(project_path, bump_type, dry_run, no_push, message):
    """Bump the local project version, commit it, tag it, and optionally push."""
    from .release import (
        bump_project_version,
        commit_release,
        create_git_tag,
        ensure_clean_worktree,
        plan_project_version,
        push_release,
    )

    path = Path(project_path).resolve()

    if dry_run:
        result = plan_project_version(path, bump_type)
        console.print(
            f"[green]Would bump {result.manifest_path.relative_to(path)} to {result.version} ({result.tag})[/green]"
        )
        return

    ensure_clean_worktree(path)

    result = bump_project_version(path, bump_type)
    console.print(
        f"[green]Bumped {result.manifest_path.relative_to(path)} to {result.version} ({result.tag})[/green]"
    )

    commit_release(path, result.tag, result.manifest_path)
    create_git_tag(path, result.tag, message)
    console.print(f"[green]Created release commit and tag {result.tag}[/green]")

    if no_push:
        console.print("[yellow]Skipped push (--no-push)[/yellow]")
        return

    push_release(path, result.tag)
    console.print(f"[green]Pushed HEAD and {result.tag}[/green]")


if __name__ == "__main__":
    main()
