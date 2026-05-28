from django import forms
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.translation import gettext_lazy as _

from club.models import McrClubTeam, McrClubTeamMember
from rider.models import Rider


class McrClubTeamRiderChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, rider):
        return f"{rider.first_name} {rider.last_name} #{rider.plate_display}"


class McrClubTeamForm(forms.Form):
    name = forms.CharField(label=_("Název družstva"), max_length=120)
    manager_name = forms.CharField(label=_("Manager družstva"), max_length=120)
    rider_20_1 = McrClubTeamRiderChoiceField(label='20" jezdec 1', queryset=Rider.objects.none(), required=False)
    rider_20_2 = McrClubTeamRiderChoiceField(label='20" jezdec 2', queryset=Rider.objects.none(), required=False)
    rider_20_3 = McrClubTeamRiderChoiceField(label='20" jezdec 3', queryset=Rider.objects.none(), required=False)
    rider_20_4 = McrClubTeamRiderChoiceField(label='20" jezdec 4', queryset=Rider.objects.none(), required=False)
    rider_24 = McrClubTeamRiderChoiceField(label='24" jezdec', queryset=Rider.objects.none(), required=False)

    def __init__(self, *args, club, year, team=None, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.club = club
        self.year = year
        self.team = team
        self.user = user
        self.assigned_rider_ids_by_wheel = self._get_assigned_rider_ids_by_wheel()
        rider_queryset = (
            Rider.objects.filter(club=club, is_active=True, is_approved=True)
            .order_by("last_name", "first_name", "uci_id")
        )
        for field_name in self._rider_field_names():
            self.fields[field_name].queryset = rider_queryset
            self.fields[field_name].empty_label = _("Vyber jezdce")

        for field in self.fields.values():
            field.widget.attrs.update({"class": self._input_class()})
        for field_name in ("rider_20_1", "rider_20_2", "rider_20_3", "rider_20_4"):
            self.fields[field_name].widget.attrs["data-assigned-same-wheel"] = ",".join(
                str(rider_id) for rider_id in sorted(self.assigned_rider_ids_by_wheel[McrClubTeamMember.WHEEL_20])
            )
        self.fields["rider_24"].widget.attrs["data-assigned-same-wheel"] = ",".join(
            str(rider_id) for rider_id in sorted(self.assigned_rider_ids_by_wheel[McrClubTeamMember.WHEEL_24])
        )

        if team and not self.is_bound:
            self.initial.update({"name": team.name, "manager_name": team.manager_name})
            members_20 = list(team.members.filter(wheel=McrClubTeamMember.WHEEL_20).order_by("position", "id"))
            for index, member in enumerate(members_20[:4], start=1):
                self.initial[f"rider_20_{index}"] = member.rider_id
            member_24 = team.members.filter(wheel=McrClubTeamMember.WHEEL_24).order_by("position", "id").first()
            if member_24:
                self.initial["rider_24"] = member_24.rider_id

    @staticmethod
    def _input_class():
        return (
            "mt-2 block w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm "
            "text-slate-900 shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-2 "
            "focus:ring-indigo-500/20 dark:border-slate-700 dark:bg-slate-900 dark:text-white"
        )

    @staticmethod
    def _rider_field_names():
        return ["rider_20_1", "rider_20_2", "rider_20_3", "rider_20_4", "rider_24"]

    def _get_assigned_rider_ids_by_wheel(self):
        memberships = McrClubTeamMember.objects.filter(
            team__year=self.year,
            team__club=self.club,
        )
        if self.team:
            memberships = memberships.exclude(team=self.team)
        assigned = {
            McrClubTeamMember.WHEEL_20: set(),
            McrClubTeamMember.WHEEL_24: set(),
        }
        for rider_id, wheel in memberships.values_list("rider_id", "wheel"):
            assigned[wheel].add(rider_id)
        return assigned

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        duplicate = McrClubTeam.objects.filter(year=self.year, club=self.club, name__iexact=name)
        if self.team:
            duplicate = duplicate.exclude(pk=self.team.pk)
        if duplicate.exists():
            raise ValidationError(_("Družstvo s tímto názvem už pro daný rok existuje."))
        return name

    def clean_manager_name(self):
        return self.cleaned_data["manager_name"].strip()

    def clean(self):
        cleaned_data = super().clean()
        entries = []
        for index in range(1, 5):
            rider = cleaned_data.get(f"rider_20_{index}")
            if rider:
                entries.append((rider, McrClubTeamMember.WHEEL_20, index))
        rider_24 = cleaned_data.get("rider_24")
        if rider_24:
            entries.append((rider_24, McrClubTeamMember.WHEEL_24, 5))

        unique_rider_ids = {rider.id for rider, _wheel, _position in entries}
        if not unique_rider_ids:
            raise ValidationError(_("Družstvo musí mít alespoň jednoho jezdce."))
        if len(unique_rider_ids) > 4:
            raise ValidationError(_("Družstvo může mít nejvýše čtyři různé jezdce."))

        duplicate_20_ids = [
            rider.id for rider, wheel, _position in entries if wheel == McrClubTeamMember.WHEEL_20
        ]
        if len(duplicate_20_ids) != len(set(duplicate_20_ids)):
            raise ValidationError(_('Stejný jezdec nesmí být vybraný ve 20" pozicích vícekrát.'))

        for rider, wheel, _position in entries:
            if rider.id in self.assigned_rider_ids_by_wheel[wheel]:
                raise ValidationError(
                    _('%(rider)s už je v jiném družstvu přihlášený na %(wheel)s".')
                    % {"rider": rider, "wheel": wheel}
                )

        self.cleaned_entries = entries
        return cleaned_data

    @transaction.atomic
    def save(self):
        team = self.team or McrClubTeam(year=self.year, club=self.club, created_by=self.user)
        team.name = self.cleaned_data["name"]
        team.manager_name = self.cleaned_data["manager_name"]
        team.club = self.club
        team.year = self.year
        if self.user and not team.created_by_id:
            team.created_by = self.user
        team.save()

        team.members.all().delete()
        McrClubTeamMember.objects.bulk_create(
            [
                McrClubTeamMember(team=team, rider=rider, wheel=wheel, position=position)
                for rider, wheel, position in self.cleaned_entries
            ]
        )
        return team
