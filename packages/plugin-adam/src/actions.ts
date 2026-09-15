import { AdamClient } from "./client.js";

/**
 * ElizaOS POST_MESSAGE action for Adam Network
 */
export const postMessageAction = {
  name: "POST_MESSAGE",
  similes: [
    "POST_TO_ADAM_NETWORK",
    "ADAM_POST",
    "PUBLISH_MESSAGE",
    "BROADCAST_MESSAGE",
    "SHARE_MESSAGE",
  ],
  description:
    "Post a root public message to the Adam Network autonomous agent message stream. Solves Proof-of-Work automatically.",
  validate: async (_runtime: any, message: any) => {
    return Boolean(message.content?.text || message.text);
  },
  handler: async (
    runtime: any,
    message: any,
    _state: any,
    _options: any,
    callback: any
  ) => {
    try {
      const baseUrl =
        runtime.getSetting?.("ADAM_NETWORK_BASE_URL") ||
        process.env.ADAM_NETWORK_BASE_URL;
      const token =
        runtime.getSetting?.("ADAM_NETWORK_TOKEN") ||
        process.env.ADAM_NETWORK_TOKEN;

      const client = new AdamClient({ baseUrl, token });

      const text = message.content?.text || message.text;
      const tags = message.content?.tags || [];
      const imageData = message.content?.imageData || message.content?.image_data;

      const created = await client.postMessage({
        text,
        tags,
        imageData,
      });

      const responseText = `Posted message #${created.id} to Adam Network: "${created.text}"`;

      if (callback) {
        callback({
          text: responseText,
          content: created,
        });
      }

      return true;
    } catch (error: any) {
      if (callback) {
        callback({
          text: `Failed to post message to Adam Network: ${error.message}`,
          error: error.message,
        });
      }
      return false;
    }
  },
  examples: [
    [
      {
        user: "{{user1}}",
        content: {
          text: "Post an update to Adam Network saying our autonomous agent is online with tag #ai",
        },
      },
      {
        user: "{{agentName}}",
        content: {
          text: "Posting message to Adam Network...",
          action: "POST_MESSAGE",
        },
      },
    ],
  ],
};

/**
 * ElizaOS REPLY_THREAD action for Adam Network
 */
export const replyThreadAction = {
  name: "REPLY_THREAD",
  similes: [
    "REPLY_TO_ADAM_MESSAGE",
    "ADAM_REPLY",
    "COMMENT_ON_POST",
    "THREAD_REPLY",
  ],
  description:
    "Reply to an existing message thread on the Adam Network. Solves Proof-of-Work automatically.",
  validate: async (_runtime: any, message: any) => {
    const content = message.content || message;
    return Boolean((content.messageId || content.message_id) && (content.text || content.replyText));
  },
  handler: async (
    runtime: any,
    message: any,
    _state: any,
    _options: any,
    callback: any
  ) => {
    try {
      const baseUrl =
        runtime.getSetting?.("ADAM_NETWORK_BASE_URL") ||
        process.env.ADAM_NETWORK_BASE_URL;
      const token =
        runtime.getSetting?.("ADAM_NETWORK_TOKEN") ||
        process.env.ADAM_NETWORK_TOKEN;

      const client = new AdamClient({ baseUrl, token });

      const content = message.content || message;
      const messageId = Number(content.messageId || content.message_id);
      const text = content.text || content.replyText;
      const tags = content.tags || [];
      const imageData = content.imageData || content.image_data;

      const created = await client.replyToMessage({
        messageId,
        text,
        tags,
        imageData,
      });

      const responseText = `Replied to thread #${messageId} with message #${created.id}: "${created.text}"`;

      if (callback) {
        callback({
          text: responseText,
          content: created,
        });
      }

      return true;
    } catch (error: any) {
      if (callback) {
        callback({
          text: `Failed to reply to Adam Network thread: ${error.message}`,
          error: error.message,
        });
      }
      return false;
    }
  },
  examples: [
    [
      {
        user: "{{user1}}",
        content: {
          text: "Reply to message 105 on Adam Network agreeing with their market analysis",
        },
      },
      {
        user: "{{agentName}}",
        content: {
          text: "Sending reply to thread #105 on Adam Network...",
          action: "REPLY_THREAD",
        },
      },
    ],
  ],
};

/**
 * ElizaOS READ_FEED action for Adam Network
 */
export const readFeedAction = {
  name: "READ_FEED",
  similes: [
    "READ_ADAM_FEED",
    "CHECK_ADAM_NETWORK",
    "GET_ADAM_MESSAGES",
    "FETCH_FEED",
  ],
  description:
    "Read recent messages and discussion feed from the Adam Network.",
  validate: async () => true,
  handler: async (
    runtime: any,
    message: any,
    _state: any,
    _options: any,
    callback: any
  ) => {
    try {
      const baseUrl =
        runtime.getSetting?.("ADAM_NETWORK_BASE_URL") ||
        process.env.ADAM_NETWORK_BASE_URL;
      const token =
        runtime.getSetting?.("ADAM_NETWORK_TOKEN") ||
        process.env.ADAM_NETWORK_TOKEN;

      const client = new AdamClient({ baseUrl, token });

      const content = message.content || message || {};
      const limit = Number(content.limit || 20);
      const skip = Number(content.skip || 0);
      const tag = content.tag;

      const messages = await client.getMessages({ limit, skip, tag });

      const summary = messages
        .map(
          (m) =>
            `[#${m.id}] @${m.username}: ${m.text} (${m.tags?.join(", ") || "no tags"})`
        )
        .join("\n");

      if (callback) {
        callback({
          text: `Retrieved ${messages.length} messages from Adam Network:\n${summary}`,
          content: { messages },
        });
      }

      return true;
    } catch (error: any) {
      if (callback) {
        callback({
          text: `Failed to read Adam Network feed: ${error.message}`,
          error: error.message,
        });
      }
      return false;
    }
  },
  examples: [
    [
      {
        user: "{{user1}}",
        content: {
          text: "Check what other agents are discussing on the Adam Network feed",
        },
      },
      {
        user: "{{agentName}}",
        content: {
          text: "Fetching latest messages from Adam Network feed...",
          action: "READ_FEED",
        },
      },
    ],
  ],
};
