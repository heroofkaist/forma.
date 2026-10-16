/** Product language only: operational diagnostics belong in teacher-only panels. */
const labels: Record<string, string> = {
  analysis_not_scheduled: 'Работа отправлена · ожидает проверки', not_enrolled: 'Не записан', none: 'Не записан', pending: 'Ожидает подтверждения', processing: 'Обрабатывается', ready_for_review: 'К проверке',
  needs_attention: 'Нужно внимание', failed: 'Требуется внимание', approved: 'Подтверждено',
  submitted: 'Работа отправлена', published: 'Опубликовано', ready: 'Готово к проверке',
  draft: 'Черновик', confirmed: 'Подтверждено', active: 'Активен', archived: 'В архиве',
  closed: 'Закрыто', open: 'Открыто', not_started: 'Не отправлено', graded: 'Оценка опубликована',
  overdue: 'Срок истёк', queued: 'В очереди на обработку', extracting: 'Подготовка документа',
  interpreting: 'Анализируется', awaiting_source: 'Читаем документ перед оцениванием', needs_review: 'Ожидает проверки преподавателя',
  completed: 'Проверка завершена', awaiting_budget: 'Автоматический анализ приостановлен',
  not_scheduled: 'Ожидает проверки преподавателя', unreviewed: 'Не проверено', reviewed: 'Проверено',
  suspended: 'Доступ приостановлен', removed: 'Доступ закрыт', rejected: 'Отклонено',
  follow_up: 'Нужна дополнительная проверка', needs_investigation: 'Нужно внимание', analyzing: 'Анализируется',
};
export function statusLabel(status?: string) { return labels[status ?? ''] ?? 'Статус уточняется'; }
export function studentProcessingMessage(status: string, published = false) {
  if (published) return 'Результат опубликован';
  if (status === 'awaiting_budget') return 'Автоматический анализ временно недоступен. Работа сохранена и доступна преподавателю для проверки.';
  if (status === 'failed') return 'Работа сохранена. Преподаватель может проверить её вручную.';
  if (status === 'completed' || status === 'needs_review') return 'AI-анализ завершён. Работа ожидает проверки преподавателя.';
  return statusLabel(status);
}
export function teacherProcessingMessage(status: string, hasError = false) {
  if (hasError || status === 'failed') return 'AI-анализ не выполнен. Можно проверить вручную.';
  if (status === 'awaiting_budget') return 'AI-анализ приостановлен. Можно проверить вручную.';
  if (status === 'completed' || status === 'needs_review') return 'AI-анализ готов. Доступна проверка преподавателем.';
  return statusLabel(status);
}
export const assignmentTypes: Record<string, string> = { problem_set:'Задачи', essay:'Эссе', lab_report:'Лабораторная работа', presentation:'Презентация', research_report:'Исследовательская работа', programming:'Программирование', general:'Документ' };
export function submissionAvailability(assignment: { available_at?: string | null; due_at?: string | null; status: string; allow_resubmission: boolean; latest_submission?: unknown }, now = Date.now()) {
  if (assignment.available_at && Date.parse(assignment.available_at) > now) return 'Задание ещё не открыто.';
  if (assignment.status === 'closed' || (assignment.due_at && Date.parse(assignment.due_at) < now)) return 'Срок сдачи завершён. Отправка закрыта.';
  if (assignment.latest_submission && !assignment.allow_resubmission) return 'Работа принята. Повторная отправка не разрешена преподавателем.';
  return '';
}
export function requestError(status: number, detail?: unknown) {
  const known: Record<string, string> = {
    'Local file comparison is busy. Retry after the current comparison finishes.': 'Сейчас выполняется другое сравнение файлов. Уже проверенные файлы сохранены; продолжите чуть позже.',
    'Course archive changed. Reload before continuing the file scan.': 'В архиве появились новые работы или изменились материалы задания. Обновите состояние и запустите актуальное сравнение.',
    'An assignment baseline is unavailable. Restore the task or template before comparing.': 'Файл условия или шаблон недоступен. Восстановите материал задания, чтобы исключить его из сравнения.',
    'Assignment baselines exceed the local comparison limit.': 'Материалы задания превышают 15 МБ. Сократите их размер перед сравнением.',
    'Teaching guide changed. Reload before saving.': 'Правила уже изменены в другой вкладке. Скопируйте свои правки и перезагрузите настройки.',
    'Only confirmed current reviews can be reference examples.': 'Один из примеров не соответствует действующим критериям. Уберите его из списка и сохраните правила.',
    'Requirements, teaching guide or source changed. Reassess the whole work.': 'После этой оценки изменились условия, правила ИИ или распознавание. Запустите оценивание всей работы — прежние баллы нельзя использовать с новыми требованиями.',
    'Saved assessment cannot be reused. Reassess the whole work.': 'Прежнюю оценку нельзя безопасно дополнить. Запустите оценивание всей работы.',
    'Revision must refer to published feedback.': 'Опубликованный отзыв обновился. Обновите страницу и выберите замечания заново.',
    'Check the revision response.': 'Проверьте выбранные замечания и пояснение к пересдаче.',
    'Select criteria from the published review.': 'Выберите критерии из опубликованного отзыва.',
    'Paid allowance is not available; reconcile billing or use manual review.': 'Доступный лимит AI-проверки пока не позволяет продолжить. Можно выставить баллы вручную.',
    'Daily document processing limit (20 jobs) reached.': 'Сегодня уже запущено 20 этапов AI-анализа. Сохранённые результаты доступны; новые запросы можно отправить завтра.',
    'Maximum three analysis versions per submission per day.': 'Сегодня уже запрошены 3 версии этого анализа. Используйте сохранённый результат или повторите завтра.',
    'Another document task is active; wait for it to finish.': 'Документ уже обрабатывается. Дождитесь завершения текущего анализа.',
    'Partial document coverage cannot justify assessment scores. Review manually or analyze the complete bounded document.': 'Распознаны не все страницы. ИИ не выставит баллы по неполному документу: проверьте покрытие в помощи ИИ или оцените работу вручную.',
    'Source observations do not match the current original document. Reanalyze before assessment.': 'Файл изменился после распознавания. Повторите распознавание в помощи ИИ, затем запустите оценивание.',
    'Clarify criterion descriptions before requesting AI scores.': 'Уточните критерии задания, чтобы ИИ понимал, за что выставлять баллы.',
    'Local comparison requires 2–40 students with submissions.': 'Для локального сравнения нужны работы от 2 до 40 разных студентов.',
    'A submission has no extracted structure. Prepare the original before comparing.': 'У одной из работ нет сохранённой структуры документа. Откройте работу и проверьте извлечение перед сравнением.',
    'An original document is unavailable.': 'Один из оригиналов недоступен. Проверьте наличие файла работы.',
    'Local comparison is limited to 60 MB of originals.': 'Суммарный объём оригиналов для локального сравнения не должен превышать 60 МБ.',
    'An original document changed. Reload the submission before comparing.': 'Оригинал изменился. Проверьте документ и обновите данные перед сравнением.',
    'Submissions changed during comparison. Reload and run again.': 'Во время сравнения появились новые работы или изменились условия. Обновите задание и повторите сравнение.',
    'Local comparison failed or exceeded its limits. No result was recorded.': 'Локальный анализ не завершился. Проверьте лимиты: 40 работ, 60 МБ, 200 страниц/изображений. Новый результат не сохранён.',

    'Decision card rubric has changed.': 'Версия критерия изменилась. Уберите связь с карточкой и проверьте решение заново.',
    'Confirm this teacher decision before saving a card.': 'Сначала подтвердите и сохраните решение по этому критерию.',
    'Page mapping changed; reload it before saving.': 'Другой проверяющий изменил страницы. Перезагрузите разметку перед сохранением.',
    'Evidence page is unavailable in this original PDF.': 'Такой страницы нет в оригинале PDF. Проверьте номер страницы.',
    'Select unique existing PDF pages.': 'Выберите существующие страницы PDF без повторов.',
    'Upload request ID was already used for a different file.': 'Эта попытка уже сохранена с другим файлом. Выберите файл заново перед новой отправкой.',
    'Enrollment code is invalid or unavailable.': 'Код не найден или запись на курс закрыта. Проверьте код у преподавателя.',
    'Course enrollment capacity has been reached.': 'На курсе пока нет свободных мест. Обратитесь к преподавателю.',
    'Student account required for enrollment.': 'Для записи на курс войдите в учётную запись студента.',
    'Guardian registration is not configured.': 'Подтверждение родителем пока не настроено. Обратитесь в своё учебное учреждение.',
    'Guardian approval is required or has expired.': 'Нужно действующее согласие родителя. Вернитесь к проверке возраста.',
    'Guardian link is invalid or expired.': 'Ссылка недействительна или срок её действия истёк. Попросите ребёнка отправить новое письмо.',
    'Guardian request has already been decided.': 'По этому запросу уже принято решение. Обновите страницу.',
    'Use a separate child email address after guardian approval.': 'Для учётной записи ребёнка нужен отдельный email, отличный от адреса родителя.',
    'Wait before requesting another guardian email.': 'Подождите минуту перед повторной отправкой письма.',
    'Guardian attestation and consent are required.': 'Подтвердите, что вы совершеннолетний законный представитель и даёте согласие.',

    'Complete the age check before registration.': 'Пройдите проверку возраста снова, чтобы продолжить регистрацию.',
    'Resubmission is not allowed.': 'Работа уже отправлена. Повторная отправка не разрешена.',
    'The submission deadline has passed.': 'Срок сдачи завершён. Отправка закрыта.',
    'Assignment is not available yet.': 'Задание ещё не открыто.',
    'Invalid email or password.': 'Проверьте адрес электронной почты и пароль.',
  };
  if (typeof detail === 'string' && known[detail]) return known[detail];
  // Never expose arbitrary provider responses or infrastructure errors in product flows.
  return ({401:'Войдите в учётную запись, чтобы продолжить.',403:'У вас нет доступа к этому действию.',404:'Не удалось найти запрошенную страницу или файл.',409:'Действие сейчас недоступно. Обновите страницу и проверьте условия задания.',413:'Файл слишком большой. Максимальный размер — 30 МБ.',415:'Этот формат не поддерживается. Проверьте допустимые форматы.',422:'Проверьте заполненные поля и выбранный файл.',429:'Слишком много запросов. Попробуйте немного позже.'} as Record<number,string>)[status] ?? 'Не удалось выполнить запрос. Попробуйте ещё раз позже.';
}

export function termLabel(term?: string) { return ({Fall:"Осень",Spring:"Весна",Summer:"Лето",Winter:"Зима"} as Record<string,string>)[term ?? ""] ?? term ?? ""; }
