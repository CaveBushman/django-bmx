import logging
from datetime import timedelta
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.forms import PasswordResetForm
from django.contrib.auth.tokens import default_token_generator
from django.contrib.sites.shortcuts import get_current_site
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.shortcuts import render, redirect, get_object_or_404
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.contrib import messages
from django.db.models import Count, Q
from django.db.models.functions import Lower
from django.views.decorators.cache import cache_control
from django.utils import timezone
from django.utils.translation import gettext as _

from .models import Account, AccountActivationAuditLog, AvatarChangeRequest, normalize_account_email
from club.models import Club
from bmx.form_protection import (
    build_security_context,
    clear_flow_attempts,
    increment_flow_attempts,
    protect_public_flow,
)

logger = logging.getLogger(__name__)
audit_logger = logging.getLogger("audit")
ACTIVATION_TOKEN_MAX_AGE = timedelta(days=settings.ACCOUNT_PENDING_ACTIVATION_MAX_AGE_DAYS)
FLOW_TEMPLATES = {
    "signup": "accounts/signup.html",
    "signin": "accounts/signin.html",
    "password_reset": "registration/password_reset_form.html",
    "activation_resend": "accounts/resend_activation.html",
}

def _render_flow_template(request, flow, status=200, extra_context=None):
    context = build_security_context(flow, request)
    if extra_context:
        context.update(extra_context)
    return render(request, FLOW_TEMPLATES[flow], context, status=status)


def _apply_flow_security_or_render(request, flow, *, extra_context=None):
    result = protect_public_flow(flow, request)
    if result is None:
        return None

    audit_logger.warning(
        "%s_rejected_%s ip=%s",
        flow,
        result["reason"],
        request.META.get("REMOTE_ADDR", ""),
    )
    messages.error(request, result["message"])
    return _render_flow_template(request, flow, status=result["status"], extra_context=extra_context)


def create_activation_audit_log(*, user, action, request=None, source="system", note=""):
    actor = getattr(request, "user", None)
    if actor is not None and not getattr(actor, "is_authenticated", False):
        actor = None
    AccountActivationAuditLog.objects.create(
        account=user,
        actor=actor,
        action=action,
        source=source,
        email_snapshot=user.email if user else "",
        note=note,
    )


def send_activation_email(request, user, *, action=AccountActivationAuditLog.Action.SENT, source="signup"):
    current_site = get_current_site(request)
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    activation_path = reverse("accounts:activate", kwargs={"uidb64": uid, "token": token})
    context = {
        "user": user,
        "domain": current_site.domain,
        "site_name": current_site.name or current_site.domain,
        "protocol": "https" if request.is_secure() else "http",
        "activation_path": activation_path,
    }
    subject = render_to_string("accounts/account_activation_subject.txt", context).strip()
    body = render_to_string("accounts/account_activation_email.txt", context)
    send_mail(subject, body, None, [user.email])
    create_activation_audit_log(user=user, action=action, request=request, source=source)


def activation_sent(request):
    return render(
        request,
        "accounts/account_activation_sent.html",
        {"pending_activation_email": request.session.get("pending_activation_email", "")},
    )


def sign_up(request):
    if request.method == 'POST':
        blocked_response = _apply_flow_security_or_render(request, "signup")
        if blocked_response is not None:
            return blocked_response

        first_name = request.POST.get('firstname', '').strip()
        last_name = request.POST.get('lastname', '').strip()
        submitted_identity = request.POST.get('username', '').strip()
        email = normalize_account_email(request.POST.get('email', '').strip() or submitted_identity)
        username = normalize_account_email(submitted_identity or email)
        password = request.POST.get('password', '')
        password2 = request.POST.get('password2', '')
        if password == password2:
            existing_user = Account.objects.filter(email__iexact=email).order_by("-date_joined").first()
            if existing_user:
                audit_logger.warning(
                    "signup_rejected_duplicate_email email=%s ip=%s",
                    email,
                    request.META.get("REMOTE_ADDR", ""),
                )
                if not existing_user.is_active:
                    request.session["pending_activation_email"] = existing_user.email
                    messages.info(
                        request,
                        _("Na tento e-mail už čeká nedokončená registrace. Pošlete si nový aktivační odkaz."),
                    )
                    return redirect(f"{reverse('accounts:resend_activation')}?email={existing_user.email}")
                messages.error(request, _("Uživatel s tímto e-mailem již existuje."))
                return _render_flow_template(request, "signup")
            if Account.objects.filter(username=username).exists():
                audit_logger.warning(
                    "signup_rejected_duplicate_username username=%s ip=%s",
                    username,
                    request.META.get("REMOTE_ADDR", ""),
                )
                messages.error(request, _("Uživatel s tímto uživatelským jménem již existuje."))
                return _render_flow_template(request, "signup")
            user = Account.objects.create_user(
                first_name=first_name,
                last_name=last_name,
                username=username,
                email=email,
                password=password,
            )
            user.is_active = False
            user.save(update_fields=["is_active"])
            clear_flow_attempts("signup", request)
            send_activation_email(
                request,
                user,
                action=AccountActivationAuditLog.Action.SENT,
                source="signup",
            )
            request.session["pending_activation_email"] = user.email
            audit_logger.info(
                "signup_success_pending_activation user_id=%s username=%s email=%s ip=%s",
                user.id,
                user.username,
                user.email,
                request.META.get("REMOTE_ADDR", ""),
            )
            return redirect('accounts:activation_sent')
        else:
            audit_logger.warning(
                "signup_rejected_password_mismatch username=%s email=%s ip=%s",
                username,
                email,
                request.META.get("REMOTE_ADDR", ""),
            )
            messages.error(request, _("Heslo není shodné s heslem pro kontrolu. Zadejte registrační údaje znovu"))
            return _render_flow_template(request, "signup")
    else:
        return _render_flow_template(request, "signup")


