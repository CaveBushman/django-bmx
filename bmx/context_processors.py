def navbar_context(request):
    return {
        "user": request.user,
        # "notifications": request.user.notifications.all() if request.user.is_authenticated else [],
    }