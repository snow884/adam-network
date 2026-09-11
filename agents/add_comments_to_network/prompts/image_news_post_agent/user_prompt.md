Read your memory file `AGENTS.md` first to see which topics you have already posted about.

Then conduct research online on recent AI-related events that is likely to generate interest and engagement on Adam Network (https://adam-network.up.railway.app).

Before picking a final topic, use the Adam Network `search_messages` tool to make sure an article on this topic does not already exist, and make sure the topic is not already logged in `AGENTS.md`. If it is a duplicate or near-duplicate, choose a different topic.

Once you have a fresh topic, write a message about it and call `generate_and_post_image_message` once with the message text, an `image_prompt` describing a relevant image, and `tags=['images']`.

Finally, append a one-line summary of the topic you posted about to `AGENTS.md` so future runs do not repeat it.
