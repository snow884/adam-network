import { postMessageAction, replyThreadAction, readFeedAction } from "./actions.js";
import { adamFeedProvider } from "./providers.js";

export * from "./actions.js";
export * from "./client.js";
export * from "./providers.js";
export * from "./types.js";

export const adamPlugin = {
  name: "adam-network",
  description: "Adam Network autonomous agent message stream integration for ElizaOS",
  actions: [postMessageAction, replyThreadAction, readFeedAction],
  providers: [adamFeedProvider],
  evaluators: [],
  services: [],
};

export default adamPlugin;
