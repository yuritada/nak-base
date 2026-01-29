'use client';

import { useState, useEffect } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { FileText, Loader2, ArrowLeft, AlertTriangle } from 'lucide-react';
import { getPaper, getFeedback } from '@/lib/api';
import type { PaperDetail, Feedback } from '@/types';
import { getPaperStatusDisplay } from '@/types';

export default function PaperDetailPage() {
  const params = useParams();
  const paperId = Number(params.id);

  const [paper, setPaper] = useState<PaperDetail | null>(null);
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!paperId) return;

    const fetchData = async () => {
      try {
        const paperData = await getPaper(paperId);
        setPaper(paperData);

        if (paperData.versions && paperData.versions.length > 0) {
          const latestVersion = paperData.versions[paperData.versions.length - 1];
          const feedbackData = await getFeedback(latestVersion.version_id);
          setFeedback(feedbackData);
        }
      } catch (e) {
        console.error('Failed to fetch paper:', e);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
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

  const statusDisplay = getPaperStatusDisplay(paper.status);

  const colorClasses = {
    green: 'bg-green-100 text-green-800',
    yellow: 'bg-yellow-100 text-yellow-800',
    red: 'bg-red-100 text-red-800',
    blue: 'bg-blue-100 text-blue-800',
    gray: 'bg-gray-100 text-gray-800',
  };

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
        <div className="flex items-center gap-3 mb-2">
          <h1 className="text-2xl font-bold">{paper.title}</h1>
          <span className={`px-2 py-1 text-xs rounded-full ${colorClasses[statusDisplay.color]}`}>
            {statusDisplay.isLoading && (
              <Loader2 className="w-3 h-3 inline-block mr-1 animate-spin" />
            )}
            {statusDisplay.label}
          </span>
        </div>
        <p className="text-gray-500">
          アップロード日時:{' '}
          {paper.created_at ? new Date(paper.created_at).toLocaleString('ja-JP') : '-'}
        </p>
        {paper.versions && paper.versions.length > 1 && (
          <p className="text-gray-500 text-sm mt-1">バージョン: {paper.versions.length}件</p>
        )}
      </div>

      <div className="bg-white rounded-lg shadow-sm border overflow-hidden">
        <div className="px-6 py-4 border-b flex items-center">
          <FileText className="w-5 h-5 text-blue-500 mr-3" />
          <span className="font-medium">AI分析結果</span>
        </div>

        <div className="p-6">
          {paper.status === 'COMPLETED' && feedback ? (
            <div className="space-y-6">
              {feedback.overall_summary && (
                <div>
                  <h3 className="font-medium text-gray-700 mb-2">総合評価</h3>
                  <div className="bg-gray-50 p-4 rounded-lg text-sm whitespace-pre-wrap">
                    {feedback.overall_summary}
                  </div>
                </div>
              )}

              {feedback.score_json && Object.keys(feedback.score_json).length > 0 && (
                <div>
                  <h3 className="font-medium text-gray-700 mb-2">評価スコア</h3>
                  <div className="bg-blue-50 p-4 rounded-lg">
                    <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                      {Object.entries(feedback.score_json).map(([key, value]) => (
                        <div key={key} className="text-center">
                          <div className="text-2xl font-bold text-blue-600">
                            {typeof value === 'number' ? value : String(value)}
                          </div>
                          <div className="text-xs text-gray-600">{key}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              )}

              {feedback.comments_json && Object.keys(feedback.comments_json).length > 0 && (
                <div>
                  <h3 className="font-medium text-gray-700 mb-2">詳細コメント</h3>
                  <div className="space-y-3">
                    {Object.entries(feedback.comments_json).map(([section, comments]) => (
                      <div key={section} className="bg-yellow-50 p-4 rounded-lg">
                        <h4 className="font-medium text-yellow-800 mb-2">{section}</h4>
                        {Array.isArray(comments) ? (
                          <ul className="list-disc list-inside text-sm space-y-1 text-yellow-900">
                            {(comments as string[]).map((comment, i) => (
                              <li key={i}>{comment}</li>
                            ))}
                          </ul>
                        ) : (
                          <p className="text-sm text-yellow-900">{String(comments)}</p>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {!feedback.overall_summary &&
                (!feedback.score_json || Object.keys(feedback.score_json).length === 0) &&
                (!feedback.comments_json || Object.keys(feedback.comments_json).length === 0) && (
                  <div className="py-8 text-center text-gray-500">
                    フィードバックの詳細がありません
                  </div>
                )}
            </div>
          ) : paper.status === 'ERROR' || paper.status === 'FAILED' ? (
            <div className="flex items-start text-red-600">
              <AlertTriangle className="w-5 h-5 mr-2 flex-shrink-0 mt-0.5" />
              <div>
                <p className="font-medium">分析中にエラーが発生しました</p>
                <p className="text-sm text-red-500 mt-1">再度アップロードをお試しください</p>
              </div>
            </div>
          ) : paper.status === 'PROCESSING' ? (
            <div className="py-8 text-center text-gray-500">
              <Loader2 className="w-6 h-6 animate-spin mx-auto mb-2" />
              分析中です...
            </div>
          ) : (
            <div className="py-8 text-center text-gray-500">フィードバックがありません</div>
          )}
        </div>
      </div>
    </div>
  );
}
