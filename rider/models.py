import logging
import os
from django.db import models
from django.db.models import Q
from django.core.cache import cache
from django.utils import timezone
from django.conf import settings
from club.models import Club
from django.db.models.signals import post_delete, pre_save, post_save
from django.dispatch import receiver
from bmx.text_normalization import normalize_search_text

logger = logging.getLogger(__name__)


from datetime import date
import re
from rider.plates import display_plate, legacy_plate_int, normalize_plate_value
from event.utils import normalize_uci_id


class Rider(models.Model):
    """ Class for rider """

    CLASS_BEGINNERS = (
        ("Beginners 1", "Beginners 1"),
        ("Beginners 2", "Beginners 2"),
        ("Beginners 3", "Beginners 3"),
        ("Beginners 4", "Beginners 4"),
    )

    CLASS_20 = (
        ("Boys 6", "Boys 6"),
        ("Boys 7", "Boys 7"),
        ("Boys 8", "Boys 8"),
        ("Boys 9", "Boys 9"),
        ("Boys 10", "Boys 10"),
        ("Boys 11", "Boys 11"),
        ("Boys 12", "Boys 12"),
        ("Boys 13", "Boys 13"),
        ("Boys 14", "Boys 14"),
        ("Boys 15", "Boys 15"),
        ("Boys 16", "Boys 16"),
        ("Men 17-24", "Men 17-24"),
        ("Men 25-29", "Men 25-29"),
        ("Men 30-34", "Men 30-34"),
        ("Men 35 and over", "Men 35 and over"),
        ("Girls 6", "Girls 6"),
        ("Girls 7", "Girls 7"),
        ("Girls 8", "Girls 8"),
        ("Girls 9", "Girls 9"),
        ("Girls 10", "Girls 10"),
        ("Girls 11", "Girls 11"),
        ("Girls 12", "Girls 12"),
        ("Girls 13", "Girls 13"),
        ("Girls 14", "Girls 14"),
        ("Girls 15", "Girls 15"),
        ("Girls 16", "Girls 16"),
        ("Women 17-24", "Women 17-24"),
        ("Women 25 and over", "Women 25 and over"),
        ("Men Junior", "Men Junior"),
        ("Men Under 23", "Men Under 23"),
        ("Men Elite", "Men Elite"),
        ("Women Junior", "Women Junior"),
        ("Women Under 23", "Women Under 23"),
        ("Women Elite", "Women Elite"),
    )

    CLASS_24 = (
        ("Boys 12 and under", "Boys 12 and under"),
        ("Boys 13 and 14", "Boys 13 and 14"),
        ("Boys 15 and 16", "Boys 15 and 16"),
        ("Men 17-24", "Men 17-24"),
        ("Men 25-29", "Men 25-29"),
        ("Men 30-34", "Men 30-34"),
        ("Men 35-39", "Men 35-39"),
        ("Men 40-44", "Men 40-44"),
        ("Men 45-49", "Men 45-49"),
        ("Men 50 and over", "Men 50 and over"),
        ("Girls 12 and under", "Girls 12 and under"),
        ("Girls 13-16", "Girls 13-16"),
        ("Women 17-29", "Women 17-29"),
        ("Women 30-39", "Women 30-39"),
        ("Women 40 and over", "Women 40 and over"),
    )

    GENDER = (("Muž", "Muž"), ("Žena", "Žena"), ("Ostatní", "Ostatní"))

    uci_id = models.IntegerField(unique=True)
    first_name = models.CharField(max_length=255, blank=False)
    middle_name = models.CharField(max_length=255, blank=True, null=True)
    last_name = models.CharField(max_length=255, blank=False)

    nationality = models.CharField(max_length=3, default="CZE")

    date_of_birth = models.DateField(blank=False)
    rc = models.CharField(max_length=1000, blank=True, null=True, default="")
    gender = models.CharField(choices=GENDER, max_length=10)

    email = models.EmailField(max_length=100, null=True, blank=True)
    search_text_normalized = models.CharField(max_length=512, default="", blank=True, db_index=True)
    phone = models.CharField(max_length=100, null=True, blank=True)

    street = models.CharField(max_length=1000, blank=True, null=True, default="")
    city = models.CharField(max_length=1000, blank=True, null=True, default="")
    zip = models.CharField(max_length=1000, blank=True, null=True, default="")

    photo = models.ImageField(
        upload_to="images/riders/",
        blank=True,
        null=True,
        default="images/riders/uni.jpeg",
    )

    club = models.ForeignKey(
        Club, related_name="rider_club", null=True, on_delete=models.SET_NULL
    )

    is_20 = models.BooleanField(default=False)
    is_24 = models.BooleanField(default=False)
    is_elite = models.BooleanField(default=False)

    points_20 = models.IntegerField(default=0, db_index=True)
    points_24 = models.IntegerField(default=0, db_index=True)

    ranking_20 = models.CharField(max_length=10, null=True, blank=True, db_index=True)
    ranking_24 = models.CharField(max_length=10, null=True, blank=True, db_index=True)

    is_in_talent_team = models.BooleanField(default=False)
    is_in_representation = models.BooleanField(default=False)

    is_qualify_to_cn_20 = models.BooleanField(default=False)
    is_qualify_to_cn_24 = models.BooleanField(default=False)
    mcr_wild_card_20 = models.BooleanField(default=False)
    mcr_wild_card_24 = models.BooleanField(default=False)

    class_20 = models.CharField(
        max_length=50, choices=CLASS_20, default="Boys 6", null=True
    )
    class_24 = models.CharField(
        max_length=50, choices=CLASS_24, default="Boys 12 and under", null=True
    )
    class_beginner = models.CharField(
        max_length=50,
        choices=CLASS_BEGINNERS,
        default="Beginners 4",
        blank=True,
        null=True,
    )

    transponder_20 = models.CharField(max_length=8, blank=True, null=True)
    transponder_24 = models.CharField(max_length=8, blank=True, null=True)

    plate = models.IntegerField(blank=True, null=True, default=0)
    plate_text = models.CharField(max_length=10, blank=True, null=True, default="")
    plate_champ_20 = models.IntegerField(null=True, blank=True)
    plate_champ_24 = models.IntegerField(null=True, blank=True)
    plate_color_20 = models.CharField(max_length=10, default="yellow", null=True)

    emergency_contact = models.CharField(max_length=255, blank=True, null=True)
    emergency_phone = models.CharField(max_length=255, blank=True, null=True)

    have_valid_insurance = models.BooleanField(default=False)

    is_active = models.BooleanField(default=True)
    is_approved = models.BooleanField(default=False)
    valid_licence = models.BooleanField(default=True)
    fix_valid_licence = models.BooleanField(default=False)

    created = models.DateTimeField(auto_now_add=True, null=True)
    updated = models.DateTimeField(auto_now=True, null=True, blank=True)

    def __str__(self):
        return self.first_name + " " + self.last_name

    @property
    def photo_url(self):
        try:
            if not self.photo:
                return ""
            if not self.photo.name:
                return ""
            if self.photo.storage.exists(self.photo.name):
                return self.photo.url

            static_name = self.photo.name.lstrip("/")
            static_candidates = [
                os.path.join(settings.BASE_DIR, "static", static_name),
                os.path.join(settings.BASE_DIR, "staticfiles", static_name),
            ]
            if any(os.path.exists(path) for path in static_candidates):
                static_prefix = settings.STATIC_URL.strip("/")
                return f"/{static_prefix}/{static_name}"

            return ""
        except (ValueError, OSError):
            return ""

    @property
    def initials(self):
        parts = [self.first_name, self.last_name]
        letters = [part.strip()[0].upper() for part in parts if part and part.strip()]
        return "".join(letters[:2])

    @property
    def plate_display(self):
        return display_plate(self.plate_text, self.plate)

    def save(self, *args, **kwargs):
        normalized_plate = normalize_plate_value(self.plate_text)
        if not normalized_plate:
            normalized_plate = normalize_plate_value(self.plate)

        self.plate_text = normalized_plate
        self.plate = legacy_plate_int(normalized_plate)
        self.search_text_normalized = normalize_search_text(
            " ".join(
                str(part) for part in [
                    self.first_name,
                    self.middle_name,
                    self.last_name,
                    self.email,
                    self.uci_id,
                    self.transponder_20,
                    self.transponder_24,
                    self.plate_text,
                ] if part
            )
        )
        super().save(*args, **kwargs)

    class Meta:
        db_table = "Jezdci"
        ordering = ["last_name", "first_name"]
        verbose_name = "Jezdec"
        verbose_name_plural = "Jezdci"

    def get_age(self, rider):
        return date.today().year - rider.date_of_birth.year

    @staticmethod
    def sum_of_riders():
        return Rider.objects.filter(is_active=True).count()

    @staticmethod
    def set_class_beginner(rider):
        age: int = rider.get_age(rider)
        if age <= 6:
            return "Beginners 1"
        elif age <= 8:
            return "Beginners 2"
        elif age <= 10:
            return "Beginners 3"
        else:
            return "Beginners 4"

    @staticmethod
    def set_class_20(rider):
        age = rider.get_age(rider)
        if rider.is_elite:
            if rider.gender == "Muž" or rider.gender == "Ostatní":
                if age <= 18:
                    return "Men Junior"
                elif age <= 22:
                    return "Men Under 23"
                else:
                    return "Men Elite"
            else:
                if age <= 18:
                    return "Women Junior"
                elif age <= 22:
                    return "Women Under 23"
                else:
                    return "Women Elite"

        if not rider.is_elite:
            if rider.gender == "Muž" or rider.gender == "Ostatní":
                if age <= 6:
                    return "Boys 6"
                elif age == 7:
                    return "Boys 7"
                elif age == 8:
                    return "Boys 8"
                elif age == 9:
                    return "Boys 9"
                elif age == 10:
                    return "Boys 10"
                elif age == 11:
                    return "Boys 11"
                elif age == 12:
                    return "Boys 12"
                elif age == 13:
                    return "Boys 13"
                elif age == 14:
                    return "Boys 14"
                elif age == 15:
                    return "Boys 15"
                elif age == 16:
                    return "Boys 16"
                elif age <= 24:
                    return "Men 17-24"
                elif age <= 29:
                    return "Men 25-29"
                elif age <= 34:
                    return "Men 30-34"
                else:
                    return "Men 35 and over"

            else:
                if age <= 6:
                    return "Girls 6"
                elif age == 7:
                    return "Girls 7"
                elif age == 8:
                    return "Girls 8"
                elif age == 9:
                    return "Girls 9"
                elif age == 10:
                    return "Girls 10"
                elif age == 11:
                    return "Girls 11"
                elif age == 12:
                    return "Girls 12"
                elif age == 13:
                    return "Girls 13"
                elif age == 14:
                    return "Girls 14"
                elif age == 15:
                    return "Girls 15"
                elif age == 16:
                    return "Girls 16"
                elif age <= 24:
                    return "Women 17-24"
                else:
                    return "Women 25 and over"

    @staticmethod
    def set_class_24(rider):
        age = rider.get_age(rider)
        if rider.gender == "Muž" or rider.gender == "Ostatní":
            if age <= 12:
                return "Boys 12 and under"
            elif age <= 14:
                return "Boys 13 and 14"
            elif age <= 16:
                return "Boys 15 and 16"
            elif age <= 24:
                return "Men 17-24"
            elif age <= 29:
                return "Men 25-29"
            elif age <= 34:
                return "Men 30-34"
            elif age <= 39:
                return "Men 35-39"
            elif age <= 44:
                return "Men 40-44"
            elif age <= 49:
                return "Men 45-49"
            else:
                return "Men 50 and over"
        else:
            if age <= 12:
                return "Girls 12 and under"
            elif age <= 16:
                return "Girls 13-16"
            elif age <= 29:
                return "Women 17-29"
            elif age <= 39:
                return "Women 30-39"
            else:
                return "Women 40 and over"

    @staticmethod
    def plate_color(class_20):
        if re.search("Elite", class_20):
            return "white"
        elif re.search("Under", class_20):
            return "gray"
        elif re.search("Junior", class_20):
            return "black"
        elif re.search("Girls", class_20) or re.search("Women", class_20):
            return "blue"
        else:
            return "yellow"


