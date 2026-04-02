import logging
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import login, logout, authenticate
from django.core.exceptions import ValidationError
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.views.decorators.cache import cache_control

from .models import Account, AvatarChangeRequest

logger = logging.getLogger(__name__)
audit_logger = logging.getLogger("audit")


def sign_up(request):
    if request.method == 'POST':
        first_name = request.POST.get('firstname', '').strip()
        last_name = request.POST.get('lastname', '').strip()
        submitted_identity = request.POST.get('username', '').strip()
        email = request.POST.get('email', '').strip() or submitted_identity
        username = submitted_identity or email
        password = request.POST.get('password', '')
        password2 = request.POST.get('password2', '')
        if password == password2:
            if Account.objects.filter(email=email).exists():
                audit_logger.warning(
                    "signup_rejected_duplicate_email email=%s ip=%s",
                    email,
                    request.META.get("REMOTE_ADDR", ""),
                )
                messages.error(request, "Uživatel s tímto e-mailem již existuje.")
                return render(request, 'accounts/signup.html')
            if Account.objects.filter(username=username).exists():
                audit_logger.warning(
                    "signup_rejected_duplicate_username username=%s ip=%s",
                    username,
                    request.META.get("REMOTE_ADDR", ""),
                )
                messages.error(request, "Uživatel s tímto uživatelským jménem již existuje.")
                return render(request, 'accounts/signup.html')
            user = Account.objects.create_user(
                first_name=first_name,
                last_name=last_name,
                username=username,
                email=email,
                password=password,
            )
            user.is_active = True
            user.save()
            login(request, user)
            audit_logger.info(
                "signup_success user_id=%s username=%s email=%s ip=%s",
                user.id,
                user.username,
                user.email,
                request.META.get("REMOTE_ADDR", ""),
            )
            return redirect('news:homepage')
        else:
            # TODO: Dodělat chybové hlášení
            audit_logger.warning(
                "signup_rejected_password_mismatch username=%s email=%s ip=%s",
                username,
                email,
                request.META.get("REMOTE_ADDR", ""),
            )
            messages.error(request, "Heslo není shodné s heslem pro kontrolu. Zadejte registrační údaje znovu")
            return render(request, 'accounts/signup.html')
    else:
        data = {}
        return render(request, 'accounts/signup.html', data)


def sign_in(request):
    if request.method == "POST":
        username = request.POST.get('username', '')
        password = request.POST.get('password', '')
        
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            
            remember_me = request.POST.get('remember-me')
            
            if remember_me:
                request.session.set_expiry(1209600)  # 14 dní (v sekundách)
            else:
                request.session.set_expiry(0)  # Vyprší po zavření prohlížeče

            audit_logger.info(
                "signin_success user_id=%s username=%s remember_me=%s ip=%s",
                user.id,
                user.username,
                bool(remember_me),
                request.META.get("REMOTE_ADDR", ""),
            )
            return redirect('news:homepage')  # Přesměrování po úspěšném přihlášení
        else:
            audit_logger.warning(
                "signin_failed username=%s ip=%s",
                username,
                request.META.get("REMOTE_ADDR", ""),
            )
            messages.error(request, "Neplatné uživatelské jméno nebo heslo.")

    return render(request, 'accounts/signin.html')


def sign_out(request):
    if request.user.is_authenticated:
        audit_logger.info(
            "signout user_id=%s username=%s ip=%s",
            request.user.id,
            request.user.username,
            request.META.get("REMOTE_ADDR", ""),
        )
    logout(request)
    return redirect('news:homepage')


@cache_control(no_cache=True, must_revalidate=True, no_store=True)
@staff_member_required
def avatar_moderation_dashboard(request):
    expired_count = AvatarChangeRequest.expire_stale_requests()
    if expired_count:
        messages.info(
            request,
            f"{expired_count} žádostí o avatar automaticky expirovalo kvůli stáří.",
        )

    if request.method == "POST":
        action = request.POST.get("action")
        request_id = request.POST.get("request_id")
        avatar_request = get_object_or_404(
            AvatarChangeRequest.objects.select_related("target_account", "target_rider", "uploaded_by"),
            pk=request_id,
            status=AvatarChangeRequest.STATUS_PENDING,
        )
        try:
            result = avatar_request.review(action, request.user)
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
        except Exception:
            logger.exception(
                "Avatar dashboard action failed for request pk=%s by user=%s action=%s",
                avatar_request.pk,
                getattr(request.user, "pk", None),
                action,
            )
            messages.error(request, "Žádost se nepodařilo zpracovat. Zkontroluj zdrojový obrázek a zkus to znovu.")
        else:
            if result == AvatarChangeRequest.STATUS_APPROVED:
                messages.success(request, f"Avatar pro {avatar_request.target_label} byl schválen.")
            elif result == AvatarChangeRequest.STATUS_REJECTED:
                messages.success(request, f"Avatar pro {avatar_request.target_label} byl zamítnut.")
            elif result == AvatarChangeRequest.STATUS_EXPIRED:
                messages.success(request, f"Žádost pro {avatar_request.target_label} byla expirována.")
        return redirect("accounts:avatar-moderation")

    pending_requests = list(
        AvatarChangeRequest.objects.filter(status=AvatarChangeRequest.STATUS_PENDING)
        .select_related("uploaded_by", "target_account", "target_rider")
        .order_by("created")
    )
    recent_requests = list(
        AvatarChangeRequest.objects.exclude(status=AvatarChangeRequest.STATUS_PENDING)
        .select_related("uploaded_by", "target_account", "target_rider", "reviewed_by")
        .order_by("-reviewed_at", "-created")[:12]
    )

    context = {
        "pending_requests": pending_requests,
        "recent_requests": recent_requests,
        "pending_count": len(pending_requests),
        "approved_count": AvatarChangeRequest.objects.filter(status=AvatarChangeRequest.STATUS_APPROVED).count(),
        "rejected_count": AvatarChangeRequest.objects.filter(status=AvatarChangeRequest.STATUS_REJECTED).count(),
        "expired_count": AvatarChangeRequest.objects.filter(status=AvatarChangeRequest.STATUS_EXPIRED).count(),
        "expiration_days": AvatarChangeRequest.expiration_days(),
    }
    return render(request, "accounts/avatar-moderation-dashboard.html", context)