def sign_in(request):
    if request.method == "POST":
        blocked_response = _apply_flow_security_or_render(request, "signin")
        if blocked_response is not None:
            return blocked_response

        username = normalize_account_email(request.POST.get('username', ''))
        password = request.POST.get('password', '')

        matched_users = list(Account.objects.filter(email__iexact=username).only("id", "email"))
        if len(matched_users) > 1:
            audit_logger.warning(
                "signin_rejected_ambiguous_email email=%s matches=%s ip=%s",
                username,
                len(matched_users),
                request.META.get("REMOTE_ADDR", ""),
            )
            messages.error(request, _("Pro tento e-mail existuje více historických účtů. Kontaktujte administrátora."))
            return _render_flow_template(request, "signin")

        auth_identity = matched_users[0].email if matched_users else username
        matched_user = Account.objects.filter(email__iexact=auth_identity).only("id", "email", "is_active", "password").first()
        if matched_user and not matched_user.is_active and matched_user.check_password(password):
            increment_flow_attempts("signin", request)
            audit_logger.warning(
                "signin_rejected_inactive_account user_id=%s ip=%s",
                matched_user.id,
                request.META.get("REMOTE_ADDR", ""),
            )
            messages.error(
                request,
                _("Účet ještě není aktivovaný. Otevřete aktivační e-mail a potvrďte registraci. Pokud zprávu nevidíte, zkontrolujte i spam."),
            )
            return _render_flow_template(request, "signin")

        user = authenticate(request, username=auth_identity, password=password)
        if user is not None:
            login(request, user)
            clear_flow_attempts("signin", request)
            
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
            increment_flow_attempts("signin", request)
            audit_logger.warning(
                "signin_failed username=%s ip=%s",
                auth_identity,
                request.META.get("REMOTE_ADDR", ""),
            )
            messages.error(request, _("Neplatné uživatelské jméno nebo heslo."))

    return _render_flow_template(request, "signin")


def activate_account(request, uidb64, token):
    try:
        user_id = force_str(urlsafe_base64_decode(uidb64))
        user = Account.objects.get(pk=user_id)
    except (TypeError, ValueError, OverflowError, Account.DoesNotExist):
        user = None

    if user is None:
        messages.error(request, _("Aktivační odkaz je neplatný."))
        return redirect("accounts:signup")

    if not default_token_generator.check_token(user, token):
        messages.error(request, _("Aktivační odkaz je neplatný nebo expiroval."))
        return redirect("accounts:signup")

    joined_at = user.date_joined or timezone.now()
    if timezone.now() - joined_at > ACTIVATION_TOKEN_MAX_AGE:
        messages.error(request, _("Aktivační odkaz expiroval. Zaregistrujte se prosím znovu."))
        return redirect("accounts:signup")

    if not user.is_active:
        user.is_active = True
        user.save(update_fields=["is_active"])
        create_activation_audit_log(
            user=user,
            action=AccountActivationAuditLog.Action.ACTIVATED,
            request=request,
            source="activation_link",
        )

    audit_logger.info(
        "account_activated user_id=%s email=%s ip=%s",
        user.id,
        user.email,
        request.META.get("REMOTE_ADDR", ""),
    )
    request.session.pop("pending_activation_email", None)
    messages.success(request, _("Účet byl úspěšně aktivován. Teď se můžete přihlásit svým e-mailem a heslem."))
    return redirect("accounts:login")