class RiderTransponderChange(models.Model):
    SLOT_20 = "20"
    SLOT_24 = "24"
    SLOT_CHOICES = (
        (SLOT_20, '20"'),
        (SLOT_24, '24"'),
    )

    rider = models.ForeignKey(
        "rider.Rider",
        on_delete=models.CASCADE,
        related_name="transponder_changes",
    )
    slot = models.CharField(max_length=2, choices=SLOT_CHOICES)
    old_transponder = models.CharField(max_length=8, blank=True, null=True)
    new_transponder = models.CharField(max_length=8, blank=True, null=True)
    changed_by = models.ForeignKey(
        "accounts.Account",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transponder_changes_made",
    )
    changed_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "Historie změny čipu"
        verbose_name_plural = "Historie změn čipů"
        ordering = ["-changed_at"]
        indexes = [
            models.Index(fields=["rider", "slot", "changed_at"], name="rider_chip_hist_date"),
        ]

    def __str__(self):
        return f"{self.rider} {self.get_slot_display()}: {self.old_transponder or '-'} -> {self.new_transponder or '-'}"

    @property
    def battery_expected_until(self):
        changed_date = self.changed_at.date() if self.changed_at else date.today()
        return changed_date + timezone.timedelta(days=365 * 3)


class RiderStatsSubscription(models.Model):
    STATUS_ACTIVE = "active"
    STATUS_EXPIRED = "expired"
    STATUS_CANCELED = "canceled"
    STATUS_PAST_DUE = "past_due"
    STATUS_CHOICES = (
        (STATUS_ACTIVE, "Aktivní"),
        (STATUS_EXPIRED, "Expirované"),
        (STATUS_CANCELED, "Zrušené"),
        (STATUS_PAST_DUE, "Neprodloužené"),
    )

    user = models.ForeignKey("accounts.Account", on_delete=models.CASCADE, related_name="rider_stats_subscriptions")
    rider = models.ForeignKey("rider.Rider", on_delete=models.CASCADE, related_name="premium_subscriptions")
    season = models.ForeignKey("event.SeasonSettings", on_delete=models.PROTECT, related_name="rider_stats_subscriptions")
    starts_at = models.DateTimeField()
    expires_at = models.DateTimeField(db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE, db_index=True)
    monthly_price = models.IntegerField(default=0)
    auto_renew = models.BooleanField(default=True)
    last_renewed_at = models.DateTimeField(null=True, blank=True)
    canceled_at = models.DateTimeField(null=True, blank=True)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Předplatné prémiových statistik"
        verbose_name_plural = "Předplatná prémiových statistik"
        indexes = [
            models.Index(fields=["user", "status", "expires_at"], name="rider_sub_user_status_exp"),
            models.Index(fields=["rider", "status", "expires_at"], name="rider_sub_rider_status_exp"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "rider"],
                condition=Q(status="active"),
                name="uniq_active_rider_stats_subscription",
            )
        ]

    def __str__(self):
        return f"{self.user} -> {self.rider} ({self.get_status_display()})"


