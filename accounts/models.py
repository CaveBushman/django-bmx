from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from event.credit import calculate_user_balance
from club.models import Club
from django.conf import settings
from django.db import transaction
from django.db.models.signals import pre_save
from django.dispatch import receiver
from PIL import Image, ImageOps, ImageFile, UnidentifiedImageError, features
from io import BytesIO
import uuid
from bmx.text_normalization import normalize_search_text

DEFAULT_ACCOUNT_PHOTO_PATHS = (
    "images/users/blank-avatar-200x200.jpg",
)


# Create your models here.


def normalize_account_email(email):
    return (email or "").strip().lower()


class MyAccountManager(BaseUserManager):
    def create_user(self, first_name, last_name, username, email, password=None):
        if not email:
            raise ValueError('Uživatel musí mít e-mailovu adresu.')

        if not username:
            raise ValueError('Uživatel musí mít uživatelské jméno')
        email = normalize_account_email(email)
        user = self.model(
            email=email,
            username=username.strip(),
            first_name=first_name,
            last_name=last_name,
        )

        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, first_name, last_name, username, email, password):
        user = self.create_user(
            email=normalize_account_email(email),
            username=username,
            password=password,
            first_name=first_name,
            last_name=last_name,
        )
        user.is_admin = True
        user.is_active = True
        user.is_staff = True
        user.is_superuser = True
        user.save(using=self._db)
        return user


class Account(AbstractBaseUser, PermissionsMixin):
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    username = models.CharField(max_length=50, unique=True)
    email = models.EmailField(max_length=100, unique=True)
    search_text_normalized = models.CharField(max_length=255, default="", blank=True, db_index=True)
    phone_number = models.CharField(max_length=50, default="", null=True, blank=True)

    # credit

    credit = models.IntegerField(default=0)

    # required

    date_joined = models.DateTimeField(auto_now_add=True)
    last_login = models.DateTimeField(auto_now_add=True)
    is_admin = models.BooleanField(default=False)
    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=False)
    is_superuser = models.BooleanField(default=False)
    is_rider = models.BooleanField(default=False)
    is_commission = models.BooleanField(default=False)
    is_commissar = models.BooleanField(default=False)
    is_club_manager = models.BooleanField(default=False)
    is_trainer = models.BooleanField(default=False)

    club = models.ForeignKey(
        Club,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="managed_users",
    )
    trainer_clubs = models.ManyToManyField(
        Club,
        blank=True,
        related_name="trainers",
    )
    riders = models.ManyToManyField(
        "rider.Rider",
        through="AccountRiderLink",
        blank=True,
        related_name="linked_accounts",
    )

    # not required
    photo = models.ImageField(
        upload_to='images/users/', blank=True, null=True, default='images/users/blank-avatar-200x200.jpg')

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username', 'first_name', 'last_name']

    objects = MyAccountManager()

    class Meta:
        verbose_name = "Uživatel"
        verbose_name_plural = "Uživatelé"

    def __str__(self):
        return self.first_name + " " + self.last_name

    def _get_persisted_email(self):
        if not self.pk:
            return None
        return type(self).objects.filter(pk=self.pk).values_list("email", flat=True).first()

    def _get_persisted_username(self):
        if not self.pk:
            return None
        return type(self).objects.filter(pk=self.pk).values_list("username", flat=True).first()

    def clean(self):
        super().clean()
        normalized_email = normalize_account_email(self.email)
        previous_email = self._get_persisted_email()

        if not normalized_email:
            raise ValidationError({"email": _("Uživatel musí mít e-mailovou adresu.")})

        # Historical case-sensitive duplicates may already exist in DB.
        # Enforce case-insensitive uniqueness only for new records or email changes.
        should_validate_uniqueness = self.pk is None or previous_email != self.email
        if should_validate_uniqueness:
            duplicate_qs = type(self).objects.filter(email__iexact=normalized_email)
            if self.pk:
                duplicate_qs = duplicate_qs.exclude(pk=self.pk)
            if duplicate_qs.exists():
                raise ValidationError(
                    {"email": _("Uživatel s tímto e-mailem již existuje bez ohledu na velikost písmen.")}
                )

    def save(self, *args, **kwargs):
        previous_email = self._get_persisted_email()
        previous_username = self._get_persisted_username()
        if self.pk is None or previous_email != self.email:
            self.email = normalize_account_email(self.email)
        if self.username and "@" in self.username and (self.pk is None or previous_username != self.username):
            self.username = normalize_account_email(self.username)
        self.search_text_normalized = normalize_search_text(
            " ".join(
                part for part in [
                    self.email,
                    self.username,
                    self.first_name,
                    self.last_name,
                ] if part
            )
        )
        super().save(*args, **kwargs)

    @property
    def photo_url(self):
        try:
            return self.photo.url if self.photo else ""
        except (ValueError, OSError):
            return ""

    def has_perm(self, perm, obj=None):
        return self.is_superuser

    def has_module_perms(self, add_label):
        return self.is_superuser


