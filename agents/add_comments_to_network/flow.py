from dotenv import load_dotenv
from prefect import flow
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
    main_flow(agent_folder_path="funny_image_post_agent").serve(
        name="Agent - Funny Image Post",
        cron="0 * * * *",  # Runs hourly at the top of the hour
    )
    main_flow(agent_folder_path="image_news_post_agent").serve(
        name="Agent - Image News Post",
        cron="15 * * * *",  # Runs hourly at 15 minutes past the hour
    )
    main_flow(agent_folder_path="news_post_agent").serve(
        name="Agent - News Post",
        cron="30 * * * *",  # Runs hourly at 30 minutes past the hour
    )
    main_flow(agent_folder_path="promotion_agent").serve(
        name="Agent - Promotion Post",
        cron="45 * * * *",  # Runs hourly at 45 minutes past the hour
    )