class RiderStatsCharge(models.Model):
    REASON_INITIAL = "initial"
    REASON_RENEWAL = "renewal"
    REASON_CHOICES = (
        (REASON_INITIAL, "První aktivace"),
        (REASON_RENEWAL, "Obnovení"),
    )

    user = models.ForeignKey("accounts.Account", on_delete=models.CASCADE, related_name="rider_stats_charges")
    rider = models.ForeignKey("rider.Rider", on_delete=models.CASCADE, related_name="premium_charges")
    season = models.ForeignKey("event.SeasonSettings", on_delete=models.PROTECT, related_name="rider_stats_charges")
    subscription = models.ForeignKey(
        "rider.RiderStatsSubscription",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="charges",
    )
    amount = models.IntegerField(default=0)
    period_start = models.DateTimeField()
    period_end = models.DateTimeField()
    reason = models.CharField(max_length=20, choices=REASON_CHOICES, default=REASON_INITIAL)
    payment_valid = models.BooleanField(default=True)
    transaction_date = models.DateTimeField(auto_now_add=True, null=True)

    class Meta:
        verbose_name = "Odečet za prémiové statistiky"
        verbose_name_plural = "Odečty za prémiové statistiky"
        indexes = [
            models.Index(fields=["user", "payment_valid", "transaction_date"], name="rider_charge_user_valid_date"),
            models.Index(fields=["subscription"], name="rider_charge_subscription"),
        ]

    def __str__(self):
        return f"{self.user} - {self.rider} - {self.amount} Kč"