class PendingActivationAccount(Account):
    class Meta:
        proxy = True
        verbose_name = "Čekající aktivace účtu"
        verbose_name_plural = "Čekající aktivace účtů"


class AccountActivationAuditLog(models.Model):
    class Action(models.TextChoices):
        SENT = "sent", "Odeslána aktivace"
        RESENT = "resent", "Znovu odeslána aktivace"
        ACTIVATED = "activated", "Účet aktivován"
        CLEANED_UP = "cleaned_up", "Neaktivní účet odstraněn"

    account = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="activation_audit_logs",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="performed_activation_audit_logs",
    )
    action = models.CharField(max_length=24, choices=Action.choices)
    source = models.CharField(max_length=64, default="system")
    email_snapshot = models.EmailField(max_length=100, blank=True, default="")
    note = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Audit aktivace účtu"
        verbose_name_plural = "Audit aktivací účtů"
        indexes = [
            models.Index(fields=["action", "created_at"], name="accounts_actaudit_action_date"),
            models.Index(fields=["email_snapshot", "created_at"], name="accounts_actaudit_email_date"),
        ]

    def __str__(self):
        return f"{self.get_action_display()} {self.email_snapshot or '-'}"


class AccountRiderLink(models.Model):
    account = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="rider_links",
    )
    rider = models.ForeignKey(
        "rider.Rider",
        on_delete=models.CASCADE,
        related_name="account_links",
    )
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Vazba uživatel-jezdec"
        verbose_name_plural = "Vazby uživatel-jezdec"
        ordering = ["account__last_name", "account__first_name", "rider__last_name", "rider__first_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["account", "rider"],
                name="unique_account_rider_link",
            )
        ]

    def __str__(self):
        return f"{self.account} -> {self.rider}"


