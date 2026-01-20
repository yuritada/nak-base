'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { Users, FileText, Clock, CheckCircle, Loader2 } from 'lucide-react';
import { getProfessorDashboard, type DashboardData } from '@/lib/api';

export default function DashboardPage() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getProfessorDashboard()
      .then(setData)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="w-8 h-8 animate-spin text-blue-500" />
      </div>
    );
  }

  if (!data) {
    return <div className="text-center py-12 text-gray-500">データを取得できませんでした</div>;
  }

  const getScoreColor = (score: number | null | undefined) => {
    if (score === null || score === undefined) return 'bg-gray-200';
    if (score >= 80) return 'bg-green-500';
    if (score >= 60) return 'bg-yellow-500';
    return 'bg-red-500';
  };

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">教授ダッシュボード</h1>

      {/* Stats Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
        <div className="bg-white p-6 rounded-lg shadow-sm border">
          <div className="flex items-center">
            <Users className="w-8 h-8 text-blue-500 mr-3" />
            <div>
              <p className="text-2xl font-bold">{data.total_students}</p>
              <p className="text-sm text-gray-500">学生数</p>
            </div>
          </div>
        </div>

        <div className="bg-white p-6 rounded-lg shadow-sm border">
          <div className="flex items-center">
            <FileText className="w-8 h-8 text-green-500 mr-3" />
            <div>
              <p className="text-2xl font-bold">{data.total_papers}</p>
              <p className="text-sm text-gray-500">総論文数</p>
            </div>
          </div>
        </div>

        <div className="bg-white p-6 rounded-lg shadow-sm border">
          <div className="flex items-center">
            <Clock className="w-8 h-8 text-yellow-500 mr-3" />
            <div>
              <p className="text-2xl font-bold">{data.papers_in_progress}</p>
              <p className="text-sm text-gray-500">分析中</p>
            </div>
          </div>
        </div>

        <div className="bg-white p-6 rounded-lg shadow-sm border">
          <div className="flex items-center">
            <CheckCircle className="w-8 h-8 text-green-500 mr-3" />
            <div>
              <p className="text-2xl font-bold">{data.papers_completed}</p>
              <p className="text-sm text-gray-500">完了</p>
            </div>
          </div>
        </div>
      </div>

      {/* Student Papers Table */}
      <div className="bg-white rounded-lg shadow-sm border overflow-hidden">
        <div className="px-6 py-4 border-b">
          <h2 className="text-lg font-semibold">学生論文一覧</h2>
        </div>

        {data.student_papers.length === 0 ? (
          <div className="px-6 py-8 text-center text-gray-500">
            まだ論文がアップロードされていません
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    学生名
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    論文タイトル
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Ver
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    ステータス
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    スコア
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                {data.student_papers.map((sp, idx) => (
                  <tr key={idx} className="hover:bg-gray-50">
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                      {sp.user_name}
                    </td>
                    <td className="px-6 py-4 text-sm text-gray-900">
                      <Link
                        href={`/papers/${sp.paper_id}`}
                        className="text-blue-600 hover:underline"
                      >
                        {sp.paper_title}
                      </Link>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                      v{sp.latest_version}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <span
                        className={`px-2 py-1 text-xs rounded-full ${
                          sp.status === 'Completed'
                            ? 'bg-green-100 text-green-800'
                            : sp.status === 'Processing'
                            ? 'bg-yellow-100 text-yellow-800'
                            : sp.status === 'Error'
                            ? 'bg-red-100 text-red-800'
                            : 'bg-gray-100 text-gray-800'
                        }`}
                      >
                        {sp.status}
                      </span>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      {sp.latest_score ? (
                        <div className="flex items-center">
                          <div
                            className={`w-3 h-3 rounded-full mr-2 ${getScoreColor(sp.latest_score.overall)}`}
                          />
                          <span className="text-sm font-medium">
                            {sp.latest_score.overall}
                          </span>
                        </div>
                      ) : (
                        <span className="text-gray-400">-</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
