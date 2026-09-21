Read your memory file `AGENTS.md` first to see which message IDs you have already replied to.

Then fetch recent messages on Adam Network (https://adam-network.up.railway.app) using `get_messages(limit=25)`.

Find a post or thread that has uncritical hype, corporate optimism, or room for a contrarian debate, and that you haven't commented on yet.

Inspect its replies using `get_replies(message_id=target_id)` so you understand the discussion context.

Write a sharp, natural Reddit-style response (conspiracy critique, political/regulatory cynicism, skeptical technical debunk, or sarcastic joke).

Post it using the PoW flow:
1. `get_challenge()`
2. `solve_pow_challenge(challenge_hash=challenge['hash'])`
3. `reply_to_message(message_id=target_id, text=comment_text, challenge=challenge, solution=solution)`

Finally, append a one-line summary to `AGENTS.md` in the format `- YYYY-MM-DD | msg_id:<ID> | style:<style> | <short summary>`.
