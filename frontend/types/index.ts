/**
 * Phase 1.5 型定義
 * バックエンドの新しいデータ構造に対応
 */

// ================== Enum Definitions ==================

export type UserRoleEnum = 'ADMIN' | 'PROFESSOR' | 'STUDENT';

export type FileRoleEnum = 'MAIN_PDF' | 'SOURCE_TEX' | 'ADDITIONAL_FILE';

export type TaskStatusEnum = 'PENDING' | 'PARSING' | 'RAG' | 'LLM' | 'COMPLETED' | 'ERROR';

export type PaperStatusEnum =
  | 'UPLOADED'
  | 'PROCESSING'
  | 'PARSED'
  | 'EMBEDDED'
  | 'FAILED'
  | 'COMPLETED'
  | 'ERROR';

// ================== Core Types ==================

export interface Paper {
  paper_id: number;
  owner_id: number | null;
  title: string;
  status: PaperStatusEnum;
  is_deleted: boolean;
  created_at: string | null;
}

export interface Version {
  version_id: number;
  paper_id: number;
  version_number: number;
  created_at: string | null;
}

export interface FileRecord {
  file_id: number;
  version_id: number;
  file_role: FileRoleEnum;
  is_primary: boolean;
  cache_path: string | null;
  is_cached: boolean;
  original_filename: string | null;
  created_at: string | null;
}

export interface InferenceTask {
  task_id: number;
  version_id: number;
  status: TaskStatusEnum;
  error_message: string | null;
  retry_count: number;
  started_at: string | null;
  completed_at: string | null;
  created_at: string | null;
}

export interface Feedback {
  feedback_id: number;
  version_id: number;
  task_id: number | null;
  score_json: Record<string, unknown> | null;
  comments_json: Record<string, unknown> | null;
  overall_summary: string | null;
  created_at: string | null;
}

// ================== Composite Types ==================

export interface VersionWithFiles extends Version {
  files: FileRecord[];
}

export interface PaperWithVersions extends Paper {
  versions: Version[];
}

export interface PaperDetail extends Paper {
  versions: VersionWithFiles[];
}

// ================== API Response Types ==================

export interface UploadResponse {
  message: string;
  paper_id: number;
  version_id: number;
  task_id: number;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

// ================== SSE Event Types ==================

export interface SSENotificationEvent {
  task_id: number;
  status: TaskStatusEnum;
  phase?: string;
  error_message?: string;
}

// ================== UI Helper Types ==================

export interface StatusDisplay {
  label: string;
  color: 'green' | 'yellow' | 'red' | 'blue' | 'gray';
  isLoading: boolean;
}

export function getTaskStatusDisplay(status: TaskStatusEnum, phase?: string): StatusDisplay {
  switch (status) {
    case 'PENDING':
      return { label: '待機中', color: 'gray', isLoading: false };
    case 'PARSING':
      return { label: phase || 'PDF解析中', color: 'yellow', isLoading: true };
    case 'RAG':
      return { label: phase || 'RAG処理中', color: 'yellow', isLoading: true };
    case 'LLM':
      return { label: phase || 'AI分析中', color: 'blue', isLoading: true };
    case 'COMPLETED':
      return { label: '完了', color: 'green', isLoading: false };
    case 'ERROR':
      return { label: 'エラー', color: 'red', isLoading: false };
    default:
      return { label: '不明', color: 'gray', isLoading: false };
  }
}

export function getPaperStatusDisplay(status: PaperStatusEnum): StatusDisplay {
  switch (status) {
    case 'UPLOADED':
      return { label: 'アップロード済み', color: 'gray', isLoading: false };
    case 'PROCESSING':
      return { label: '処理中', color: 'yellow', isLoading: true };
    case 'PARSED':
      return { label: '解析済み', color: 'blue', isLoading: false };
    case 'EMBEDDED':
      return { label: '埋め込み済み', color: 'blue', isLoading: false };
    case 'COMPLETED':
      return { label: '完了', color: 'green', isLoading: false };
    case 'FAILED':
    case 'ERROR':
      return { label: 'エラー', color: 'red', isLoading: false };
    default:
      return { label: '不明', color: 'gray', isLoading: false };
  }
}
