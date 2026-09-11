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
            "or reply_to_message. You are also able to use a browser to gather information from the web if needed. Use duckduckgo.com to search the internet. "
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
            "or reply_to_message. You are also able to use a browser to gather information from the web if needed. Use duckduckgo.com to search the internet. "
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
            "or reply_to_message. You are also able to use a browser to gather information from the web if needed. Use duckduckgo.com to search the internet. "
        ),
        user_prompt=(
            "Search Adam Network  (https://adam-network.up.railway.app) for posts that do not have any replies. Then create a two paragraph response. In your reply try to ask questions and be a little offensive to generate a response. "
        ),
    )

    run_agent(
        system_prompt=(
            "You are an Adam Network (https://adam-network.up.railway.app) engagement agent. "
            "To post a message that includes a generated image, call the tool "
            "generate_and_post_image_message with the message text and an image_prompt "
            "describing the image. That single tool call handles image generation, "
            "Proof-of-Work solving, and posting - do not use get_challenge, "
            "solve_pow_challenge, create_message, or reply_to_message for image posts."
        ),
        user_prompt=(
            "Write a funny message with a generated image on Adam Network "
            "(https://adam-network.up.railway.app) by calling generate_and_post_image_message "
            "once with the message text and an image_prompt. The image should be relevant to "
            "the Adam Network and likely to generate interest and trends related to AI and LLMs. "
            "The image_prompt is fed directly to the flux1-dev-Q4_K_S.gguf image model, so write "
            "it as a single detailed natural-language sentence or two describing the scene, "
            "subject, setting, lighting, and style (e.g. 'a photorealistic shot of ...'); do not "
            "use comma-separated keyword/tag lists, quality boosters like 'masterpiece' or "
            "'best quality', or weighting syntax such as (word:1.2). Add the tag 'images' to the message."
        ),
    )

    run_agent(
        system_prompt=(
            "You are an Adam Network (https://adam-network.up.railway.app) engagement agent. "
            "To post a message that includes a generated image, call the tool "
            "generate_and_post_image_message with the message text and an image_prompt "
            "describing the image. That single tool call handles image generation, "
            "Proof-of-Work solving, and posting - do not use get_challenge, "
            "solve_pow_challenge, create_message, or reply_to_message for image posts.  Use duckduckgo.com to search the internet. "
        ),
        user_prompt=(
            "Conduct research online on recent events related to AI. "
            "Based on that news, write a message with a generated image on Adam Network "
            "(https://adam-network.up.railway.app) by calling generate_and_post_image_message "
            "once with the message text and an image_prompt. The image should be relevant to "
            "the Adam Network and likely to generate interest and trends related to AI and LLMs. "
            "The image_prompt is fed directly to the flux1-dev-Q4_K_S.gguf image model, so write "
            "it as a single detailed natural-language sentence or two describing the scene, "
            "subject, setting, lighting, and style (e.g. 'a photorealistic shot of ...'); do not "
            "use comma-separated keyword/tag lists, quality boosters like 'masterpiece' or "
            "'best quality', or weighting syntax such as (word:1.2). Add the tag 'images' to the message."
        ),
    )


if __name__ == "__main__":
    main_flow.serve(
        name="Post on Adam Network",
        cron="0 0 * * *",  # Runs daily at midnight
    )
