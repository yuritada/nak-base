const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export interface User {
  user_id: number;
  email: string;
  name: string;
  role: 'Student' | 'Professor';
  created_at: string;
}

export interface Paper {
  paper_id: number;
  user_id: number;
  title: string;
  target_conference: string | null;
  status: 'Draft' | 'Processing' | 'Completed' | 'Error';
  created_at: string;
  updated_at: string;
}

export interface Version {
  version_id: number;
  paper_id: number;
  drive_file_id: string;
  version_number: number;
  file_name: string;
  file_type: string;
  created_at: string;
}

export interface Feedback {
  feedback_id: number;
  version_id: number;
  report_drive_id: string | null;
  score_json: {
    overall: number;
    format: number;
    logic: number;
    novelty: number;
    improvement: number | null;
  } | null;
  comments_json: Record<string, unknown> | null;
  overall_summary: string | null;
  created_at: string;
}

export interface TaskStatus {
  task_id: number;
  version_id: number;
  status: 'Pending' | 'Processing' | 'Completed' | 'Error';
  error_message: string | null;
  conference_rule_id: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}

export interface ConferenceRule {
  rule_id: string;
  name: string;
  format_rules: Record<string, unknown> | null;
  style_guide: string | null;
}

export interface DashboardData {
  total_students: number;
  total_papers: number;
  papers_in_progress: number;
  papers_completed: number;
  student_papers: {
    user_id: number;
    user_name: string;
    paper_id: number;
    paper_title: string;
    latest_version: number;
    status: string;
    latest_score: { overall: number } | null;
  }[];
}

// Users API
export async function createUser(data: { email: string; name: string; role: string }): Promise<User> {
  const res = await fetch(`${API_URL}/users/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error('Failed to create user');
  return res.json();
}

export async function getUsers(): Promise<User[]> {
  const res = await fetch(`${API_URL}/users/`);
  if (!res.ok) throw new Error('Failed to fetch users');
  return res.json();
}

export async function getUserByEmail(email: string): Promise<User> {
  const res = await fetch(`${API_URL}/users/email/${encodeURIComponent(email)}`);
  if (!res.ok) throw new Error('User not found');
  return res.json();
}

// Papers API
export async function createPaper(userId: number, data: { title: string; target_conference?: string }): Promise<Paper> {
  const res = await fetch(`${API_URL}/papers/?user_id=${userId}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error('Failed to create paper');
  return res.json();
}

export async function getPapers(userId?: number): Promise<Paper[]> {
  const url = userId ? `${API_URL}/papers/?user_id=${userId}` : `${API_URL}/papers/`;
  const res = await fetch(url);
  if (!res.ok) throw new Error('Failed to fetch papers');
  return res.json();
}

export async function getPaper(paperId: number): Promise<Paper & { versions: Version[] }> {
  const res = await fetch(`${API_URL}/papers/${paperId}`);
  if (!res.ok) throw new Error('Failed to fetch paper');
  return res.json();
}

export async function uploadPaperVersion(
  paperId: number,
  file: File,
  conferenceRuleId: string = 'GENERAL'
): Promise<{ message: string; paper_id: number; version_id: number; task_id: number }> {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('conference_rule_id', conferenceRuleId);

  const res = await fetch(`${API_URL}/papers/${paperId}/upload`, {
    method: 'POST',
    body: formData,
  });
  if (!res.ok) throw new Error('Failed to upload file');
  return res.json();
}

// Feedback API
export async function getFeedbackByVersion(versionId: number): Promise<Feedback[]> {
  const res = await fetch(`${API_URL}/feedbacks/version/${versionId}`);
  if (!res.ok) throw new Error('Failed to fetch feedback');
  return res.json();
}

export async function getTaskStatus(taskId: number): Promise<TaskStatus> {
  const res = await fetch(`${API_URL}/feedbacks/task/${taskId}`);
  if (!res.ok) throw new Error('Failed to fetch task status');
  return res.json();
}

// Dashboard API
export async function getProfessorDashboard(): Promise<DashboardData> {
  const res = await fetch(`${API_URL}/dashboard/professor`);
  if (!res.ok) throw new Error('Failed to fetch dashboard');
  return res.json();
}

export async function getStudentDashboard(userId: number): Promise<unknown> {
  const res = await fetch(`${API_URL}/dashboard/student/${userId}`);
  if (!res.ok) throw new Error('Failed to fetch dashboard');
  return res.json();
}

export async function getConferenceRules(): Promise<ConferenceRule[]> {
  const res = await fetch(`${API_URL}/dashboard/conference-rules`);
  if (!res.ok) throw new Error('Failed to fetch conference rules');
  return res.json();
}
