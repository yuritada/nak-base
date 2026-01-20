'use client';

import { useState, useCallback, useEffect } from 'react';
import { useDropzone } from 'react-dropzone';
import { Upload, FileText, CheckCircle, AlertCircle, Loader2 } from 'lucide-react';
import { createPaper, uploadPaperVersion, getTaskStatus, getConferenceRules, getUsers, type ConferenceRule, type User } from '@/lib/api';

type UploadStatus = 'idle' | 'uploading' | 'processing' | 'completed' | 'error';

export default function UploadPage() {
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState('');
  const [conferenceRule, setConferenceRule] = useState('GENERAL');
  const [userId, setUserId] = useState<number | null>(null);
  const [status, setStatus] = useState<UploadStatus>('idle');
  const [taskId, setTaskId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [conferenceRules, setConferenceRules] = useState<ConferenceRule[]>([]);
  const [users, setUsers] = useState<User[]>([]);

  useEffect(() => {
    getConferenceRules().then(setConferenceRules).catch(console.error);
    getUsers().then(setUsers).catch(console.error);
  }, []);

  const onDrop = useCallback((acceptedFiles: File[]) => {
    if (acceptedFiles.length > 0) {
      const f = acceptedFiles[0];
      setFile(f);
      if (!title) {
        setTitle(f.name.replace(/\.(pdf|tex)$/i, ''));
      }
    }
  }, [title]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'application/pdf': ['.pdf'],
      'application/x-tex': ['.tex'],
      'text/x-tex': ['.tex'],
    },
    maxFiles: 1,
  });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file || !title || !userId) return;

    setStatus('uploading');
    setError(null);

    try {
      // Create paper
      const paper = await createPaper(userId, { title, target_conference: conferenceRule });

      // Upload file
      const result = await uploadPaperVersion(paper.paper_id, file, conferenceRule);
      setTaskId(result.task_id);
      setStatus('processing');

      // Poll for completion
      const pollInterval = setInterval(async () => {
        try {
          const taskStatus = await getTaskStatus(result.task_id);
          if (taskStatus.status === 'Completed') {
            clearInterval(pollInterval);
            setStatus('completed');
          } else if (taskStatus.status === 'Error') {
            clearInterval(pollInterval);
            setStatus('error');
            setError(taskStatus.error_message || 'An error occurred');
          }
        } catch (err) {
          console.error('Poll error:', err);
        }
      }, 3000);

    } catch (err) {
      setStatus('error');
      setError(err instanceof Error ? err.message : 'Upload failed');
    }
  };

  const getStatusDisplay = () => {
    switch (status) {
      case 'uploading':
        return (
          <div className="flex items-center text-blue-600">
            <Loader2 className="w-5 h-5 mr-2 animate-spin" />
            アップロード中...
          </div>
        );
      case 'processing':
        return (
          <div className="flex items-center text-yellow-600">
            <Loader2 className="w-5 h-5 mr-2 animate-spin" />
            AI分析中... (タスクID: {taskId})
          </div>
        );
      case 'completed':
        return (
          <div className="flex items-center text-green-600">
            <CheckCircle className="w-5 h-5 mr-2" />
            分析完了！
          </div>
        );
      case 'error':
        return (
          <div className="flex items-center text-red-600">
            <AlertCircle className="w-5 h-5 mr-2" />
            エラー: {error}
          </div>
        );
      default:
        return null;
    }
  };

  return (
    <div className="max-w-2xl mx-auto">
      <h1 className="text-2xl font-bold mb-6">論文アップロード</h1>

      <form onSubmit={handleSubmit} className="space-y-6">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            ユーザー選択
          </label>
          <select
            value={userId || ''}
            onChange={(e) => setUserId(Number(e.target.value))}
            className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            required
          >
            <option value="">ユーザーを選択...</option>
            {users.map((user) => (
              <option key={user.user_id} value={user.user_id}>
                {user.name} ({user.role})
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            論文タイトル
          </label>
          <input
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="論文のタイトルを入力"
            className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            required
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            対象学会フォーマット
          </label>
          <select
            value={conferenceRule}
            onChange={(e) => setConferenceRule(e.target.value)}
            className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          >
            {conferenceRules.map((rule) => (
              <option key={rule.rule_id} value={rule.rule_id}>
                {rule.name}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            ファイル選択
          </label>
          <div
            {...getRootProps()}
            className={`border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors ${
              isDragActive ? 'border-blue-500 bg-blue-50' : 'border-gray-300 hover:border-gray-400'
            }`}
          >
            <input {...getInputProps()} />
            {file ? (
              <div className="flex items-center justify-center">
                <FileText className="w-8 h-8 text-blue-500 mr-3" />
                <span className="text-gray-700">{file.name}</span>
              </div>
            ) : (
              <div>
                <Upload className="w-12 h-12 text-gray-400 mx-auto mb-4" />
                <p className="text-gray-600">
                  ファイルをドラッグ＆ドロップ、またはクリックして選択
                </p>
                <p className="text-sm text-gray-400 mt-2">
                  PDF または TeX ファイル
                </p>
              </div>
            )}
          </div>
        </div>

        {status !== 'idle' && (
          <div className="p-4 bg-gray-50 rounded-lg">
            {getStatusDisplay()}
          </div>
        )}

        <button
          type="submit"
          disabled={!file || !title || !userId || status === 'uploading' || status === 'processing'}
          className="w-full py-3 px-4 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors"
        >
          アップロードして分析開始
        </button>
      </form>

      {status === 'completed' && (
        <div className="mt-6 p-4 bg-green-50 border border-green-200 rounded-lg">
          <p className="text-green-800">
            分析が完了しました。
            <a href="/papers" className="underline ml-2">
              論文一覧で結果を確認
            </a>
          </p>
        </div>
      )}
    </div>
  );
}
