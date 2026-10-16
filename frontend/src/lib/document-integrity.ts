export type IntegritySummary = { id?: string; status: string; detector_status?: string; signal_count?: number | null; units_analyzed?: number; units_total?: number; model?: string; authorship_probability?: null };
export type IntegrityReport = IntegritySummary & { report?: { status: string; detector_status: string; model: string; chunks_analyzed: number; chunks_total: number; units_analyzed: number; units_total: number; features: { concept: string; unit: number; quote: string }[]; style_signals: { unit: number; quote: string; observation: string; alternative_explanation: string }[] } };
export const INTEGRITY_NOTE = 'AI detector может ошибаться. Не используйте его как единственное основание оценки или вывода об авторстве. Сверяйте фрагменты с оригиналом и обсуждайте работу со студентом.';
export function detectorLabel(value?: IntegritySummary | null) {
  if (!value) return 'Не запускался';
  if (['queued', 'extracting', 'interpreting'].includes(value.status)) return 'Анализируется…';
  if (value.status === 'awaiting_budget') return 'Ожидает бюджета';
  if (value.status === 'failed') return 'Анализ не завершён';
  if (value.status === 'stale') return 'Нужно обновить';
  if (value.status === 'input_limit') return 'Превышен объём';
  if (value.detector_status === 'not_applicable') return 'Не применим к этой работе';
  if (value.detector_status === 'insufficient_text' || value.status === 'no_readable_text') return 'Недостаточно текста';
  if (value.status === 'completed' && value.detector_status === 'advisory') return value.signal_count ? 'Есть сигналы для проверки' : 'Неопределённо';
  return 'Не запускался';
}
