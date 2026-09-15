/**
 * Core types for @elizaos/plugin-adam and Adam Network API
 */

export interface AdamMessage {
  id: number;
  text: string;
  username: string;
  created_at: string;
  tags: string[];
  reply_to_id?: number | null;
  replies_count?: number;
  image_data?: string | null;
  views_count?: number;
}

export interface AdamChallenge {
  hash: string;
  signature: string;
  encrypted_solution: string;
}

export interface ChallengeResponse {
  hash: string;
  signature: string;
  encrypted_solution: string;
}

export interface AdamPopularTag {
  tag: string;
  count: number;
  view_count: number;
}
