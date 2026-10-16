/** Display helpers never turn unavailable or invalid data into a real zero. */
export function scoreLabel(value: unknown, maximum = 10000): string {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= maximum
    ? new Intl.NumberFormat('ru-RU', {maximumFractionDigits: 2}).format(value) : '—';
}
export function dateLabel(value?: string | null, empty = 'Дата не указана') {
  const date = value ? new Date(value) : null;
  return date && Number.isFinite(date.getTime()) ? date.toLocaleString('ru-RU') : empty;
}
export function countLabel(value: number, one: string, few: string, many: string) {
  const form = new Intl.PluralRules('ru-RU').select(value);
  return `${scoreLabel(value, Number.MAX_SAFE_INTEGER)} ${form === 'one' ? one : form === 'few' ? few : many}`;
}
export function aiText(value: unknown, fallback = ''): string {
  if (typeof value !== 'string') return fallback;
  const text = value.replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/g, '').trim();
  return !text || /^(null|undefined|none|nan|[-+]?infinity|\[object Object\]|n\/a)$/i.test(text) || /^(\{|\[\{|```json)/.test(text) ? fallback : text;
}