def password_reset_request(request):
    if request.method == "POST":
        form = PasswordResetForm(request.POST)
        blocked_response = _apply_flow_security_or_render(request, "password_reset", extra_context={"form": form})
        if blocked_response is not None:
            return blocked_response

        if form.is_valid():
            form.save(
                request=request,
                use_https=request.is_secure(),
                from_email=None,
                email_template_name="registration/password_reset_email.html",
                subject_template_name="registration/password_reset_subject.txt",
            )
            clear_flow_attempts("password_reset", request)
            audit_logger.info(
                "password_reset_requested email=%s ip=%s",
                request.POST.get("email", "").strip().lower(),
                request.META.get("REMOTE_ADDR", ""),
            )
            return redirect("accounts:password_reset_done")

        increment_flow_attempts("password_reset", request)
    else:
        form = PasswordResetForm()

    return _render_flow_template(request, "password_reset", extra_context={"form": form})


def resend_activation_email(request):
    email = (request.POST.get("email") if request.method == "POST" else request.GET.get("email", "")) or request.session.get("pending_activation_email", "")
    email = normalize_account_email(email)

    if request.method == "POST":
        blocked_response = _apply_flow_security_or_render(
            request,
            "activation_resend",
            extra_context={"email": email},
        )
        if blocked_response is not None:
            return blocked_response

        user = Account.objects.filter(email__iexact=email, is_active=False).order_by("-date_joined").first()
        if user and timezone.now() - (user.date_joined or timezone.now()) <= ACTIVATION_TOKEN_MAX_AGE:
            send_activation_email(
                request,
                user,
                action=AccountActivationAuditLog.Action.RESENT,
                source="resend_form",
            )
            request.session["pending_activation_email"] = user.email
            audit_logger.info(
                "activation_resent user_id=%s email=%s ip=%s",
                user.id,
                user.email,
                request.META.get("REMOTE_ADDR", ""),
            )

        clear_flow_attempts("activation_resend", request)
        messages.success(
            request,
            _("Pokud pro tento e-mail existuje čekající registrace, poslali jsme nový aktivační odkaz."),
        )
        return redirect("accounts:activation_sent")

    return _render_flow_template(request, "activation_resend", extra_context={"email": email})


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
def ops_dashboard(request):
    from event.models import CreditTransaction, Entry, EntryForeign, Event, FinanceAuditLog, Result
    from ranking.ranking import get_ranking_recount_status
    from rider.models import Rider

    clubs_without_manager = (
        Club.objects.filter(is_active=True)
        .exclude(team_name="Bez klubové příslušnosti")
        .exclude(managed_users__is_club_manager=True, managed_users__is_active=True)
        .order_by("team_name")
        .distinct()
    )

    duplicate_email_groups = (
        Account.objects.annotate(email_lower=Lower("email"))
        .values("email_lower")
        .annotate(total=Count("id"))
        .filter(total__gt=1)
        .order_by("-total", "email_lower")
    )
    today = timezone.localdate()
    suspicious_entry_q = (
        Q(payment_complete=False, transaction_date__lt=timezone.now() - timedelta(days=2))
        | Q(checkout=True, payment_complete=False)
        | Q(payment_complete=True, rider__isnull=True)
    )
    checkout_entries_missing_refund = (
        Entry.objects.filter(
            checkout=True,
            payment_complete=True,
            transaction_date__date=today,
        )
        .exclude(credit_transactions__kind=CreditTransaction.Kind.CHECKOUT_REFUND)
        .exclude(suspicious_entry_q)
    )
    orphan_refunds = CreditTransaction.objects.filter(
        kind=CreditTransaction.Kind.CHECKOUT_REFUND,
        source_entry__isnull=True,
        transaction_date__date=today,
    )
    refunds_for_non_checkout_entries = CreditTransaction.objects.filter(
        kind=CreditTransaction.Kind.CHECKOUT_REFUND,
        source_entry__checkout=False,
        transaction_date__date=today,
    )
    pending_avatar_requests = (
        AvatarChangeRequest.objects.filter(status=AvatarChangeRequest.STATUS_PENDING)
        .select_related("uploaded_by", "target_account", "target_rider")
        .order_by("-created")[:8]
    )

    import_candidates = []
    import_fields = (
        ("xls_results_uploaded", "BEM výsledky", "xls_results"),
        ("rem_results_uploaded", "REM výsledky", "rem_results"),
        ("full_results_uploaded", "PDF výsledky", "full_results"),
        ("html_results_uploaded", "HTML výsledky", "html_results"),
        ("bem_entries_created", "BEM registrace", "bem_entries"),
        ("rem_entries_created", "REM registrace", "rem_entries"),
    )
    for event in Event.objects.select_related("organizer").only(
        "id",
        "name",
        "date",
        "organizer__team_name",
        *(field for field, _, _ in import_fields),
    ):
        for timestamp_field, label, file_field in import_fields:
            timestamp = getattr(event, timestamp_field, None)
            if not timestamp:
                continue
            import_candidates.append(
                {
                    "event": event,
                    "label": label,
                    "timestamp": timestamp,
                    "has_file": bool(getattr(event, file_field, None)),
                }
            )
    recent_imports = sorted(import_candidates, key=lambda item: item["timestamp"], reverse=True)[:10]

    _current_year = timezone.localdate().year

    rider_data_issues = {
        "missing_club_count": Rider.objects.filter(is_active=True, club__isnull=True).count(),
        "missing_transponder_count": Rider.objects.filter(
            Q(is_20=True) & (Q(transponder_20__isnull=True) | Q(transponder_20=""))
            | Q(is_24=True) & (Q(transponder_24__isnull=True) | Q(transponder_24=""))
        ).count(),
        "ranking_mismatch_count": Rider.objects.filter(
            Q(is_20=False, points_20__gt=0) | Q(is_24=False, points_24__gt=0)
        ).count(),
    }
    _results_this_year = Result.objects.filter(event__date__year=_current_year)
    result_data_issues = {
        "missing_rider_count": _results_this_year.filter(rider__isnull=True).count(),
        "missing_category_count": _results_this_year.filter(Q(category__isnull=True) | Q(category="")).count(),
        "missing_event_type_count": _results_this_year.filter(Q(event_type__isnull=True) | Q(event_type="")).count(),
        "marked_zero_points_count": _results_this_year.filter(points=0).filter(
            Q(marked_20=True) | Q(marked_24=True)
        ).count(),
    }

    _excluded_event_types = [
        "Světový pohár", "Evropský pohár",
        "Mistrovství Evropy", "Mistrovství světa",
        "Mistrovství ČR družstev",
    ]

    past_events_without_results = (
        Event.objects.select_related("organizer")
        .filter(date__lt=timezone.localdate(), date__year=_current_year, canceled=False)
        .exclude(type_for_ranking__in=_excluded_event_types)
        .annotate(results_count=Count("result"))
        .filter(results_count=0)
        .only("id", "name", "date", "organizer__team_name")
        .order_by("-date")[:10]
    )

    past_events_results_not_sent_ccf = (
        Event.objects.select_related("organizer")
        .filter(date__lt=timezone.localdate(), date__year=_current_year, canceled=False, ccf_uploaded=False)
        .exclude(type_for_ranking__in=_excluded_event_types)
        .annotate(results_count=Count("result"))
        .filter(results_count__gt=0)
        .only("id", "name", "date", "organizer__team_name")
        .order_by("-date")
    )

    checkout_entries_missing_refund_preview = (
        checkout_entries_missing_refund
        .select_related("event", "rider")
        .order_by("-transaction_date")[:3]
    )

    context = {
        "duplicate_email_groups": list(duplicate_email_groups),

        "recent_activation_logs": AccountActivationAuditLog.objects.select_related("account", "actor").order_by("-created_at")[:20],
        "recent_finance_logs": FinanceAuditLog.objects.select_related("actor").order_by("-created_at")[:10],
        "checkout_entries_missing_refund_count": checkout_entries_missing_refund.count(),
        "orphan_refunds_count": orphan_refunds.count(),
        "refunds_for_non_checkout_entries_count": refunds_for_non_checkout_entries.count(),
        "clubs_without_manager": clubs_without_manager[:25],
        "clubs_without_manager_count": clubs_without_manager.count(),
        "pending_avatar_requests": pending_avatar_requests,
        "pending_avatar_requests_count": AvatarChangeRequest.objects.filter(status=AvatarChangeRequest.STATUS_PENDING).count(),
        "recent_imports": recent_imports,
        "ranking_recount_status": get_ranking_recount_status(),
        "rider_data_issues": rider_data_issues,
        "result_data_issues": result_data_issues,
        "past_events_without_results": past_events_without_results,
        "past_events_without_results_count": past_events_without_results.count(),
        "past_events_results_not_sent_ccf": past_events_results_not_sent_ccf,
        "past_events_results_not_sent_ccf_count": past_events_results_not_sent_ccf.count(),
        "checkout_entries_missing_refund_preview": checkout_entries_missing_refund_preview,
    }
    return render(request, "accounts/ops-dashboard.html", context)


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
