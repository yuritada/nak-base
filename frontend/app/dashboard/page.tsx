'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { FileText, Loader2, Plus } from 'lucide-react';
import { getPapers, type Paper } from '@/lib/api';

export default function DashboardPage() {
  const [papers, setPapers] = useState<Paper[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchPapers = async () => {
    try {
      const data = await getPapers();
      setPapers(data);
    } catch (e) {
      console.error('Failed to fetch papers:', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchPapers();
    // 3秒ごとにポーリング
    const interval = setInterval(fetchPapers, 3000);
    return () => clearInterval(interval);
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="w-8 h-8 animate-spin text-blue-500" />
      </div>
    );
  }

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold">論文一覧</h1>
        <Link
          href="/upload"
          className="flex items-center px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
        >
          <Plus className="w-5 h-5 mr-2" />
          アップロード
        </Link>
      </div>

      <div className="bg-white rounded-lg shadow-sm border overflow-hidden">
        {papers.length === 0 ? (
          <div className="px-6 py-12 text-center">
            <FileText className="w-12 h-12 text-gray-300 mx-auto mb-4" />
            <p className="text-gray-500 mb-4">まだ論文がありません</p>
            <Link
              href="/upload"
              className="text-blue-600 hover:underline"
            >
              最初の論文をアップロードする
            </Link>
          </div>
        ) : (
          <table className="w-full">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  タイトル
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  アップロード日時
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  ステータス
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {papers.map((paper) => (
                <PaperRow key={paper.id} paper={paper} />
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

function PaperRow({ paper }: { paper: Paper }) {
  const [status, setStatus] = useState<string>('pending');

  useEffect(() => {
    // 論文詳細を取得してステータスを確認
    const checkStatus = async () => {
      try {
        const res = await fetch(`http://localhost:8000/papers/${paper.id}`);
        if (res.ok) {
          const data = await res.json();
          if (data.tasks && data.tasks.length > 0) {
            setStatus(data.tasks[0].status);
          }
        }
      } catch (e) {
        console.error('Failed to fetch paper status:', e);
      }
    };
    checkStatus();
  }, [paper.id]);

  const isCompleted = status === 'completed';
  const isProcessing = status === 'processing' || status === 'pending';

  return (
    <tr className="hover:bg-gray-50">
      <td className="px-6 py-4 text-sm text-gray-900">
        {isCompleted ? (
          <Link
            href={`/papers/${paper.id}`}
            className="text-blue-600 hover:underline"
          >
            {paper.title}
          </Link>
        ) : (
          <span className="text-gray-500">{paper.title}</span>
        )}
      </td>
      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
        {new Date(paper.created_at).toLocaleString('ja-JP')}
      </td>
      <td className="px-6 py-4 whitespace-nowrap">
        <span
          className={`px-2 py-1 text-xs rounded-full ${
            status === 'completed'
              ? 'bg-green-100 text-green-800'
              : status === 'error'
              ? 'bg-red-100 text-red-800'
              : 'bg-yellow-100 text-yellow-800'
          }`}
        >
          {isProcessing && <Loader2 className="w-3 h-3 inline-block mr-1 animate-spin" />}
          {status === 'completed' ? '完了' : status === 'error' ? 'エラー' : '解析中'}
        </span>
      </td>
    </tr>
  );
}
