import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add current directory to path so we can import deadline_agent
sys.path.insert(0, str(Path(__file__).parent))

from rich.console import Console
from rich.table import Table

from deadline_agent import AgentConfig, DeadlineAgent


def main():
    cfg = AgentConfig.from_env()
    missing = [k for k, v in {
        "DA_EMAIL_ADDRESS": os.getenv("DA_EMAIL_ADDRESS"),
        "DA_EMAIL_PASSWORD": os.getenv("DA_EMAIL_PASSWORD"),
    }.items() if not v]
    if missing:
        print("Missing required env vars:", ", ".join(missing))
        print("Set DA_EMAIL_ADDRESS and DA_EMAIL_PASSWORD. Optional: DA_IMAP_HOST, DA_IMAP_PORT, DA_MAILBOX, DA_SINCE_DAYS, DA_MAX_MESSAGES")
        return

    # Agent uses IMAP by default
    agent = DeadlineAgent(cfg)
    deadlines, stats = agent.collect_deadlines()

    console = Console()
    
    # Show stats if debug mode or if no deadlines found
    if cfg.debug or len(deadlines) == 0:
        console.print(f"\n[bold cyan]Scan Statistics:[/bold cyan]")
        console.print(f"  Emails fetched: {stats.emails_fetched}")
        console.print(f"  Emails processed: {stats.emails_processed}")
        console.print(f"  Deadlines found: {stats.deadlines_found}")
        console.print(f"  Unique senders: {stats.unique_senders}")
        if stats.sample_subjects:
            console.print(f"\n[bold]Sample subjects:[/bold]")
            for subj in stats.sample_subjects:
                console.print(f"  • {subj}")
        console.print("")
    
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Deadline")
    table.add_column("Title")
    table.add_column("Source")
    table.add_column("Confidence")

    for d in deadlines:
        table.add_row(
            d.deadline_at.strftime("%Y-%m-%d %H:%M"),
            d.title,
            d.source,
            f"{d.confidence:.2f}",
        )

    if deadlines:
        console.print(table)
    else:
        console.print(f"[yellow]No deadlines found after scanning {stats.emails_fetched} emails.[/yellow]")


if __name__ == "__main__":
    main()


