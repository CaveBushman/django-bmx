import logging
import os
from uuid import uuid4

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.files.storage import default_storage
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django_ckeditor_5.exceptions import NoImageException
from django_ckeditor_5.forms import UploadFileForm
from django_ckeditor_5.storage_utils import image_verify

from event.forms import EventPropositionForm
from event.models import Event, EventProposition

logger = logging.getLogger(__name__)


def _get_structured_proposition(event):
    try:
        return event.structured_proposition
    except EventProposition.DoesNotExist:
        return None


def can_manage_event_proposition(user, event):
    if not user.is_authenticated:
        return False
    if user.is_admin or user.is_superuser or user.is_staff:
        return True
    return bool(
        user.is_club_manager
        and user.club_id
        and event.organizer_id
        and user.club_id == event.organizer_id
    )


def can_upload_proposition_editor_media(user):
    if not user.is_authenticated:
        return False
    return bool(
        user.is_admin
        or user.is_superuser
        or user.is_staff
        or user.is_club_manager
    )


@require_POST
@login_required(login_url="/event/not-reg")
def proposition_editor_upload_view(request):
    if not can_upload_proposition_editor_media(request.user):
        return JsonResponse(
            {"error": {"message": "Nemáte oprávnění nahrávat obrázky."}},
            status=403,
        )

    form = UploadFileForm(request.POST, request.FILES)
    if not form.is_valid():
        message = form.errors.get("upload", ["Neplatný upload obrázku."])[0]
        return JsonResponse({"error": {"message": message}}, status=400)

    uploaded_file = request.FILES["upload"]

    try:
        image_verify(uploaded_file)
    except NoImageException:
        return JsonResponse(
            {"error": {"message": "Nahraný soubor není platný obrázek."}},
            status=400,
        )

    uploaded_file.seek(0)
    file_ext = os.path.splitext(uploaded_file.name or "")[1].lower() or ".jpg"
    stored_name = default_storage.save(
        f"proposition_uploads/{uuid4().hex}{file_ext}",
        uploaded_file,
    )
    return JsonResponse({"url": default_storage.url(stored_name)})


def proposition_detail_view(request, pk):
    event = get_object_or_404(
        Event.objects.select_related("organizer", "structured_proposition"),
        pk=pk,
    )
    proposition = _get_structured_proposition(event)
    can_edit = can_manage_event_proposition(request.user, event)

    if proposition and (proposition.is_published or can_edit):
        return render(
            request,
            "event/proposition-detail.html",
            {
                "event": event,
                "proposition": proposition,
                "can_edit_proposition": can_edit,
                "is_preview": not proposition.is_published,
            },
        )

    if event.proposition:
        return redirect(event.proposition.url)

    messages.error(request, "Propozice pro tento závod zatím nejsou zveřejněné.")
    return redirect("event:event-detail", pk=pk)


@login_required(login_url="/event/not-reg")
def proposition_edit_view(request, pk):
    event = get_object_or_404(
        Event.objects.select_related("organizer", "structured_proposition"),
        pk=pk,
    )
    if not can_manage_event_proposition(request.user, event):
        messages.error(request, "Propozice může upravovat jen klubový manažer pořadatelského klubu.")
        return redirect("event:event-detail", pk=pk)

    proposition, created = EventProposition.objects.get_or_create(
        event=event,
        defaults={"created_by": request.user, "updated_by": request.user},
    )

    if request.method == "POST":
        form = EventPropositionForm(request.POST, instance=proposition)
        if form.is_valid():
            proposition = form.save(commit=False)
            if created and not proposition.created_by_id:
                proposition.created_by = request.user
            proposition.updated_by = request.user
            proposition.save()
            messages.success(request, "Formulářová propozice byla uložena.")
            return redirect("event:proposition-detail", pk=event.pk)
    else:
        form = EventPropositionForm(instance=proposition)

    return render(
        request,
        "event/proposition-edit.html",
        {
            "event": event,
            "form": form,
        },
    )
