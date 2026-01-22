/**
 * MVP版 API Client
 * シンプルなAPI関数
 */

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export interface Paper {
  id: number;
  user_id: number;
  title: string;
  created_at: string;
}

export interface Task {
  id: number;
  paper_id: number;
  file_path: string;
  parsed_text: string | null;
  status: 'pending' | 'processing' | 'completed' | 'error';
  result_json: {
    summary?: string;
    typos?: string[];
    suggestions?: string[];
    error?: string;
  } | null;
  created_at: string;
  updated_at: string;
}

export interface PaperWithTasks extends Paper {
  tasks: Task[];
}

// Auth API
export async function demoLogin(): Promise<{ access_token: string }> {
  const res = await fetch(`${API_URL}/auth/demo-login`, {
    method: 'POST',
  });
  if (!res.ok) throw new Error('Login failed');
  return res.json();
}

// Papers API
export async function getPapers(): Promise<Paper[]> {
  const res = await fetch(`${API_URL}/papers/`);
  if (!res.ok) throw new Error('Failed to fetch papers');
  return res.json();
}

export async function getPaper(paperId: number): Promise<PaperWithTasks> {
  const res = await fetch(`${API_URL}/papers/${paperId}`);
  if (!res.ok) throw new Error('Failed to fetch paper');
  return res.json();
}

export async function uploadPaper(
  title: string,
  file: File
): Promise<{ message: string; paper_id: number; task_id: number }> {
  const formData = new FormData();
  formData.append('title', title);
  formData.append('file', file);

  const res = await fetch(`${API_URL}/papers/upload`, {
    method: 'POST',
    body: formData,
  });
  if (!res.ok) throw new Error('Failed to upload file');
  return res.json();
}

export async function getTask(taskId: number): Promise<Task> {
  const res = await fetch(`${API_URL}/papers/tasks/${taskId}`);
  if (!res.ok) throw new Error('Failed to fetch task');
  return res.json();
}
