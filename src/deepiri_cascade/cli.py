import click
from rich.console import Console

console = Console()


@click.group()
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
@click.pass_context
def main(ctx):
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
    if results.get("failed"):
        console.print(f"[red]✗ Failed: {len(results['failed'])}[/red]")


if __name__ == "__main__":
    main()