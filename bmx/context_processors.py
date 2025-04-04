def navbar_context(request):
    from accounts.models import Account

    if request.user.is_authenticated:
        try:
            account = Account.objects.get(id=request.user.id)
            return {'user_credit': account.credit}
        except Account.DoesNotExist:
            return {'user_credit': 0}
    return {}