import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

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
