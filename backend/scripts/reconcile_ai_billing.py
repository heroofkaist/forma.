"""Explicit operator command: billing metadata GETs only, never inference.

Uses only the intended environment, never loads .env. No arbitrary cost overrides
or automatic refunds: a reservation without a generation ID remains held.
"""
import argparse
import json
import os


def reconcile(client, charge_id):
    import ai_budget
    from budget_models import AIRequestCharge
    from services.ai_providers.openrouter import MODEL
    with ai_budget.SessionLocal() as db:
        row = db.get(AIRequestCharge, charge_id)
        if not row or row.provider != 'openrouter' or not row.generation_id:
            raise ValueError('A stored OpenRouter generation ID is required; keep the unknown reservation held.')
        generation = row.generation_id
    response = client.get('/generation', params={'id': generation})
    response.raise_for_status()
    data = response.json()['data']
    if data.get('id') != generation or data.get('model') != MODEL or data.get('is_byok') is not False:
        raise ValueError('Billing metadata identity does not match the reservation.')
    ai_budget.money(data.get('total_cost'))  # Missing/invalid is never a refund.
    from datetime import datetime
    billed = datetime.fromisoformat(data['created_at'].replace('Z', '+00:00'))
    return ai_budget.record(charge_id, cost=data['total_cost'], generation_id=generation,
        billed_month=ai_budget.month(billed), tokens={'prompt_tokens': data.get('tokens_prompt'),
                                                   'completion_tokens': data.get('tokens_completion')})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reservation')
    parser.add_argument('--resume-provider', action='store_true')
    args = parser.parse_args()
    if not args.reservation and not args.resume_provider:
        parser.error('Choose --reservation UUID and/or --resume-provider.')
    if not os.getenv('FORMA_DATABASE_URL'):
        parser.error('Set the intended FORMA_DATABASE_URL explicitly; no default database is permitted.')
    from services.ai_providers.openrouter import BASE, secret, verify_key
    import ai_budget
    import httpx
    try:
        with httpx.Client(base_url=BASE, headers={'Authorization': 'Bearer ' + secret()},
                          timeout=15, trust_env=False, follow_redirects=False) as client:
            if args.reservation:
                print(json.dumps(reconcile(client, args.reservation)))
            if args.resume_provider:
                ai_budget.resume_provider_after_verified_credit(verify_key(client))
                print('Provider credit verified; HTTP 402 circuit cleared. Jobs still require authorized resume.')
    except Exception as error:
        # Do not expose HTTP URLs, SDK bodies, SQL parameters or credentials.
        raise SystemExit('Billing reconciliation failed (' + type(error).__name__ + '); no inference was attempted.') from None


if __name__ == '__main__':
    main()
