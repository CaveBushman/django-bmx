from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from event.credit import calculate_user_balance
from django.db.models.signals import pre_save
from django.dispatch import receiver


# Create your models here.

class MyAccountManager(BaseUserManager):
    def create_user(self, first_name, last_name, username, email, password=None):
        if not email:
            raise ValueError('Uživatel musí mít e-mailovu adresu.')

        if not username:
            raise ValueError('Uživatel musí mít uživatelské jméno')
        email = self.normalize_email(email)
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
            email=self.normalize_email(email),
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

    def has_perm(self, perm, obj=None):
        return self.is_superuser

    def has_module_perms(self, add_label):
        return self.is_superuser

@receiver(pre_save, sender=Account)
def update_credit_before_save(sender, instance, **kwargs):
    if instance.pk:  # Only if the user already exists (not a new record)
        try:
            instance.credit = calculate_user_balance(instance.pk)
        except Exception as e:
            # Log error or handle the exception as needed
            instance.credit = 0  # Default to 0 in case of error