class TrainerClubSubscription(models.Model):
    STATUS_ACTIVE = "active"
    STATUS_EXPIRED = "expired"
    STATUS_CANCELED = "canceled"
    STATUS_PAST_DUE = "past_due"
    STATUS_CHOICES = (
        (STATUS_ACTIVE, "Aktivní"),
        (STATUS_EXPIRED, "Expirované"),
        (STATUS_CANCELED, "Zrušené"),
        (STATUS_PAST_DUE, "Neprodloužené"),
    )

    PRODUCT_CLUB_STATS = "club_stats"
    PRODUCT_EXTENDED = "club_extended"
    PRODUCT_CHOICES = (
        (PRODUCT_CLUB_STATS, "Prémiové statistiky klubu"),
        (PRODUCT_EXTENDED, "Rozšířené funkce trenéra"),
    )

    user = models.ForeignKey("accounts.Account", on_delete=models.CASCADE, related_name="trainer_club_subscriptions")
    club = models.ForeignKey("club.Club", on_delete=models.CASCADE, related_name="trainer_subscriptions")
    season = models.ForeignKey("event.SeasonSettings", on_delete=models.PROTECT, related_name="trainer_club_subscriptions")
    product = models.CharField(max_length=30, choices=PRODUCT_CHOICES, default=PRODUCT_CLUB_STATS, db_index=True)
    starts_at = models.DateTimeField()
    expires_at = models.DateTimeField(db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE, db_index=True)
    monthly_price = models.IntegerField(default=0)
    auto_renew = models.BooleanField(default=True)
    last_renewed_at = models.DateTimeField(null=True, blank=True)
    canceled_at = models.DateTimeField(null=True, blank=True)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Předplatné trenéra pro klub"
        verbose_name_plural = "Předplatná trenérů pro kluby"
        indexes = [
            models.Index(fields=["user", "product", "status", "expires_at"], name="trainer_sub_user_prod_exp"),
            models.Index(fields=["club", "product", "status", "expires_at"], name="trainer_sub_club_prod_exp"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "club", "product"],
                condition=Q(status="active"),
                name="uniq_active_trainer_club_subscription",
            )
        ]

    def __str__(self):
        return f"{self.user} -> {self.club} [{self.get_product_display()}]"


