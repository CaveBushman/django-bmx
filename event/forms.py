from django import forms
from ckeditor.widgets import CKEditorWidget

from event.models import EventProposition

TEXT_INPUT_CLASS = (
    "w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-slate-700 "
    "shadow-sm outline-none transition focus:border-indigo-500 focus:ring-4 "
    "focus:ring-indigo-100 dark:border-slate-600 dark:bg-slate-900 dark:text-white "
    "dark:focus:ring-indigo-950"
)


class EventPropositionForm(forms.ModelForm):
    class Meta:
        model = EventProposition
        fields = [
            "venue_name",
            "venue_address",
            "office_hours",
            "contact_name",
            "contact_email",
            "contact_phone",
            "summary",
            "schedule",
            "categories",
            "registration_info",
            "awards",
            "accommodation",
            "additional_info",
            "is_published",
        ]
        widgets = {
            "venue_name": forms.TextInput(attrs={"class": TEXT_INPUT_CLASS}),
            "venue_address": forms.TextInput(attrs={"class": TEXT_INPUT_CLASS}),
            "office_hours": forms.TextInput(attrs={"class": TEXT_INPUT_CLASS}),
            "contact_name": forms.TextInput(attrs={"class": TEXT_INPUT_CLASS}),
            "contact_email": forms.EmailInput(attrs={"class": TEXT_INPUT_CLASS}),
            "contact_phone": forms.TextInput(attrs={"class": TEXT_INPUT_CLASS}),
            "summary": CKEditorWidget(),
            "schedule": CKEditorWidget(),
            "categories": CKEditorWidget(),
            "registration_info": CKEditorWidget(),
            "awards": CKEditorWidget(),
            "accommodation": CKEditorWidget(),
            "additional_info": CKEditorWidget(),
        }
