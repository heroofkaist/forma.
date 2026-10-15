"""Student-facing progress contains no operational diagnostics."""
def processing_message(status):
    if status == 'awaiting_budget':
        return 'Автоматический анализ временно недоступен. Работа сохранена и доступна преподавателю для проверки.'
    return 'Не удалось завершить автоматический анализ. Работа сохранена; преподаватель может проверить её вручную.'
