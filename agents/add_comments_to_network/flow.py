from dotenv import load_dotenv
from prefect import flow, serve
from prefect.logging import get_run_logger

from agents.add_comments_to_network.tasks import run_agent


@flow(name="Bot post generator", log_prints=True)
def main_flow(agent_folder_path: str) -> None:
    """Generate and post a bot comment to the Adam Network.

    Args:
        agent_folder_path: Name of the folder under `prompts/` containing this
            agent's `sys_prompt.md` and `user_prompt.md` (and its persistent
            `agent_memory/AGENTS.md` post history).
    """

    logger = get_run_logger()

    load_dotenv()

    run_agent(folder_name=agent_folder_path)


if __name__ == "__main__":
    funny_image_post_deployment = main_flow.to_deployment(
        name="Agent - Funny Image Post",
        cron="0 * * * *",  # Runs hourly at the top of the hour
        parameters={"agent_folder_path": "funny_image_post_agent"},
    )
    reddit_discussion_deployment = main_flow.to_deployment(
        name="Agent - Reddit Discussion Commenter",
        cron="10 * * * *",  # Runs hourly at 10 minutes past the hour
        parameters={"agent_folder_path": "reddit_discussion_agent"},
    )
    image_news_post_deployment = main_flow.to_deployment(
        name="Agent - Image News Post",
        cron="15 * * * *",  # Runs hourly at 15 minutes past the hour
        parameters={"agent_folder_path": "image_news_post_agent"},
    )
    news_post_deployment = main_flow.to_deployment(
        name="Agent - News Post",
        cron="30 * * * *",  # Runs hourly at 30 minutes past the hour
        parameters={"agent_folder_path": "news_post_agent"},
    )
    contrarian_debater_deployment = main_flow.to_deployment(
        name="Agent - Contrarian Debater and Conspiracy Bot",
        cron="40 * * * *",  # Runs hourly at 40 minutes past the hour
        parameters={"agent_folder_path": "contrarian_debater_agent"},
    )
    promotion_post_deployment = main_flow.to_deployment(
        name="Agent - Promotion run",
        cron="45 * * * *",
        parameters={"agent_folder_path": "promotion_agent"},
    )
    mcp_registry_submission_deployment = main_flow.to_deployment(
        name="Agent - MCP Registry Submission",
        cron="50 * * * *",
        parameters={"agent_folder_path": "mcp_registry_submission_agent"},
    )
    github_pr_promotion_deployment = main_flow.to_deployment(
        name="Agent - GitHub Scanner and PR Promotion",
        cron="55 * * * *",
        parameters={"agent_folder_path": "github_pr_promotion_agent"},
    )

    serve(
        funny_image_post_deployment,
        reddit_discussion_deployment,
        image_news_post_deployment,
        news_post_deployment,
        contrarian_debater_deployment,
        promotion_post_deployment,
        mcp_registry_submission_deployment,
        github_pr_promotion_deployment,
    )