class TrainerClubCharge(models.Model):
    REASON_INITIAL = "initial"
    REASON_RENEWAL = "renewal"
    REASON_CHOICES = (
        (REASON_INITIAL, "První aktivace"),
        (REASON_RENEWAL, "Obnovení"),
    )

    user = models.ForeignKey("accounts.Account", on_delete=models.CASCADE, related_name="trainer_club_charges")
    club = models.ForeignKey("club.Club", on_delete=models.CASCADE, related_name="trainer_charges")
    season = models.ForeignKey("event.SeasonSettings", on_delete=models.PROTECT, related_name="trainer_club_charges")
    subscription = models.ForeignKey(
        "rider.TrainerClubSubscription",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="charges",
    )
    product = models.CharField(
        max_length=30,
        choices=TrainerClubSubscription.PRODUCT_CHOICES,
        default=TrainerClubSubscription.PRODUCT_CLUB_STATS,
    )
    amount = models.IntegerField(default=0)
    period_start = models.DateTimeField()
    period_end = models.DateTimeField()
    reason = models.CharField(max_length=20, choices=REASON_CHOICES, default=REASON_INITIAL)
    payment_valid = models.BooleanField(default=True)
    transaction_date = models.DateTimeField(auto_now_add=True, null=True)

    class Meta:
        verbose_name = "Odečet za trenérské předplatné"
        verbose_name_plural = "Odečty za trenérská předplatná"
        indexes = [
            models.Index(fields=["user", "payment_valid", "transaction_date"], name="trainer_charge_user_valid_date"),
            models.Index(fields=["subscription"], name="trainer_charge_subscription"),
        ]

    def __str__(self):
        return f"{self.user} - {self.club} - {self.amount} Kč"


@receiver(post_save, sender=RiderStatsCharge)
@receiver(post_delete, sender=RiderStatsCharge)
def update_user_balance_for_stats_charge(sender, instance, **kwargs):
    if not instance.user_id:
        return
    from accounts.models import Account
    from event.credit import calculate_user_balance

    new_balance = calculate_user_balance(instance.user_id)
    Account.objects.filter(id=instance.user_id).update(credit=new_balance)


@receiver(post_save, sender=TrainerClubCharge)
@receiver(post_delete, sender=TrainerClubCharge)
def update_user_balance_for_trainer_charge(sender, instance, **kwargs):
    if not instance.user_id:
        return
    from accounts.models import Account
    from event.credit import calculate_user_balance

    new_balance = calculate_user_balance(instance.user_id)
    Account.objects.filter(id=instance.user_id).update(credit=new_balance)


# nastavení kategorie jezdce při ukládání
@receiver(pre_save, sender=Rider)
def set_class(sender, instance, **kwargs):
    age = instance.get_age(instance)
    is_elite = instance.is_elite
    instance.class_beginner = instance.set_class_beginner(instance)
    instance.class_20 = instance.set_class_20(instance)
    instance.class_24 = instance.set_class_24(instance)
    instance.plate_color_20 = instance.plate_color(instance.class_20)


pre_save.connect(set_class, sender=Rider)

# vymazání staré fotky jezdce při její změně
@receiver(pre_save, sender=Rider)
def delete_file_on_change_extension(sender, instance, **kwargs):
    if instance.pk:
        try:
            old_photo = Rider.objects.get(pk=instance.pk).photo
        except Rider.DoesNotExist:
            return
        else:
            new_photo = instance.photo
            default_paths = ("static/images/riders/uni.jpeg", "media/images/riders/uni.jpeg", "images/riders/uni.jpeg")
            if str(old_photo) in default_paths:
                return

            try:
                old_name = getattr(old_photo, "name", "") or ""
                new_name = getattr(new_photo, "name", "") or ""
                if old_photo and old_name not in default_paths and old_name != new_name:
                    old_photo.delete(save=False)
            except Exception:
                pass


pre_save.connect(delete_file_on_change_extension, sender=Rider)


@receiver(post_save, sender=Rider)
@receiver(post_delete, sender=Rider)
def invalidate_active_riders_cache(sender, **kwargs):
    cache.delete("active_riders")


