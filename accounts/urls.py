from django.urls import path
from . import views
from django.contrib.auth import views as auth_views
from django.urls import reverse_lazy

app_name = "accounts"

urlpatterns = [
    path('signup/', views.sign_up, name='signup'),
    path('signup/activation-sent/', views.activation_sent, name='activation_sent'),
    path('signup/resend-activation/', views.resend_activation_email, name='resend_activation'),
    path('activate/<uidb64>/<token>/', views.activate_account, name='activate'),
    path('login/', views.sign_in, name='login'),
    path('logout/', views.sign_out, name='logout'),
    path('ops/', views.ops_dashboard, name='ops_dashboard'),
    path('avatar-moderation/', views.avatar_moderation_dashboard, name='avatar-moderation'),
    path('reset_password/', views.password_reset_request, name='password_reset'),
    path(
        'reset_password_sent/',
        auth_views.PasswordResetDoneView.as_view(
            template_name='registration/password_reset_done.html',
        ),
        name='password_reset_done',
    ),
    path(
        'reset/<uidb64>/<token>/',
        auth_views.PasswordResetConfirmView.as_view(
            template_name='registration/password_reset_confirm.html',
            success_url=reverse_lazy('accounts:password_reset_complete'),
        ),
        name='password_reset_confirm',
    ),
    path(
        'reset_password_complete/',
        auth_views.PasswordResetCompleteView.as_view(
            template_name='registration/password_reset_complete.html',
        ),
        name='password_reset_complete',
    ),
]
