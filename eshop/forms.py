from django import forms
from datetime import timedelta

from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from event.models_events import Event
from .models import Order

_INPUT = (
    "block w-full rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm text-slate-900 "
    "shadow-sm outline-none transition placeholder:text-slate-400 "
    "focus:border-indigo-400 focus:ring-4 focus:ring-indigo-100 "
    "dark:border-slate-700 dark:bg-slate-950 dark:text-white dark:placeholder:text-slate-500 "
    "dark:focus:border-indigo-500 dark:focus:ring-indigo-900/40"
)
_TEXTAREA = _INPUT + " resize-none"


class CheckoutForm(forms.ModelForm):
    event = forms.ModelChoiceField(
        queryset=Event.objects.none(),
        label=_("Závod"),
        widget=forms.Select(attrs={"class": _INPUT}),
        empty_label=_("Vyber závod"),
        required=True,
    )

    class Meta:
        model = Order
        fields = ["first_name", "last_name", "email", "phone", "event", "note"]
        widgets = {
            "first_name": forms.TextInput(attrs={"class": _INPUT, "placeholder": "Jan", "autocomplete": "given-name"}),
            "last_name": forms.TextInput(attrs={"class": _INPUT, "placeholder": "Novák", "autocomplete": "family-name"}),
            "email": forms.EmailInput(attrs={"class": _INPUT, "placeholder": "jan@example.com", "autocomplete": "email"}),
            "phone": forms.TextInput(attrs={"class": _INPUT, "placeholder": "+420 xxx xxx xxx", "autocomplete": "tel"}),
            "note": forms.Textarea(attrs={"class": _TEXTAREA, "rows": 2, "placeholder": "Poznámka k objednávce (nepovinné)…"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        cutoff = timezone.localdate() + timedelta(days=5)
        self.fields["event"].queryset = Event.objects.filter(
            date__gte=cutoff,
            eshop_pickup_enabled=True,
        ).exclude(
            type_for_ranking__in=[
                "Evropský pohár",
                "Světový pohár",
                "Mistrovství Evropy",
                "Mistrovství světa",
            ]
        ).order_by("date")
        if not self.is_bound and not self.initial.get("event"):
            first_event = self.fields["event"].queryset.first()
            if first_event:
                self.initial["event"] = first_event.pk