class ForeignRider(models.Model):
    """ Class for foreign rider """

    CLASS_20 = (
        ("Boys 6", "Boys 6"),
        ("Boys 7", "Boys 7"),
        ("Boys 8", "Boys 8"),
        ("Boys 9", "Boys 9"),
        ("Boys 10", "Boys 10"),
        ("Boys 11", "Boys 11"),
        ("Boys 12", "Boys 12"),
        ("Boys 13", "Boys 13"),
        ("Boys 14", "Boys 14"),
        ("Boys 15", "Boys 15"),
        ("Boys 16", "Boys 16"),
        ("Men 17-24", "Men 17-24"),
        ("Men 25-29", "Men 25-29"),
        ("Men 30-34", "Men 30-34"),
        ("Men 35 and over", "Men 35 and over"),
        ("Girls 6", "Girls 6"),
        ("Girls 7", "Girls 7"),
        ("Girls 8", "Girls 8"),
        ("Girls 9", "Girls 9"),
        ("Girls 10", "Girls 10"),
        ("Girls 11", "Girls 11"),
        ("Girls 12", "Girls 12"),
        ("Girls 13", "Girls 13"),
        ("Girls 14", "Girls 14"),
        ("Girls 15", "Girls 15"),
        ("Girls 16", "Girls 16"),
        ("Women 17-24", "Women 17-24"),
        ("Women 25 and over", "Women 25 and over"),
        ("Men Junior", "Men Junior"),
        ("Men Under 23", "Men Under 23"),
        ("Men Elite", "Men Elite"),
        ("Women Junior", "Women Junior"),
        ("Women Under 23", "Women Under 23"),
        ("Women Elite", "Women Elite"),
    )

    CLASS_24 = (
        ("Boys 12 and under", "Boys 12 and under"),
        ("Boys 13 and 14", "Boys 13 and 14"),
        ("Boys 15 and 16", "Boys 15 and 16"),
        ("Men 17-24", "Men 17-24"),
        ("Men 25-29", "Men 25-29"),
        ("Men 30-34", "Men 30-34"),
        ("Men 35-39", "Men 35-39"),
        ("Men 40-44", "Men 40-44"),
        ("Men 45-49", "Men 45-49"),
        ("Men 50 and over", "Men 50 and over"),
        ("Girls 12 and under", "Girls 12 and under"),
        ("Girls 13-16", "Girls 13-16"),
        ("Women 17-29", "Women 17-29"),
        ("Women 30-39", "Women 30-39"),
        ("Women 40 and over", "Women 40 and over"),
    )

    GENDER = (("Muž", "Muž"), ("Žena", "Žena"), ("Ostatní", "Ostatní"))

    uci_id = models.IntegerField(unique=True)
    first_name = models.CharField(max_length=255, blank=False)
    last_name = models.CharField(max_length=255, blank=False)

    date_of_birth = models.DateField(blank=False)
    gender = models.CharField(choices=GENDER, max_length=10)

    nationality = models.CharField(max_length=3, default="")

    class_20 = models.CharField(
        max_length=50, choices=CLASS_20, default="Boys 6", null=True
    )
    class_24 = models.CharField(
        max_length=50, choices=CLASS_24, default="Boys 12 and under", null=True
    )

    is_20 = models.BooleanField(default=False)
    is_24 = models.BooleanField(default=False)
    is_elite = models.BooleanField(default=False)

    transponder_20 = models.CharField(max_length=8, blank=True, null=True)
    transponder_24 = models.CharField(max_length=8, blank=True, null=True)

    plate = models.IntegerField(blank=True, null=True, default=0)
    plate_text = models.CharField(max_length=10, blank=True, null=True, default="")

    state = models.CharField(max_length=3, null=True, blank=True)
    club = models.CharField(max_length=200, null=True, blank=True)

    created = models.DateTimeField(auto_now_add=True, null=True)
    updated = models.DateTimeField(auto_now=True, null=True, blank=True)

    def __str__(self):
        return self.first_name + " " + self.last_name

    @property
    def plate_display(self):
        return display_plate(self.plate_text, self.plate)

    def save(self, *args, **kwargs):
        self.uci_id = normalize_uci_id(self.uci_id)
        normalized_plate = normalize_plate_value(self.plate_text)
        if not normalized_plate:
            normalized_plate = normalize_plate_value(self.plate)

        self.plate_text = normalized_plate
        self.plate = legacy_plate_int(normalized_plate)
        super().save(*args, **kwargs)

    class Meta:
        db_table = "Zahranicni_jezdci"
        ordering = ["last_name", "first_name"]
        verbose_name = "Zahranicni jezdec"
        verbose_name_plural = "Zahranicni jezdci"

    def get_age(self, rider):
        return date.today().year - rider.date_of_birth.year

    @staticmethod
    def set_class_20(gender, age: int, is_elite):
        if is_elite:
            if gender == "Muž" or gender == "Ostatní":
                if age <= 18:
                    return "Men Junior"
                elif age <= 22:
                    return "Men Under 23"
                else:
                    return "Men Elite"
            else:
                if age <= 18:
                    return "Women Junior"
                elif age <= 22:
                    return "Women Under 23"
                else:
                    return "Women Elite"

        if not is_elite:
            if gender == "Muž" or gender == "Ostatní":
                if age <= 6:
                    return "Boys 6"
                elif age == 7:
                    return "Boys 7"
                elif age == 8:
                    return "Boys 8"
                elif age == 9:
                    return "Boys 9"
                elif age == 10:
                    return "Boys 10"
                elif age == 11:
                    return "Boys 11"
                elif age == 12:
                    return "Boys 12"
                elif age == 13:
                    return "Boys 13"
                elif age == 14:
                    return "Boys 14"
                elif age == 15:
                    return "Boys 15"
                elif age == 16:
                    return "Boys 16"
                elif age <= 24:
                    return "Men 17-24"
                elif age <= 29:
                    return "Men 25-29"
                elif age <= 34:
                    return "Men 30-34"
                else:
                    return "Men 35 and over"

            else:
                if age <= 6:
                    return "Girls 6"
                elif age == 7:
                    return "Girls 7"
                elif age == 8:
                    return "Girls 8"
                elif age == 9:
                    return "Girls 9"
                elif age == 10:
                    return "Girls 10"
                elif age == 11:
                    return "Girls 11"
                elif age == 12:
                    return "Girls 12"
                elif age == 13:
                    return "Girls 13"
                elif age == 14:
                    return "Girls 14"
                elif age == 15:
                    return "Girls 15"
                elif age == 16:
                    return "Girls 16"
                elif age <= 24:
                    return "Women 17-24"
                else:
                    return "Women 25 and over"

    @staticmethod
    def set_class_24(gender, age: int):
        logger.debug(f"Nastavuji kategorii 24 - věk {age}, pohlaví {gender}")
        if gender == "Muž" or gender == "Ostatní":
            if age <= 12:
                return "Boys 12 and under"
            elif age <= 14:
                return "Boys 13 and 14"
            elif age <= 16:
                return "Boys 15 and 16"
            elif age <= 24:
                return "Men 17-24"
            elif age <= 29:
                return "Men 25-29"
            elif age <= 34:
                return "Men 30-34"
            elif age <= 39:
                return "Men 35-39"
            elif age <= 44:
                return "Men 40-44"
            elif age <= 49:
                return "Men 45-49"
            else:
                return "Men 50 and over"
        else:
            if age <= 12:
                return "Girls 12 and under"
            elif age <= 16:
                return "Girls 13-16"
            elif age <= 29:
                return "Women 17-29"
            elif age <= 39:
                return "Women 30-39"
            else:
                return "Women 40 and over"


