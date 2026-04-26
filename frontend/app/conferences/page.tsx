'use client';

import { useState, useEffect } from 'react';
import { Plus, Edit2, Trash2, Save, X, BookOpen } from 'lucide-react';
import {
  getConferences,
  createConference,
  updateConference,
  deleteConference,
} from '@/lib/api';
import type { ConferenceRule } from '@/types';

type EditMode = 'create' | 'edit' | null;

export default function ConferencesPage() {
  const [conferences, setConferences] = useState<ConferenceRule[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [editMode, setEditMode] = useState<EditMode>(null);
  const [editingId, setEditingId] = useState<string | null>(null);

  // Form state
  const [formRuleId, setFormRuleId] = useState('');
  const [formName, setFormName] = useState('');
  const [formStyleGuide, setFormStyleGuide] = useState('');
  const [formFormatRules, setFormFormatRules] = useState('');
  const [formError, setFormError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  // Load conferences
  useEffect(() => {
    loadConferences();
  }, []);

  const loadConferences = async () => {
    try {
      setLoading(true);
      const data = await getConferences();
      setConferences(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load conferences');
    } finally {
      setLoading(false);
    }
  };

  const resetForm = () => {
    setFormRuleId('');
    setFormName('');
    setFormStyleGuide('');
    setFormFormatRules('');
    setFormError(null);
    setEditMode(null);
    setEditingId(null);
  };

  const startCreate = () => {
    resetForm();
    setEditMode('create');
  };

  const startEdit = (conf: ConferenceRule) => {
    setFormRuleId(conf.rule_id);
    setFormName(conf.name);
    setFormStyleGuide(conf.style_guide || '');
    setFormFormatRules(
      conf.format_rules ? JSON.stringify(conf.format_rules, null, 2) : ''
    );
    setFormError(null);
    setEditMode('edit');
    setEditingId(conf.rule_id);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);
    setSaving(true);

    try {
      // Parse format_rules JSON
      let formatRules: Record<string, unknown> | undefined;
      if (formFormatRules.trim()) {
        try {
          formatRules = JSON.parse(formFormatRules);
        } catch {
          setFormError('フォーマット規定のJSONが不正です');
          setSaving(false);
          return;
        }
      }

      if (editMode === 'create') {
        if (!formRuleId.trim()) {
          setFormError('ルールIDは必須です');
          setSaving(false);
          return;
        }
        await createConference({
          rule_id: formRuleId.trim(),
          name: formName.trim(),
          style_guide: formStyleGuide.trim() || undefined,
          format_rules: formatRules,
        });
      } else if (editMode === 'edit' && editingId) {
        await updateConference(editingId, {
          name: formName.trim(),
          style_guide: formStyleGuide.trim() || undefined,
          format_rules: formatRules,
        });
      }

      await loadConferences();
      resetForm();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : 'Failed to save');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (ruleId: string) => {
    if (!confirm(`学会「${ruleId}」を削除しますか？`)) return;

    try {
      await deleteConference(ruleId);
      await loadConferences();
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to delete');
    }
  };

  if (loading) {
    return (
      <div className="text-center py-12">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto"></div>
        <p className="mt-4 text-gray-600">読み込み中...</p>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold">学会ルール管理</h1>
        {!editMode && (
          <button
            onClick={startCreate}
            className="flex items-center px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
          >
            <Plus className="w-5 h-5 mr-2" />
            新規作成
          </button>
        )}
      </div>

      {error && (
        <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg text-red-700">
          {error}
        </div>
      )}

      {/* Create/Edit Form */}
      {editMode && (
        <div className="mb-8 bg-white p-6 rounded-lg shadow-sm border">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-lg font-semibold">
              {editMode === 'create' ? '新規学会ルール作成' : '学会ルール編集'}
            </h2>
            <button
              onClick={resetForm}
              className="text-gray-500 hover:text-gray-700"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            {editMode === 'create' && (
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  ルールID（英数字、ハイフン）
                </label>
                <input
                  type="text"
                  value={formRuleId}
                  onChange={(e) => setFormRuleId(e.target.value)}
                  placeholder="例: JSAI-2025"
                  pattern="[a-zA-Z0-9\-_]+"
                  className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  required
                />
                <p className="text-xs text-gray-500 mt-1">
                  一度作成すると変更できません
                </p>
              </div>
            )}

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                学会名
              </label>
              <input
                type="text"
                value={formName}
                onChange={(e) => setFormName(e.target.value)}
                placeholder="例: 人工知能学会全国大会 2025"
                className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                required
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                フォーマット規定（JSON形式、任意）
              </label>
              <textarea
                value={formFormatRules}
                onChange={(e) => setFormFormatRules(e.target.value)}
                placeholder={`{
  "max_pages": 8,
  "font_size": 10,
  "margin_cm": 2.5,
  "columns": 2
}`}
                rows={5}
                className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent font-mono text-sm"
              />
              <p className="text-xs text-gray-500 mt-1">
                ページ数、フォントサイズなどの数値規定
              </p>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                スタイルガイド（任意）
              </label>
              <textarea
                value={formStyleGuide}
                onChange={(e) => setFormStyleGuide(e.target.value)}
                placeholder={`## 論文の構成
1. 概要（Abstract）: 200語以内で研究の目的、手法、結果を記述
2. はじめに（Introduction）: 研究背景と目的
3. 関連研究（Related Work）: 先行研究のレビュー
4. 提案手法（Proposed Method）
5. 実験（Experiments）
6. 結論（Conclusion）

## 注意事項
- 参考文献はIEEE形式で記載
- 図表には必ずキャプションを付ける`}
                rows={10}
                className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
              <p className="text-xs text-gray-500 mt-1">
                論文構成、参考文献形式などの文章ガイド（Markdownで記述可）
              </p>
            </div>

            {formError && (
              <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
                {formError}
              </div>
            )}

            <div className="flex justify-end space-x-3">
              <button
                type="button"
                onClick={resetForm}
                className="px-4 py-2 border rounded-lg hover:bg-gray-50 transition-colors"
              >
                キャンセル
              </button>
              <button
                type="submit"
                disabled={saving}
                className="flex items-center px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-400 transition-colors"
              >
                <Save className="w-4 h-4 mr-2" />
                {saving ? '保存中...' : '保存'}
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Conference List */}
      {conferences.length === 0 ? (
        <div className="text-center py-12 bg-white rounded-lg border">
          <BookOpen className="w-12 h-12 text-gray-400 mx-auto mb-4" />
          <p className="text-gray-600">学会ルールが登録されていません</p>
          <p className="text-gray-500 text-sm mt-2">
            「新規作成」ボタンから学会ルールを追加してください
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          {conferences.map((conf) => (
            <div
              key={conf.rule_id}
              className="bg-white p-6 rounded-lg shadow-sm border"
            >
              <div className="flex justify-between items-start">
                <div className="flex-1">
                  <div className="flex items-center space-x-3">
                    <span className="px-2 py-1 bg-blue-100 text-blue-800 text-xs font-mono rounded">
                      {conf.rule_id}
                    </span>
                    <h3 className="text-lg font-semibold">{conf.name}</h3>
                  </div>

                  {conf.format_rules && Object.keys(conf.format_rules).length > 0 && (
                    <div className="mt-3">
                      <p className="text-sm text-gray-500 mb-1">フォーマット規定:</p>
                      <div className="flex flex-wrap gap-2">
                        {Object.entries(conf.format_rules).map(([key, value]) => (
                          <span
                            key={key}
                            className="px-2 py-1 bg-gray-100 text-gray-700 text-xs rounded"
                          >
                            {key}: {String(value)}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {conf.style_guide && (
                    <div className="mt-3">
                      <p className="text-sm text-gray-500 mb-1">スタイルガイド:</p>
                      <p className="text-sm text-gray-700 whitespace-pre-wrap line-clamp-3">
                        {conf.style_guide}
                      </p>
                    </div>
                  )}
                </div>

                <div className="flex space-x-2 ml-4">
                  <button
                    onClick={() => startEdit(conf)}
                    className="p-2 text-gray-500 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-colors"
                    title="編集"
                  >
                    <Edit2 className="w-5 h-5" />
                  </button>
                  <button
                    onClick={() => handleDelete(conf.rule_id)}
                    className="p-2 text-gray-500 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                    title="削除"
                  >
                    <Trash2 className="w-5 h-5" />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
