'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { FileText, Clock, CheckCircle, AlertCircle, Loader2 } from 'lucide-react';
import { getPapers, type Paper } from '@/lib/api';

const statusConfig = {
  Draft: { icon: FileText, color: 'text-gray-500', bg: 'bg-gray-100' },
  Processing: { icon: Loader2, color: 'text-yellow-500', bg: 'bg-yellow-100' },
  Completed: { icon: CheckCircle, color: 'text-green-500', bg: 'bg-green-100' },
  Error: { icon: AlertCircle, color: 'text-red-500', bg: 'bg-red-100' },
};

export default function PapersPage() {
  const [papers, setPapers] = useState<Paper[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getPapers()
      .then(setPapers)
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

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold">論文一覧</h1>
        <Link
          href="/upload"
          className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
        >
          新規アップロード
        </Link>
      </div>

      {papers.length === 0 ? (
        <div className="text-center py-12 bg-white rounded-lg shadow-sm border">
          <FileText className="w-12 h-12 text-gray-400 mx-auto mb-4" />
          <p className="text-gray-600">まだ論文がアップロードされていません</p>
          <Link href="/upload" className="text-blue-600 hover:underline mt-2 inline-block">
            最初の論文をアップロード
          </Link>
        </div>
      ) : (
        <div className="space-y-4">
          {papers.map((paper) => {
            const config = statusConfig[paper.status];
            const StatusIcon = config.icon;

            return (
              <Link
                key={paper.paper_id}
                href={`/papers/${paper.paper_id}`}
                className="block bg-white p-6 rounded-lg shadow-sm border hover:shadow-md transition-shadow"
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <h2 className="text-lg font-semibold text-gray-900 mb-1">
                      {paper.title}
                    </h2>
                    <p className="text-sm text-gray-500">
                      {paper.target_conference || '学会未指定'}
                    </p>
                  </div>
                  <div className={`flex items-center px-3 py-1 rounded-full ${config.bg}`}>
                    <StatusIcon className={`w-4 h-4 mr-1 ${config.color} ${paper.status === 'Processing' ? 'animate-spin' : ''}`} />
                    <span className={`text-sm ${config.color}`}>{paper.status}</span>
                  </div>
                </div>
                <div className="mt-4 flex items-center text-sm text-gray-500">
                  <Clock className="w-4 h-4 mr-1" />
                  {new Date(paper.created_at).toLocaleDateString('ja-JP')}
                </div>
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}
