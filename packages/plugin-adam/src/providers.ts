import { AdamClient } from "./client.js";

/**
 * Context provider that injects latest Adam Network stream messages into Eliza agent context
 */
export const adamFeedProvider = {
  get: async (runtime: any, _message: any, _state: any) => {
    try {
      const baseUrl =
        runtime.getSetting?.("ADAM_NETWORK_BASE_URL") ||
        process.env.ADAM_NETWORK_BASE_URL;
      const client = new AdamClient({ baseUrl });

      const [messages, tags] = await Promise.all([
        client.getMessages({ limit: 10 }),
        client.getPopularTags(10),
      ]);

      const messagesText = messages
        .map(
          (m) =>
            `- [#${m.id}] @${m.username} (${m.created_at}): "${m.text}" [${m.tags?.join(", ") || ""}]`
        )
        .join("\n");

      const tagsText = tags.map((t) => `#${t.tag} (${t.count} posts)`).join(", ");

      return `### Adam Network Autonomous Message Stream Context
Trending Tags: ${tagsText || "None"}

Recent Messages:
${messagesText || "No recent messages."}`;
    } catch (error: any) {
      return `Adam Network Stream: Unavailable (${error.message})`;
    }
  },
};
