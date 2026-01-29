/**
 * nak-base API Client
 * Phase 1.5: 新モデル構造対応
 */

import type {
  Paper,
  PaperDetail,
  InferenceTask,
  UploadResponse,
  Version,
  Feedback,
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

// ================== Papers API ==================

export async function getPapers(): Promise<Paper[]> {
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
}

export async function uploadPaper(options: UploadOptions): Promise<UploadResponse> {
  const { title, file, isReference = false } = options;

  const formData = new FormData();
  formData.append('title', title);
  formData.append('file', file);

  if (isReference) {
    formData.append('is_reference', 'true');
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

export type { Paper, PaperDetail, InferenceTask, UploadResponse, Version, Feedback };
