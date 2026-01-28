import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'nak-base - 論文フィードバックシステム MVP',
  description: 'PDFを投げたらAIが感想を返す',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="ja">
      <body className="bg-gray-50 min-h-screen">
        <nav className="bg-white shadow-sm border-b">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div className="flex justify-between h-16">
              <div className="flex items-center">
                <a href="/" className="text-xl font-bold text-blue-600">
                  nak-base
                </a>
                <span className="ml-2 text-sm text-gray-500">
                  MVP
                </span>
              </div>
              <div className="flex items-center space-x-4">
                <a href="/dashboard" className="text-gray-600 hover:text-gray-900">
                  論文一覧
                </a>
                <a href="/upload" className="text-gray-600 hover:text-gray-900">
                  アップロード
                </a>
              </div>
            </div>
          </div>
        </nav>
        <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          {children}
        </main>
      </body>
    </html>
  )
}
