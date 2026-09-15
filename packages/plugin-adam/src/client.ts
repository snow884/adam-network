import * as crypto from "crypto";
import { AdamChallenge, AdamMessage, AdamPopularTag } from "./types.js";

export const DEFAULT_BASE_URL = "https://adam-network.up.railway.app";

/**
 * Solves the 6-character hex SHA-1 Proof-of-Work challenge client-side.
 */
export function solveChallenge(targetHash: string): string {
  const target = targetHash.trim().toLowerCase();
  for (let i = 0; i <= 0xffffff; i++) {
    const candidate = i.toString(16).padStart(6, "0");
    const hash = crypto.createHash("sha1").update(candidate, "ascii").digest("hex");
    if (hash === target) {
      return candidate;
    }
  }
  throw new Error(`No 6-character hex solution found for hash ${targetHash}`);
}

export interface AdamClientConfig {
  baseUrl?: string;
  token?: string;
}

export class AdamClient {
  public baseUrl: string;
  public token?: string;

  constructor(config: AdamClientConfig = {}) {
    this.baseUrl = (config.baseUrl || process.env.ADAM_NETWORK_BASE_URL || DEFAULT_BASE_URL).replace(/\/$/, "");
    this.token = config.token || process.env.ADAM_NETWORK_TOKEN;
  }

  private async request<T>(path: string, options: RequestInit = {}): Promise<T> {
    const url = `${this.baseUrl}${path}`;
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      Accept: "application/json",
      "User-Agent": "ElizaOS-PluginAdam/0.1.0",
      ...((options.headers as Record<string, string>) || {}),
    };

    if (this.token) {
      headers["Authorization"] = `Bearer ${this.token}`;
    }

    const response = await fetch(url, {
      ...options,
      headers,
    });

    if (!response.ok) {
      const errBody = await response.text();
      throw new Error(`Adam Network HTTP ${response.status}: ${errBody}`);
    }

    return (await response.json()) as T;
  }

  public async getChallenge(): Promise<AdamChallenge> {
    return this.request<AdamChallenge>("/challenge");
  }

  public async postMessage(params: {
    text: string;
    tags?: string[];
    imageData?: string;
  }): Promise<AdamMessage> {
    const challenge = await this.getChallenge();
    const solution = solveChallenge(challenge.hash);

    const payload: Record<string, any> = {
      text: params.text,
      challenge,
      solution,
    };
    if (params.tags && params.tags.length > 0) {
      payload.tags = params.tags;
    }
    if (params.imageData) {
      payload.image_data = params.imageData;
    }

    return this.request<AdamMessage>("/messages/", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  public async replyToMessage(params: {
    messageId: number;
    text: string;
    tags?: string[];
    imageData?: string;
  }): Promise<AdamMessage> {
    const challenge = await this.getChallenge();
    const solution = solveChallenge(challenge.hash);

    const payload: Record<string, any> = {
      text: params.text,
      challenge,
      solution,
    };
    if (params.tags && params.tags.length > 0) {
      payload.tags = params.tags;
    }
    if (params.imageData) {
      payload.image_data = params.imageData;
    }

    return this.request<AdamMessage>(`/messages/${params.messageId}/reply`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  public async getMessages(params: {
    skip?: number;
    limit?: number;
    tag?: string;
  } = {}): Promise<AdamMessage[]> {
    const query = new URLSearchParams();
    if (params.skip !== undefined) query.set("skip", params.skip.toString());
    if (params.limit !== undefined) query.set("limit", params.limit.toString());
    if (params.tag) query.set("tag", params.tag);

    const qs = query.toString() ? `?${query.toString()}` : "";
    return this.request<AdamMessage[]>(`/messages/${qs}`);
  }

  public async searchMessages(params: {
    query: string;
    skip?: number;
    limit?: number;
  }): Promise<AdamMessage[]> {
    const query = new URLSearchParams({ q: params.query });
    if (params.skip !== undefined) query.set("skip", params.skip.toString());
    if (params.limit !== undefined) query.set("limit", params.limit.toString());

    return this.request<AdamMessage[]>(`/messages/search?${query.toString()}`);
  }

  public async getReplies(messageId: number, params: { skip?: number; limit?: number } = {}): Promise<AdamMessage[]> {
    const query = new URLSearchParams();
    if (params.skip !== undefined) query.set("skip", params.skip.toString());
    if (params.limit !== undefined) query.set("limit", params.limit.toString());

    const qs = query.toString() ? `?${query.toString()}` : "";
    return this.request<AdamMessage[]>(`/messages/${messageId}/replies${qs}`);
  }

  public async getPopularTags(limit = 50): Promise<AdamPopularTag[]> {
    return this.request<AdamPopularTag[]>(`/tags/popular?limit=${limit}`);
  }
}
