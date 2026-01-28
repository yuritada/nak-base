'use client';

import { useState, useEffect } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import { FileText, Loader2, ArrowLeft } from 'lucide-react';
import { getPaper, type PaperWithTasks, type Task } from '@/lib/api';

export default function PaperDetailPage() {
  const params = useParams();
  const router = useRouter();
  const paperId = Number(params.id);
  const [paper, setPaper] = useState<PaperWithTasks | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!paperId) return;

    getPaper(paperId)
      .then(setPaper)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [paperId]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="w-8 h-8 animate-spin text-blue-500" />
      </div>
    );
  }

  if (!paper) {
    return <div className="text-center py-12 text-gray-500">論文が見つかりません</div>;
  }

  const task = paper.tasks?.[0];

  return (
    <div>
      <div className="mb-6">
        <Link
          href="/dashboard"
          className="inline-flex items-center text-gray-500 hover:text-gray-700 mb-4"
        >
          <ArrowLeft className="w-4 h-4 mr-1" />
          一覧に戻る
        </Link>
        <h1 className="text-2xl font-bold mb-2">{paper.title}</h1>
        <p className="text-gray-500">
          アップロード日時: {new Date(paper.created_at).toLocaleString('ja-JP')}
        </p>
      </div>

      {task ? (
        <div className="bg-white rounded-lg shadow-sm border overflow-hidden">
          <div className="px-6 py-4 border-b flex items-center">
            <FileText className="w-5 h-5 text-blue-500 mr-3" />
            <span className="font-medium">AI分析結果</span>
            <span
              className={`ml-auto px-2 py-1 text-xs rounded-full ${
                task.status === 'completed'
                  ? 'bg-green-100 text-green-800'
                  : task.status === 'error'
                  ? 'bg-red-100 text-red-800'
                  : 'bg-yellow-100 text-yellow-800'
              }`}
            >
              {task.status === 'completed' ? '完了' : task.status === 'error' ? 'エラー' : '処理中'}
            </span>
          </div>

          <div className="p-6">
            {task.status === 'completed' && task.result_json ? (
              <div className="space-y-6">
                {/* 要約 */}
                {task.result_json.summary && (
                  <div>
                    <h3 className="font-medium text-gray-700 mb-2">要約</h3>
                    <div className="bg-gray-50 p-4 rounded-lg text-sm whitespace-pre-wrap">
                      {task.result_json.summary}
                    </div>
                  </div>
                )}

                {/* 誤字脱字 */}
                {task.result_json.typos && task.result_json.typos.length > 0 && (
                  <div>
                    <h3 className="font-medium text-gray-700 mb-2">検出された誤字脱字</h3>
                    <div className="bg-yellow-50 p-4 rounded-lg">
                      <ul className="list-disc list-inside text-sm space-y-1">
                        {task.result_json.typos.map((typo, i) => (
                          <li key={i}>{typo}</li>
                        ))}
                      </ul>
                    </div>
                  </div>
                )}

                {/* 改善提案 */}
                {task.result_json.suggestions && task.result_json.suggestions.length > 0 && (
                  <div>
                    <h3 className="font-medium text-gray-700 mb-2">改善提案</h3>
                    <div className="bg-blue-50 p-4 rounded-lg">
                      <ul className="list-disc list-inside text-sm space-y-1">
                        {task.result_json.suggestions.map((suggestion, i) => (
                          <li key={i}>{suggestion}</li>
                        ))}
                      </ul>
                    </div>
                  </div>
                )}
              </div>
            ) : task.status === 'error' ? (
              <div className="text-red-600">
                エラーが発生しました: {task.result_json?.error || '不明なエラー'}
              </div>
            ) : (
              <div className="py-8 text-center text-gray-500">
                <Loader2 className="w-6 h-6 animate-spin mx-auto mb-2" />
                分析中です...
              </div>
            )}
          </div>
        </div>
      ) : (
        <div className="bg-white rounded-lg shadow-sm border p-6 text-center text-gray-500">
          タスクが見つかりません
        </div>
      )}
    </div>
  );
}
