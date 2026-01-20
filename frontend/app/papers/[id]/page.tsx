'use client';

import { useState, useEffect } from 'react';
import { useParams } from 'next/navigation';
import { FileText, CheckCircle, AlertCircle, Loader2, ChevronDown, ChevronUp } from 'lucide-react';
import { getPaper, getFeedbackByVersion, type Feedback, type Version } from '@/lib/api';

interface PaperDetail {
  paper_id: number;
  title: string;
  target_conference: string | null;
  status: string;
  versions: Version[];
}

export default function PaperDetailPage() {
  const params = useParams();
  const paperId = Number(params.id);
  const [paper, setPaper] = useState<PaperDetail | null>(null);
  const [feedbacks, setFeedbacks] = useState<Record<number, Feedback[]>>({});
  const [loading, setLoading] = useState(true);
  const [expandedVersion, setExpandedVersion] = useState<number | null>(null);

  useEffect(() => {
    if (!paperId) return;

    getPaper(paperId)
      .then(async (data) => {
        setPaper(data);
        // Fetch feedbacks for each version
        const feedbackPromises = data.versions.map((v: Version) =>
          getFeedbackByVersion(v.version_id).then((fb) => ({ versionId: v.version_id, feedbacks: fb }))
        );
        const results = await Promise.all(feedbackPromises);
        const feedbackMap: Record<number, Feedback[]> = {};
        results.forEach((r) => {
          feedbackMap[r.versionId] = r.feedbacks;
        });
        setFeedbacks(feedbackMap);
        // Expand latest version
        if (data.versions.length > 0) {
          setExpandedVersion(data.versions[data.versions.length - 1].version_id);
        }
      })
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

  const renderScoreBar = (score: number, label: string, color: string) => (
    <div className="mb-3">
      <div className="flex justify-between text-sm mb-1">
        <span className="text-gray-600">{label}</span>
        <span className="font-medium">{score}/100</span>
      </div>
      <div className="w-full bg-gray-200 rounded-full h-2">
        <div
          className={`h-2 rounded-full ${color}`}
          style={{ width: `${score}%` }}
        />
      </div>
    </div>
  );

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold mb-2">{paper.title}</h1>
        <p className="text-gray-500">{paper.target_conference || '学会未指定'}</p>
      </div>

      <div className="space-y-4">
        {paper.versions
          .sort((a, b) => b.version_number - a.version_number)
          .map((version) => {
            const versionFeedbacks = feedbacks[version.version_id] || [];
            const feedback = versionFeedbacks[0];
            const isExpanded = expandedVersion === version.version_id;

            return (
              <div
                key={version.version_id}
                className="bg-white rounded-lg shadow-sm border overflow-hidden"
              >
                <button
                  onClick={() => setExpandedVersion(isExpanded ? null : version.version_id)}
                  className="w-full px-6 py-4 flex items-center justify-between hover:bg-gray-50 transition-colors"
                >
                  <div className="flex items-center">
                    <FileText className="w-5 h-5 text-blue-500 mr-3" />
                    <div className="text-left">
                      <span className="font-medium">Version {version.version_number}</span>
                      <span className="text-sm text-gray-500 ml-3">
                        {version.file_name}
                      </span>
                    </div>
                  </div>
                  <div className="flex items-center">
                    {feedback?.score_json && (
                      <span className="text-sm font-medium mr-4">
                        総合: {feedback.score_json.overall}/100
                      </span>
                    )}
                    {isExpanded ? (
                      <ChevronUp className="w-5 h-5 text-gray-400" />
                    ) : (
                      <ChevronDown className="w-5 h-5 text-gray-400" />
                    )}
                  </div>
                </button>

                {isExpanded && feedback && (
                  <div className="px-6 pb-6 border-t">
                    <div className="grid md:grid-cols-2 gap-6 mt-4">
                      <div>
                        <h3 className="font-medium mb-4">スコア</h3>
                        {feedback.score_json && (
                          <>
                            {renderScoreBar(feedback.score_json.overall, '総合', 'bg-blue-500')}
                            {renderScoreBar(feedback.score_json.format, '形式', 'bg-green-500')}
                            {renderScoreBar(feedback.score_json.logic, '論理', 'bg-purple-500')}
                            {renderScoreBar(feedback.score_json.novelty, '新規性', 'bg-orange-500')}
                            {feedback.score_json.improvement !== null && (
                              renderScoreBar(feedback.score_json.improvement, '改善度', 'bg-teal-500')
                            )}
                          </>
                        )}
                      </div>

                      <div>
                        <h3 className="font-medium mb-4">サマリー</h3>
                        <div className="bg-gray-50 p-4 rounded-lg text-sm whitespace-pre-wrap">
                          {feedback.overall_summary || 'サマリーはありません'}
                        </div>
                      </div>
                    </div>

                    {feedback.comments_json && (
                      <div className="mt-6">
                        <h3 className="font-medium mb-4">詳細フィードバック</h3>

                        {/* Linter Results */}
                        {feedback.comments_json.linter_result && (
                          <div className="mb-4">
                            <h4 className="text-sm font-medium text-gray-700 mb-2">形式チェック</h4>
                            <div className="bg-gray-50 p-4 rounded-lg text-sm">
                              {(feedback.comments_json.linter_result as { typos?: Array<{ original: string; suggested: string }> }).typos?.length ? (
                                <div className="mb-2">
                                  <span className="font-medium">誤字脱字:</span>
                                  <ul className="list-disc list-inside ml-2">
                                    {(feedback.comments_json.linter_result as { typos: Array<{ original: string; suggested: string }> }).typos.slice(0, 5).map((t, i) => (
                                      <li key={i}>{t.original} → {t.suggested}</li>
                                    ))}
                                  </ul>
                                </div>
                              ) : (
                                <p className="text-green-600">誤字脱字は検出されませんでした</p>
                              )}
                            </div>
                          </div>
                        )}

                        {/* Logic Results */}
                        {feedback.comments_json.logic_result && (
                          <div className="mb-4">
                            <h4 className="text-sm font-medium text-gray-700 mb-2">論理構造</h4>
                            <div className="bg-gray-50 p-4 rounded-lg text-sm">
                              {(feedback.comments_json.logic_result as { summary?: string }).summary || '分析結果なし'}
                            </div>
                          </div>
                        )}

                        {/* Diff Results */}
                        {feedback.comments_json.diff_result && (feedback.comments_json.diff_result as { improvement_score?: number }).improvement_score !== null && (
                          <div className="mb-4">
                            <h4 className="text-sm font-medium text-gray-700 mb-2">前回からの改善</h4>
                            <div className="bg-gray-50 p-4 rounded-lg text-sm">
                              {(feedback.comments_json.diff_result as { summary?: string }).summary || '比較データなし'}
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )}

                {isExpanded && !feedback && (
                  <div className="px-6 pb-6 border-t">
                    <div className="py-8 text-center text-gray-500">
                      <Loader2 className="w-6 h-6 animate-spin mx-auto mb-2" />
                      分析中またはフィードバックがありません
                    </div>
                  </div>
                )}
              </div>
            );
          })}
      </div>
    </div>
  );
}
