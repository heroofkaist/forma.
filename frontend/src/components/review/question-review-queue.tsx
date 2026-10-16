import Link from 'next/link';
import { needsPageMapping, questionMappingUrl, questionReviewUrl, type QuestionQueue } from '../../lib/review-pilot';
import { statusLabel } from '../../lib/presentation';

export function QuestionReviewQueue({ data, question }: { data: QuestionQueue; question: string }) {
  const missing = data.items.filter(needsPageMapping).length;
  return <>
    {missing > 0 && <p className="notice">Требуют разметки: {missing}. Нажмите «Разметить страницы» — откроется нужный вопрос и выбор страниц оригинала.</p>}
    <div className="student-table-wrap"><table className="student-table">
      <thead><tr><th>СТУДЕНТ</th><th>СТРАНИЦЫ ВОПРОСА</th><th>ПРОВЕРКА</th><th><span className="rw-sr-only">Действия</span></th></tr></thead>
      <tbody>{data.items.map(item => {
        const needsMapping = needsPageMapping(item);
        const hasPages = !item.mapping?.stale && !!item.mapping?.pages.length;
        const unavailable = item.file_type === 'pdf' && item.page_count === 0;
        return <tr key={item.id}>
          <td>{item.student_name}</td>
          <td>{hasPages ? item.mapping!.pages.join(', ') : item.file_type !== 'pdf' ? 'Оригинал доступен для скачивания' : unavailable ? 'Страницы пока недоступны' : item.mapping?.stale ? 'Вопрос изменён — обновите разметку' : 'Страницы ещё не отмечены'}</td>
          <td>{statusLabel(item.review_status)}</td>
          <td>{needsMapping ? <Link className="button" href={questionMappingUrl(item.id, question)} aria-label={`Разметить страницы — ${item.student_name}`}>Разметить страницы →</Link> : <Link href={questionReviewUrl(item.id, question, hasPages ? item.mapping?.pages : [])}>{unavailable ? 'Открыть работу →' : 'Проверить вопрос →'}</Link>}</td>
        </tr>;
      })}</tbody>
    </table>{!data.items.length && <p className="student-empty">Работ пока нет.</p>}</div>
  </>;
}
