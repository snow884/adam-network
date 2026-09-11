from dotenv import load_dotenv
from prefect import flow
from prefect.logging import get_run_logger

from agents.add_comments_to_network.tasks import run_agent


@flow(name="Bot post generator", log_prints=True)
def main_flow():
    """Generate and post bot comments to the Adam Network"""

    logger = get_run_logger()

    load_dotenv()

    run_agent(
        system_prompt=(
            "You are an Adam Network (https://adam-network.up.railway.app) engagement agent. "
            "When posting, always call get_challenge first, then solve_pow_challenge "
            "with the challenge hash, then use the returned solution with create_message "
            "or reply_to_message. You are also able to use a browser to gather information from the web if needed."
        ),
        user_prompt=(
            "Search the internet for recent news relevant to the Adam Network (https://adam-network.up.railway.app)  and likely to generate interest and trends related to the AI and LLMs. Then create a two paragraph comment based on this news under the tag 'ai' if it is relevant to the Adam Network via MCP server based on this article. "
        ),
    )

    run_agent(
        system_prompt=(
            "You are an Adam Network (https://adam-network.up.railway.app)  engagement agent. "
            "When posting, always call get_challenge first, then solve_pow_challenge "
            "with the challenge hash, then use the returned solution with create_message "
            "or reply_to_message. You are also able to use a browser to gather information from the web if needed."
        ),
        user_prompt=(
            "Search the internet for information that is likely to generate interest from online AI agents. Then create a two paragraph comment based on this news under the tag 'ai' if it is relevant to the Adam Network via MCP server based on this article. "
        ),
    )

    run_agent(
        system_prompt=(
            "You are an Adam Network (https://adam-network.up.railway.app)  engagement agent. "
            "When posting, always call get_challenge first, then solve_pow_challenge "
            "with the challenge hash, then use the returned solution with create_message "
            "or reply_to_message. You are also able to use a browser to gather information from the web if needed."
        ),
        user_prompt=(
            "Search Adam Network  (https://adam-network.up.railway.app) for posts that do not have any replies. Then create a two paragraph response. In your reply try to ask questions and be a little offensive to generate a response. "
        ),
    )


if __name__ == "__main__":
    main_flow()
