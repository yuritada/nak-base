'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import Link from 'next/link';
import { FileText, Loader2, Plus, RefreshCw, WifiOff, GitBranch } from 'lucide-react';
import { getPapers } from '@/lib/api';
import { useSSE } from '@/hooks';
import type { PaperListItem, TaskStatusEnum, SSENotificationEvent } from '@/types';
import { getTaskStatusDisplay, getPaperStatusDisplay } from '@/types';

interface PaperWithTaskInfo extends PaperListItem {
  taskStatus?: TaskStatusEnum;
  taskPhase?: string;
  taskId?: number;
}

export default function DashboardPage() {
  const [papers, setPapers] = useState<PaperWithTaskInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const papersRef = useRef<PaperWithTaskInfo[]>([]);

  const handleSSEMessage = useCallback((event: SSENotificationEvent) => {
    setPapers((prev) =>
      prev.map((paper) => {
        if (paper.taskId === event.task_id) {
          return {
            ...paper,
            taskStatus: event.status,
            taskPhase: event.phase,
          };
        }
        return paper;
      })
    );
  }, []);

  const { isConnected, error: sseError } = useSSE({
    onMessage: handleSSEMessage,
  });

  const fetchPapers = useCallback(async () => {
    try {
      const data = await getPapers();
      const papersWithInfo: PaperWithTaskInfo[] = data.map((paper) => ({
        ...paper,
        taskStatus: undefined,
        taskPhase: undefined,
      }));
      setPapers(papersWithInfo);
      papersRef.current = papersWithInfo;
    } catch (e) {
      console.error('Failed to fetch papers:', e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchPapers();
  }, [fetchPapers]);

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
        <div className="flex items-center gap-4">
          <h1 className="text-2xl font-bold">論文一覧</h1>
          {!isConnected && (
            <span className="flex items-center text-sm text-yellow-600">
              <WifiOff className="w-4 h-4 mr-1" />
              オフライン
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={fetchPapers}
            className="flex items-center px-3 py-2 text-gray-600 hover:text-gray-900 rounded-lg hover:bg-gray-100"
            title="更新"
          >
            <RefreshCw className="w-5 h-5" />
          </button>
          <Link
            href="/upload"
            className="flex items-center px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
          >
            <Plus className="w-5 h-5 mr-2" />
            アップロード
          </Link>
        </div>
      </div>

      {sseError && (
        <div className="mb-4 p-3 bg-yellow-50 border border-yellow-200 rounded-lg text-yellow-800 text-sm">
          {sseError}
        </div>
      )}

      <div className="bg-white rounded-lg shadow-sm border overflow-hidden">
        {papers.length === 0 ? (
          <div className="px-6 py-12 text-center">
            <FileText className="w-12 h-12 text-gray-300 mx-auto mb-4" />
            <p className="text-gray-500 mb-4">まだ論文がありません</p>
            <Link href="/upload" className="text-blue-600 hover:underline">
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
                  バージョン
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
                <PaperRow key={paper.paper_id} paper={paper} />
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

function PaperRow({ paper }: { paper: PaperWithTaskInfo }) {
  const statusDisplay = paper.taskStatus
    ? getTaskStatusDisplay(paper.taskStatus, paper.taskPhase)
    : getPaperStatusDisplay(paper.status);

  const isCompleted = paper.status === 'COMPLETED';
  const isProcessing = statusDisplay.isLoading;

  const colorClasses = {
    green: 'bg-green-100 text-green-800',
    yellow: 'bg-yellow-100 text-yellow-800',
    red: 'bg-red-100 text-red-800',
    blue: 'bg-blue-100 text-blue-800',
    gray: 'bg-gray-100 text-gray-800',
  };

  const hasResubmissions = paper.child_paper_count > 0;

  return (
    <tr className="hover:bg-gray-50">
      <td className="px-6 py-4 text-sm text-gray-900">
        {isCompleted ? (
          <Link
            href={`/papers/${paper.paper_id}`}
            className="text-blue-600 hover:underline"
          >
            {paper.title}
          </Link>
        ) : (
          <span className="text-gray-500">{paper.title}</span>
        )}
      </td>
      <td className="px-6 py-4 whitespace-nowrap text-sm">
        <div className="flex items-center gap-1">
          {hasResubmissions ? (
            <>
              <GitBranch className="w-4 h-4 text-purple-500" />
              <span className="text-purple-600 font-medium">
                v{paper.total_versions}
              </span>
              <span className="text-gray-400 text-xs">
                ({paper.child_paper_count}回再提出)
              </span>
            </>
          ) : (
            <span className="text-gray-500">v1</span>
          )}
        </div>
      </td>
      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
        {paper.created_at ? new Date(paper.created_at).toLocaleString('ja-JP') : '-'}
      </td>
      <td className="px-6 py-4 whitespace-nowrap">
        <span className={`px-2 py-1 text-xs rounded-full ${colorClasses[statusDisplay.color]}`}>
          {isProcessing && <Loader2 className="w-3 h-3 inline-block mr-1 animate-spin" />}
          {statusDisplay.label}
        </span>
      </td>
    </tr>
  );
}
