'use client';

import { useState, useRef } from 'react';
import { useRouter } from 'next/navigation';
import { Upload, FileText, CheckCircle, AlertCircle, Loader2 } from 'lucide-react';
import { uploadPaper, getTask } from '@/lib/api';

type UploadStatus = 'idle' | 'uploading' | 'processing' | 'completed' | 'error';

export default function UploadPage() {
  const router = useRouter();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState('');
  const [status, setStatus] = useState<UploadStatus>('idle');
  const [error, setError] = useState<string | null>(null);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      const f = e.target.files[0];
      setFile(f);
      if (!title) {
        setTitle(f.name.replace(/\.pdf$/i, ''));
      }
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file || !title) return;

    setStatus('uploading');
    setError(null);

    try {
      const result = await uploadPaper(title, file);
      setStatus('processing');

      // ポーリングで完了を待つ
      const pollInterval = setInterval(async () => {
        try {
          const task = await getTask(result.task_id);
          if (task.status === 'completed') {
            clearInterval(pollInterval);
            setStatus('completed');
          } else if (task.status === 'error') {
            clearInterval(pollInterval);
            setStatus('error');
            setError(task.result_json?.error || 'エラーが発生しました');
          }
        } catch (err) {
          console.error('Poll error:', err);
        }
      }, 3000);

    } catch (err) {
      setStatus('error');
      setError(err instanceof Error ? err.message : 'アップロードに失敗しました');
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
            AI分析中...
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
    <div className="max-w-lg mx-auto">
      <h1 className="text-2xl font-bold mb-6">論文アップロード</h1>

      <form onSubmit={handleSubmit} className="space-y-6 bg-white p-6 rounded-lg shadow-sm border">
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
            PDFファイル
          </label>
          <input
            type="file"
            ref={fileInputRef}
            accept=".pdf"
            onChange={handleFileChange}
            className="hidden"
          />
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            className="w-full border-2 border-dashed rounded-lg p-8 text-center cursor-pointer hover:border-gray-400 transition-colors"
          >
            {file ? (
              <div className="flex items-center justify-center">
                <FileText className="w-8 h-8 text-blue-500 mr-3" />
                <span className="text-gray-700">{file.name}</span>
              </div>
            ) : (
              <div>
                <Upload className="w-12 h-12 text-gray-400 mx-auto mb-4" />
                <p className="text-gray-600">クリックしてPDFファイルを選択</p>
              </div>
            )}
          </button>
        </div>

        {status !== 'idle' && (
          <div className="p-4 bg-gray-50 rounded-lg">
            {getStatusDisplay()}
          </div>
        )}

        <button
          type="submit"
          disabled={!file || !title || status === 'uploading' || status === 'processing'}
          className="w-full py-3 px-4 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors"
        >
          アップロードして分析開始
        </button>
      </form>

      {status === 'completed' && (
        <div className="mt-6 p-4 bg-green-50 border border-green-200 rounded-lg">
          <p className="text-green-800">
            分析が完了しました。
            <button
              onClick={() => router.push('/dashboard')}
              className="underline ml-2"
            >
              論文一覧で結果を確認
            </button>
          </p>
        </div>
      )}
    </div>
  );
}
