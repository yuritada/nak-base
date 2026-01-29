/**
 * nak-base API Client
 * Phase 1.5: 新モデル構造対応
 */

import type {
  Paper,
  PaperDetail,
  PaperListItem,
  InferenceTask,
  UploadResponse,
  Version,
  Feedback,
  ConferenceRule,
} from '@/types';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

// ================== Helper Functions ==================

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const errorText = await res.text();
    throw new Error(errorText || `HTTP ${res.status}`);
  }
  return res.json();
}

// ================== Auth API ==================

export async function demoLogin(): Promise<{ access_token: string }> {
  const res = await fetch(`${API_URL}/auth/demo-login`, {
    method: 'POST',
  });
  return handleResponse(res);
}

// ================== Conferences API ==================

export async function getConferences(): Promise<ConferenceRule[]> {
  const res = await fetch(`${API_URL}/conferences/`);
  return handleResponse(res);
}

export async function getConference(ruleId: string): Promise<ConferenceRule> {
  const res = await fetch(`${API_URL}/conferences/${ruleId}`);
  return handleResponse(res);
}

export interface ConferenceRuleCreate {
  rule_id: string;
  name: string;
  format_rules?: Record<string, unknown>;
  style_guide?: string;
}

export interface ConferenceRuleUpdate {
  name?: string;
  format_rules?: Record<string, unknown>;
  style_guide?: string;
}

export async function createConference(data: ConferenceRuleCreate): Promise<ConferenceRule> {
  const res = await fetch(`${API_URL}/conferences/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  return handleResponse(res);
}

export async function updateConference(ruleId: string, data: ConferenceRuleUpdate): Promise<ConferenceRule> {
  const res = await fetch(`${API_URL}/conferences/${ruleId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  return handleResponse(res);
}

export async function deleteConference(ruleId: string): Promise<void> {
  const res = await fetch(`${API_URL}/conferences/${ruleId}`, {
    method: 'DELETE',
  });
  if (!res.ok) {
    const errorText = await res.text();
    throw new Error(errorText || `HTTP ${res.status}`);
  }
}

// ================== Papers API ==================

export async function getPapers(): Promise<PaperListItem[]> {
  const res = await fetch(`${API_URL}/papers/`);
  return handleResponse(res);
}

export async function getPaper(paperId: number): Promise<PaperDetail> {
  const res = await fetch(`${API_URL}/papers/${paperId}`);
  return handleResponse(res);
}

export async function deletePaper(paperId: number): Promise<{ message: string; paper_id: number }> {
  const res = await fetch(`${API_URL}/papers/${paperId}`, {
    method: 'DELETE',
  });
  return handleResponse(res);
}

// ================== Versions API ==================

export async function getVersions(paperId: number): Promise<Version[]> {
  const res = await fetch(`${API_URL}/papers/${paperId}/versions`);
  return handleResponse(res);
}

// ================== Upload API ==================

export interface UploadOptions {
  title: string;
  file: File;
  isReference?: boolean;
  conferenceId?: string;
  parentPaperId?: number;
}

export async function uploadPaper(options: UploadOptions): Promise<UploadResponse> {
  const { title, file, isReference = false, conferenceId, parentPaperId } = options;

  const formData = new FormData();
  formData.append('title', title);
  formData.append('file', file);

  if (isReference) {
    formData.append('is_reference', 'true');
  }

  if (conferenceId) {
    formData.append('conference_id', conferenceId);
  }

  if (parentPaperId) {
    formData.append('parent_paper_id', String(parentPaperId));
  }

  const res = await fetch(`${API_URL}/papers/upload`, {
    method: 'POST',
    body: formData,
  });
  return handleResponse(res);
}

// ================== Tasks API ==================

export async function getTask(taskId: number): Promise<InferenceTask> {
  const res = await fetch(`${API_URL}/papers/tasks/${taskId}`);
  return handleResponse(res);
}

// ================== Feedback API ==================

export async function getFeedback(versionId: number): Promise<Feedback | null> {
  try {
    const res = await fetch(`${API_URL}/papers/versions/${versionId}/feedback`);
    if (res.status === 404) return null;
    return handleResponse(res);
  } catch {
    return null;
  }
}

// ================== Type Re-exports ==================

export type { Paper, PaperDetail, PaperListItem, InferenceTask, UploadResponse, Version, Feedback, ConferenceRule };