class AvatarChangeRequest(models.Model):
    STATUS_PENDING = "pending"
    STATUS_APPROVED = "approved"
    STATUS_REJECTED = "rejected"
    STATUS_EXPIRED = "expired"
    STATUS_CHOICES = (
        (STATUS_PENDING, "Čeká na schválení"),
        (STATUS_APPROVED, "Schváleno"),
        (STATUS_REJECTED, "Zamítnuto"),
        (STATUS_EXPIRED, "Expirováno"),
    )

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="submitted_avatar_change_requests",
    )
    target_account = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="avatar_change_requests",
    )
    target_rider = models.ForeignKey(
        "rider.Rider",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="avatar_change_requests",
    )
    image = models.ImageField(upload_to="images/avatar-change-requests/")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True)
    review_note = models.CharField(max_length=255, blank=True, default="")
    created = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_avatar_change_requests",
    )

    class Meta:
        verbose_name = "Žádost o změnu avataru"
        verbose_name_plural = "Žádosti o změnu avataru"
        ordering = ["-created"]
        indexes = [
            models.Index(fields=["status", "-created"], name="avatar_req_status_created_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["target_account"],
                condition=models.Q(status="pending", target_account__isnull=False),
                name="unique_pending_avatar_request_per_account",
            ),
            models.UniqueConstraint(
                fields=["target_rider"],
                condition=models.Q(status="pending", target_rider__isnull=False),
                name="unique_pending_avatar_request_per_rider",
            ),
        ]

    def __str__(self):
        target = self.target_account or self.target_rider
        return f"{self.get_status_display()}: {target}"

    def clean(self):
        super().clean()
        has_account = bool(self.target_account_id)
        has_rider = bool(self.target_rider_id)
        if has_account == has_rider:
            raise ValidationError("Žádost musí cílit právě na jeden profil.")

    @property
    def target_label(self):
        if self.target_account_id:
            return str(self.target_account)
        if self.target_rider_id:
            return str(self.target_rider)
        return ""

    @property
    def image_url(self):
        try:
            return self.image.url if self.image else ""
        except (ValueError, OSError):
            return ""

    @classmethod
    def expiration_days(cls):
        return getattr(settings, "AVATAR_REQUEST_EXPIRATION_DAYS", 30)

    @classmethod
    def pending_cutoff(cls):
        return timezone.now() - timezone.timedelta(days=cls.expiration_days())

    @classmethod
    def expire_stale_requests(cls):
        stale_requests = list(
            cls.objects.filter(
                status=cls.STATUS_PENDING,
                created__lt=cls.pending_cutoff(),
            )
        )
        for stale_request in stale_requests:
            stale_request.expire()
        return len(stale_requests)

    @property
    def is_stale(self):
        return self.status == self.STATUS_PENDING and self.created < self.pending_cutoff()

    def _build_normalized_avatar(self):
        final_size = int(getattr(settings, "AVATAR_FINAL_IMAGE_SIZE", 512))
        output_quality = int(getattr(settings, "AVATAR_FINAL_IMAGE_QUALITY", 86))
        preferred_format = "WEBP" if features.check("webp") else "JPEG"
        extension = "webp" if preferred_format == "WEBP" else "jpg"
        original_truncated_setting = ImageFile.LOAD_TRUNCATED_IMAGES

        try:
            ImageFile.LOAD_TRUNCATED_IMAGES = True
            with self.image.open("rb") as image_file:
                image = Image.open(image_file)
                image.load()
                image = ImageOps.exif_transpose(image).convert("RGB")
                image = ImageOps.fit(
                    image,
                    (final_size, final_size),
                    method=Image.Resampling.LANCZOS,
                    centering=(0.5, 0.5),
                )
                output = BytesIO()
                try:
                    if preferred_format == "WEBP":
                        image.save(output, format="WEBP", quality=output_quality, method=6)
                    else:
                        image.save(output, format="JPEG", quality=90, optimize=True)
                except (OSError, KeyError):
                    output = BytesIO()
                    image.save(output, format="JPEG", quality=90, optimize=True)
                    preferred_format = "JPEG"
                    extension = "jpg"
        except FileNotFoundError as exc:
            raise ValidationError("Nahraný avatar nebyl na serveru nalezen.") from exc
        except UnidentifiedImageError as exc:
            raise ValidationError("Nahraný soubor není platný obrázek.") from exc
        except OSError as exc:
            raise ValidationError(f"Nahraný avatar se nepodařilo zpracovat: {exc}") from exc
        finally:
            ImageFile.LOAD_TRUNCATED_IMAGES = original_truncated_setting

        output.seek(0)
        if self.target_account_id:
            filename = f"account-avatar-{self.target_account_id}-{uuid.uuid4().hex[:12]}.{extension}"
        else:
            filename = f"rider-avatar-{self.target_rider_id}-{uuid.uuid4().hex[:12]}.{extension}"
        return filename, ContentFile(output.read())

    def _cleanup_request_image(self):
        if not self.image:
            return
        self.image.delete(save=False)
        self.image = ""

    def _finalize(self, *, status, reviewer=None, note=""):
        self.status = status
        self.reviewed_by = reviewer
        self.reviewed_at = timezone.now()
        self.review_note = note
        self._cleanup_request_image()
        self.save(update_fields=["status", "reviewed_by", "reviewed_at", "review_note", "image"])

    def approve(self, reviewer, note=""):
        filename, normalized_image = self._build_normalized_avatar()
        if self.target_account_id:
            self.target_account.photo.save(filename, normalized_image, save=False)
            self.target_account.save(update_fields=["photo"])
        elif self.target_rider_id:
            self.target_rider.photo.save(filename, normalized_image, save=False)
            self.target_rider.save(update_fields=["photo"])
        else:
            raise ValidationError("Žádost o avatar nemá cílový profil.")
        self._finalize(status=self.STATUS_APPROVED, reviewer=reviewer, note=note)

    def reject(self, reviewer, note=""):
        self._finalize(status=self.STATUS_REJECTED, reviewer=reviewer, note=note)

    def expire(self, note=""):
        self._finalize(status=self.STATUS_EXPIRED, reviewer=None, note=note or "Žádost expirovala bez schválení.")

    def review(self, action, reviewer, note=""):
        if action in {"approve", self.STATUS_APPROVED}:
            self.approve(reviewer, note=note)
            return self.STATUS_APPROVED
        if action in {"reject", self.STATUS_REJECTED}:
            self.reject(reviewer, note=note)
            return self.STATUS_REJECTED
        if action in {"expire", self.STATUS_EXPIRED}:
            self.expire(note=note)
            return self.STATUS_EXPIRED
        raise ValidationError("Neplatná akce moderace avataru.")


class PendingAvatarChangeRequest(AvatarChangeRequest):
    class Meta:
        proxy = True
        verbose_name = "Čekající avatar"
        verbose_name_plural = "Čekající avatary"

import logging
logger = logging.getLogger(__name__)

@receiver(pre_save, sender=Account)
def update_credit_before_save(sender, instance, **kwargs):
    if instance.pk:  # Only if the user already exists (not a new record)
        try:
            instance.credit = calculate_user_balance(instance.pk)
        except Exception as e:
            logger.error("Nepodařilo se přepočítat kredit pro uživatele pk=%s: %s", instance.pk, e)
            # Zachováme původní hodnotu kreditu z DB — nenulujeme


@receiver(pre_save, sender=Account)
def delete_old_account_photo_on_change(sender, instance, **kwargs):
    if not instance.pk:
        return

    try:
        old_photo = Account.objects.only("photo").get(pk=instance.pk).photo
    except Account.DoesNotExist:
        return

    new_photo = instance.photo
    old_name = getattr(old_photo, "name", "") or ""
    new_name = getattr(new_photo, "name", "") or ""

    if not old_name or old_name == new_name or old_name in DEFAULT_ACCOUNT_PHOTO_PATHS:
        return

    def delete_old_photo():
        try:
            old_photo.delete(save=False)
        except Exception:
            logger.exception(
                "Nepodařilo se smazat původní profilovou fotku uživatele pk=%s: %s",
                instance.pk,
                old_name,
            )

    transaction.on_commit(delete_old_photo)