@receiver(pre_save, sender=ForeignRider)
def set_class_foreign(sender, instance, *args, **kwargs):
    age = instance.get_age(instance)
    is_elite = instance.is_elite
    instance.class_20 = instance.set_class_20(instance.gender, age, is_elite)
    instance.class_24 = instance.set_class_24(instance.gender, age)


# ---------------------------------------------------------------------------
# Mobilní aplikace – předplatné
# ---------------------------------------------------------------------------

class MobileAppSubscription(models.Model):
    STATUS_ACTIVE = "active"
    STATUS_EXPIRED = "expired"
    STATUS_CANCELED = "canceled"
    STATUS_PAST_DUE = "past_due"
    STATUS_CHOICES = (
        (STATUS_ACTIVE, "Aktivní"),
        (STATUS_EXPIRED, "Expirované"),
        (STATUS_CANCELED, "Zrušené"),
        (STATUS_PAST_DUE, "Neprodloužené"),
    )

    user = models.ForeignKey("accounts.Account", on_delete=models.CASCADE, related_name="mobile_app_subscriptions")
    season = models.ForeignKey("event.SeasonSettings", on_delete=models.PROTECT, related_name="mobile_app_subscriptions")
    starts_at = models.DateTimeField()
    expires_at = models.DateTimeField(db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE, db_index=True)
    monthly_price = models.IntegerField(default=0)
    auto_renew = models.BooleanField(default=True)
    last_renewed_at = models.DateTimeField(null=True, blank=True)
    canceled_at = models.DateTimeField(null=True, blank=True)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Předplatné mobilní aplikace"
        verbose_name_plural = "Předplatná mobilní aplikace"
        indexes = [
            models.Index(fields=["user", "status", "expires_at"], name="mobile_sub_user_status_exp"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["user"],
                condition=Q(status="active"),
                name="uniq_active_mobile_app_subscription",
            )
        ]

    def __str__(self):
        return f"{self.user} – mobilní app ({self.get_status_display()})"


class MobileAppCharge(models.Model):
    REASON_INITIAL = "initial"
    REASON_RENEWAL = "renewal"
    REASON_PROMO = "promo"
    REASON_CHOICES = (
        (REASON_INITIAL, "První aktivace"),
        (REASON_RENEWAL, "Obnovení"),
        (REASON_PROMO, "Promo kód"),
    )

    user = models.ForeignKey("accounts.Account", on_delete=models.CASCADE, related_name="mobile_app_charges")
    season = models.ForeignKey("event.SeasonSettings", on_delete=models.PROTECT, related_name="mobile_app_charges")
    subscription = models.ForeignKey(
        "rider.MobileAppSubscription",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="charges",
    )
    amount = models.IntegerField(default=0)
    period_start = models.DateTimeField()
    period_end = models.DateTimeField()
    reason = models.CharField(max_length=20, choices=REASON_CHOICES, default=REASON_INITIAL)
    payment_valid = models.BooleanField(default=True)
    transaction_date = models.DateTimeField(auto_now_add=True, null=True)

    class Meta:
        verbose_name = "Odečet za mobilní aplikaci"
        verbose_name_plural = "Odečty za mobilní aplikaci"
        indexes = [
            models.Index(fields=["user", "payment_valid", "transaction_date"], name="mobile_charge_user_valid_date"),
            models.Index(fields=["subscription"], name="mobile_charge_subscription"),
        ]

    def __str__(self):
        return f"{self.user} – mobilní app – {self.amount} Kč"


