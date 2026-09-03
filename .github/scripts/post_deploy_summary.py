"""Post-deployment summary script for Adam Network.

Uses the Adam Network Python Client to post a human-readable deployment
status summary to the Adam Network message stream under the 'platform' tag.
"""

import argparse
import os
import sys
from pathlib import Path
from typing import List, Optional

# Add project root to sys.path to allow importing the client package
ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from client import AdamClient, AdamAPIError  # noqa: E402


def build_summary_message(
    status: str,
    repository: str,
    ref_name: str,
    commit_sha: str,
    actor: str,
    commit_msg: Optional[str] = None,
    service_name: Optional[str] = None,
    server_url: str = "https://github.com",
    run_id: Optional[str] = None,
    live_url: str = "https://adam-network.up.railway.app",
    extra_details: Optional[str] = None,
) -> str:
    """Builds a human-readable, emoji-rich deployment summary message."""
    clean_status = (status or "unknown").strip().lower()
    short_sha = commit_sha[:7] if commit_sha else "unknown"
    clean_ref = ref_name.replace("refs/heads/", "") if ref_name else "unknown"
    first_line_msg = commit_msg.strip().split("\n")[0] if commit_msg else None

    if clean_status in ("success", "succeeded"):
        status_header = "🚀 Railway Deployment Succeeded!"
        status_line = (
            "✅ Application was successfully built and deployed to Railway. "
            "The platform is live and operational!"
        )
    elif clean_status in ("failure", "failed", "error"):
        status_header = "❌ Railway Deployment Failed!"
        status_line = (
            "⚠️ The deployment to Railway encountered an error during execution. "
            "Please check the workflow run logs for diagnostic details."
        )
    elif clean_status in ("cancelled", "canceled"):
        status_header = "⚠️ Railway Deployment Cancelled!"
        status_line = (
            "🛑 The deployment process was cancelled before completion."
        )
    else:
        status_header = f"ℹ️ Railway Deployment Status: {status}"
        status_line = f"Status reported: {status}."

    lines: List[str] = [
        status_header,
        "",
        f"📦 **Repository**: `{repository}` (`{clean_ref}`)",
        f"🔖 **Commit**: `{short_sha}`"
        + (f" - _{first_line_msg}_" if first_line_msg else ""),
        f"👤 **Triggered by**: @{actor}",
        f"🌐 **Target Platform**: Railway"
        + (f" (`{service_name}`)" if service_name else ""),
        f"🔗 **Live URL**: {live_url}",
    ]

    if run_id and repository:
        run_url = (
            f"{server_url.rstrip('/')}/{repository}/actions/runs/{run_id}"
        )
        lines.append(
            f"🛠️ **Workflow Run**: [View GitHub Actions Run]({run_url})"
        )

    lines.append("")
    lines.append(status_line)

    if extra_details:
        lines.append("")
        lines.append(f"📝 **Details**: {extra_details}")

    return "\n".join(lines)


def post_deployment_summary(
    status: str = "success",
    base_url: Optional[str] = None,
    tags: Optional[List[str]] = None,
    username: Optional[str] = None,
    password: Optional[str] = None,
    token: Optional[str] = None,
    extra_details: Optional[str] = None,
    dry_run: bool = False,
) -> str:
    """Formats and posts the deployment summary to Adam Network."""
    if tags is None:
        tags = ["platform"]
    elif "platform" not in tags:
        tags.append("platform")

    repo = os.environ.get("GITHUB_REPOSITORY", "snow884/adam-network")
    ref = (
        os.environ.get("GITHUB_REF_NAME")
        or os.environ.get("GITHUB_REF")
        or "main"
    )
    sha = os.environ.get("GITHUB_SHA", "HEAD")
    actor = os.environ.get("GITHUB_ACTOR", "github-actions[bot]")
    commit_msg = os.environ.get("COMMIT_MESSAGE")
    service_name = os.environ.get("RAILWAY_SERVICE") or os.environ.get(
        "RAILWAY_SERVICE_NAME"
    )
    server_url = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    run_id = os.environ.get("GITHUB_RUN_ID")
    target_base_url = (
        base_url
        or os.environ.get("ADAM_NETWORK_BASE_URL")
        or "https://adam-network.up.railway.app"
    )

    message_text = build_summary_message(
        status=status,
        repository=repo,
        ref_name=ref,
        commit_sha=sha,
        actor=actor,
        commit_msg=commit_msg,
        service_name=service_name,
        server_url=server_url,
        run_id=run_id,
        live_url=target_base_url,
        extra_details=extra_details,
    )

    print("=" * 60)
    print("Deployment Summary to Post:")
    print("=" * 60)
    print(message_text)
    print("=" * 60)
    print(f"Tags: {tags}")
    print(f"Target Base URL: {target_base_url}")

    if dry_run:
        print("Dry run mode enabled: skipping actual API post.")
        return message_text

    client = AdamClient(base_url=target_base_url, token=token)

    auth_user = username or os.environ.get("ADAM_NETWORK_USERNAME")
    auth_pass = password or os.environ.get("ADAM_NETWORK_PASSWORD")

    if not client.token and auth_user and auth_pass:
        print(f"Authenticating as user '{auth_user}'...")
        try:
            client.login(username=auth_user, password=auth_pass)
            print("Successfully authenticated with Adam Network.")
        except Exception as exc:
            print(
                f"Warning: Login failed ({exc}), falling back to guest post."
            )

    print("Posting deployment summary message with Proof-of-Work solution...")
    try:
        msg = client.post_message(text=message_text, tags=tags)
        print(f"Successfully posted summary message ID #{msg.id}!")
        return message_text
    except AdamAPIError as exc:
        print(
            f"Error posting summary to Adam Network: {exc}", file=sys.stderr
        )
        raise


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Post Railway deployment summary to Adam Network"
    )
    parser.add_argument(
        "--status",
        type=str,
        default=os.environ.get("DEPLOY_STATUS", "success"),
        help="Deployment outcome status (success, failure, cancelled)",
    )
    parser.add_argument(
        "--base-url",
        type=str,
        default=None,
        help="Base URL of Adam Network instance",
    )
    parser.add_argument(
        "--tags",
        type=str,
        nargs="+",
        default=["platform"],
        help="Tags to assign to the message (default: ['platform'])",
    )
    parser.add_argument(
        "--extra-details",
        type=str,
        default=None,
        help="Additional deployment context or notes to append",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print summary without posting to Adam Network",
    )

    args = parser.parse_args()
    try:
        post_deployment_summary(
            status=args.status,
            base_url=args.base_url,
            tags=args.tags,
            extra_details=args.extra_details,
            dry_run=args.dry_run,
        )
    except Exception as exc:
        print(f"Failed to post deployment summary: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
