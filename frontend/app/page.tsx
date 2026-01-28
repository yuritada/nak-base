'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { demoLogin } from '@/lib/api';

export default function LoginPage() {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleDemoLogin = async () => {
    setLoading(true);
    setError(null);

    try {
      const { access_token } = await demoLogin();
      // Cookieに保存
      document.cookie = `token=${access_token}; path=/; max-age=86400`;
      // ダッシュボードへ遷移
      router.push('/dashboard');
    } catch (e) {
      setError('ログインに失敗しました');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-[60vh] flex flex-col items-center justify-center">
      <div className="text-center mb-8">
        <h1 className="text-4xl font-bold text-gray-900 mb-4">
          nak-base
        </h1>
        <p className="text-xl text-gray-600 mb-2">
          論文フィードバックシステム MVP
        </p>
        <p className="text-gray-500">
          PDFを投げたらAIが感想を返す
        </p>
      </div>

      <div className="bg-white p-8 rounded-lg shadow-sm border">
        <button
          onClick={handleDemoLogin}
          disabled={loading}
          className="w-full px-8 py-4 bg-blue-600 text-white text-lg font-medium rounded-lg hover:bg-blue-700 disabled:bg-blue-300 transition-colors"
        >
          {loading ? '接続中...' : 'デモを開始する'}
        </button>

        {error && (
          <p className="mt-4 text-red-600 text-center">{error}</p>
        )}
      </div>
    </div>
  );
}