@receiver(post_save, sender=MobileAppCharge)
@receiver(post_delete, sender=MobileAppCharge)
def update_user_balance_for_mobile_charge(sender, instance, **kwargs):
    if not instance.user_id:
        return
    from accounts.models import Account
    from event.credit import calculate_user_balance

    new_balance = calculate_user_balance(instance.user_id)
    Account.objects.filter(id=instance.user_id).update(credit=new_balance)


# ---------------------------------------------------------------------------
# Promo kódy
# ---------------------------------------------------------------------------

import secrets
import string


def _generate_promo_code():
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(10))


class PromoCode(models.Model):
    DISCOUNT_PERCENT = "percent"
    DISCOUNT_FIXED = "fixed"
    DISCOUNT_FREE = "free"
    DISCOUNT_CHOICES = (
        (DISCOUNT_PERCENT, "Procento ze ceny"),
        (DISCOUNT_FIXED, "Pevná sleva (Kč)"),
        (DISCOUNT_FREE, "Zdarma (100 %)"),
    )

    PRODUCT_MOBILE_APP = "mobile_app"
    PRODUCT_RIDER_STATS = "rider_stats"
    PRODUCT_TRAINER_CLUB = "trainer_club"
    PRODUCT_TRAINER_EXTENDED = "trainer_extended"
    PRODUCT_ALL = "all"
    PRODUCT_CHOICES = (
        (PRODUCT_MOBILE_APP, "Mobilní aplikace"),
        (PRODUCT_RIDER_STATS, "Prémiové statistiky"),
        (PRODUCT_TRAINER_CLUB, "Trenérské statistiky klubu"),
        (PRODUCT_TRAINER_EXTENDED, "Rozšířené trenérské funkce"),
        (PRODUCT_ALL, "Vše"),
    )

    code = models.CharField(max_length=32, unique=True, default=_generate_promo_code)
    description = models.CharField(max_length=255, blank=True)
    discount_type = models.CharField(max_length=10, choices=DISCOUNT_CHOICES, default=DISCOUNT_FREE)
    discount_value = models.IntegerField(default=100, help_text="Procento (0–100) nebo pevná částka v Kč. U 'Zdarma' se ignoruje.")
    product = models.CharField(max_length=30, choices=PRODUCT_CHOICES, default=PRODUCT_MOBILE_APP, db_index=True)
    max_uses = models.IntegerField(null=True, blank=True, help_text="Prázdné = neomezeno")
    used_count = models.IntegerField(default=0)
    valid_from = models.DateTimeField(null=True, blank=True)
    valid_until = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        "accounts.Account", on_delete=models.SET_NULL, null=True, blank=True, related_name="created_promo_codes"
    )
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Promo kód"
        verbose_name_plural = "Promo kódy"
        ordering = ["-created"]

    def __str__(self):
        return f"{self.code} ({self.get_product_display()}, {self.get_discount_type_display()})"

    def is_valid(self, at_time=None):
        now = at_time or timezone.now()
        if not self.is_active:
            return False
        if self.valid_from and now < self.valid_from:
            return False
        if self.valid_until and now > self.valid_until:
            return False
        if self.max_uses is not None and self.used_count >= self.max_uses:
            return False
        return True

    def calculate_discount(self, original_price):
        if self.discount_type == self.DISCOUNT_FREE:
            return original_price
        if self.discount_type == self.DISCOUNT_PERCENT:
            return int(original_price * self.discount_value / 100)
        if self.discount_type == self.DISCOUNT_FIXED:
            return min(self.discount_value, original_price)
        return 0


class PromoCodeUsage(models.Model):
    promo_code = models.ForeignKey(PromoCode, on_delete=models.CASCADE, related_name="usages")
    user = models.ForeignKey("accounts.Account", on_delete=models.CASCADE, related_name="promo_code_usages")
    product = models.CharField(max_length=30)
    discount_applied = models.IntegerField(default=0)
    used_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Použití promo kódu"
        verbose_name_plural = "Použití promo kódů"
        ordering = ["-used_at"]
        constraints = [
            models.UniqueConstraint(fields=["promo_code", "user"], name="uniq_promo_usage_per_user"),
        ]

    def __str__(self):
        return f"{self.user} – {self.promo_code.code} ({self.used_at:%Y-%m-%d})"


pre_save.connect(set_class_foreign, sender=ForeignRider)
