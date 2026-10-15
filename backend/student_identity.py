"""Display identity for already-authorized academic routes; legacy anonymous work stays anonymous."""
from account_models import Account


def student_display_name(db, student_id, saved_name=''):
    account = db.get(Account, student_id)
    if account and account.display_name.strip():
        return account.display_name.strip()
    name = (saved_name or '').strip()
    if name and name != student_id:
        return name
    return 'Студент · ' + student_id[:8]
