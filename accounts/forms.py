"""Formuláře pro registraci a správu projektového modelu ``Account``."""

from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import Account


class SignUpForm(UserCreationForm):
    email = forms.EmailField(required=True)
    first_name = forms.CharField(max_length=30, required=True)
    last_name = forms.CharField(max_length=30, required=True)

    class Meta:
        model = Account
        fields = ['username', 'first_name', 'last_name', 'email']
