import Link from 'next/link';
import { needsPageMapping, questionMappingUrl, questionReviewUrl, type QuestionQueue } from '../../lib/review-pilot';
import { statusLabel } from '../../lib/presentation';

export function QuestionReviewQueue({ data, question }: { data: QuestionQueue; question: string }) {
  const missing = data.items.filter(needsPageMapping).length;
  return <>
    {data.items[0]&&<p><Link className="button primary" href={questionReviewUrl(data.items[0].id,question,data.items[0].mapping?.pages)}>Начать проверку группы →</Link></p>}
    {missing > 0 && <p className="notice">Для {missing} работ страницы вопроса пока не найдены. Можно начать проверку с оригинала и при необходимости отметить страницы.</p>}
    <div className="student-table-wrap"><table className="student-table">
      <thead><tr><th>СТУДЕНТ</th><th>СТРАНИЦЫ ВОПРОСА</th><th>ПРОВЕРКА</th><th><span className="rw-sr-only">Действия</span></th></tr></thead>
      <tbody>{data.items.map(item => {
        const needsMapping = needsPageMapping(item);
        const hasPages = !item.mapping?.stale && !!item.mapping?.pages.length;
        const unavailable = item.file_type === 'pdf' && item.page_count === 0;
        return <tr key={item.id}>
          <td>{item.student_name}</td>
          <td>{hasPages ? `${item.mapping!.pages.join(', ')}${item.mapping?.inferred?' · найдено распознаванием':item.mapping?.whole_work?' · вся работа':''}` : item.file_type !== 'pdf' ? 'Оригинал доступен для скачивания' : unavailable ? 'Страницы пока недоступны' : item.mapping?.stale ? 'Вопрос изменён — обновите разметку' : 'Страницы ещё не отмечены'}</td>
          <td>{statusLabel(item.review_status)}</td>
          <td><Link className="button" href={questionReviewUrl(item.id,question,hasPages?item.mapping?.pages:[])}>Проверить вопрос →</Link>{needsMapping&&<Link className="rw-text-button" href={questionMappingUrl(item.id,question)}>Уточнить страницы</Link>}</td>
        </tr>;
      })}</tbody>
    </table>{!data.items.length && <p className="student-empty">Работ пока нет.</p>}</div>
  </>;
}
