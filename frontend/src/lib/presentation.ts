/** Product language only: operational diagnostics belong in teacher-only panels. */
const labels: Record<string, string> = {
  analysis_not_scheduled: 'Работа отправлена · ожидает проверки', not_enrolled: 'Не записан', none: 'Не записан', pending: 'Ожидает подтверждения', processing: 'Обрабатывается', ready_for_review: 'К проверке',
  needs_attention: 'Нужно внимание', failed: 'Требуется внимание', approved: 'Подтверждено',
  submitted: 'Работа отправлена', published: 'Опубликовано', ready: 'Готово к проверке',
  draft: 'Черновик', confirmed: 'Подтверждено', active: 'Активен', archived: 'В архиве',
  closed: 'Закрыто', open: 'Открыто', not_started: 'Не отправлено', graded: 'Оценка опубликована',
  overdue: 'Срок истёк', queued: 'В очереди на обработку', extracting: 'Подготовка документа',
  interpreting: 'Анализируется', needs_review: 'Ожидает проверки преподавателя',
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
