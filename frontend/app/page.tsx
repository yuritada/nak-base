'use client';

import Link from 'next/link';
import { FileText, Upload, BarChart3, Users } from 'lucide-react';

export default function Home() {
  return (
    <div className="space-y-8">
      <div className="text-center py-12">
        <h1 className="text-4xl font-bold text-gray-900 mb-4">
          nak-base
        </h1>
        <p className="text-xl text-gray-600 mb-2">
          研究室の「集合知」で、最高の一本を。
        </p>
        <p className="text-gray-500">
          AIによる多層的フィードバックで、論文の質を向上させます
        </p>
      </div>

      <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-6">
        <Link href="/upload" className="block">
          <div className="bg-white p-6 rounded-lg shadow-sm border hover:shadow-md transition-shadow">
            <Upload className="w-12 h-12 text-blue-500 mb-4" />
            <h2 className="text-lg font-semibold mb-2">論文アップロード</h2>
            <p className="text-gray-600 text-sm">
              PDF/TeXファイルをアップロードしてAI分析を開始
            </p>
          </div>
        </Link>

        <Link href="/papers" className="block">
          <div className="bg-white p-6 rounded-lg shadow-sm border hover:shadow-md transition-shadow">
            <FileText className="w-12 h-12 text-green-500 mb-4" />
            <h2 className="text-lg font-semibold mb-2">論文一覧</h2>
            <p className="text-gray-600 text-sm">
              アップロードした論文とフィードバックを確認
            </p>
          </div>
        </Link>

        <Link href="/dashboard" className="block">
          <div className="bg-white p-6 rounded-lg shadow-sm border hover:shadow-md transition-shadow">
            <BarChart3 className="w-12 h-12 text-purple-500 mb-4" />
            <h2 className="text-lg font-semibold mb-2">ダッシュボード</h2>
            <p className="text-gray-600 text-sm">
              全体の進捗状況とスコアを一覧表示
            </p>
          </div>
        </Link>

        <Link href="/users" className="block">
          <div className="bg-white p-6 rounded-lg shadow-sm border hover:shadow-md transition-shadow">
            <Users className="w-12 h-12 text-orange-500 mb-4" />
            <h2 className="text-lg font-semibold mb-2">ユーザー管理</h2>
            <p className="text-gray-600 text-sm">
              学生・教授のアカウント管理
            </p>
          </div>
        </Link>
      </div>

      <div className="bg-white p-6 rounded-lg shadow-sm border">
        <h2 className="text-xl font-semibold mb-4">システムの特徴</h2>
        <div className="grid md:grid-cols-3 gap-6">
          <div>
            <h3 className="font-medium text-blue-600 mb-2">形式チェック</h3>
            <p className="text-gray-600 text-sm">
              誤字脱字、学会フォーマット違反を自動検出
            </p>
          </div>
          <div>
            <h3 className="font-medium text-green-600 mb-2">論理分析</h3>
            <p className="text-gray-600 text-sm">
              AbstractとConclusionの整合性、章立ての論理をチェック
            </p>
          </div>
          <div>
            <h3 className="font-medium text-purple-600 mb-2">RAG検索</h3>
            <p className="text-gray-600 text-sm">
              過去の優秀論文と比較し、改善点を提案
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
