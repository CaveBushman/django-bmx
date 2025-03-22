from django.urls import path
from . import views
from django.contrib.auth import views as auth_views

app_name = "accounts"

urlpatterns = [
    path('signup/', views.sign_up, name='signup'),
    path('signin/', views.sign_in, name='signin'),
    path('signout/', views.sign_out, name='signout'),
        # URL pro začátek procesu resetování hesla
    path('reset_password/', auth_views.PasswordResetView.as_view(), name='password_reset'),
    
    # URL pro potvrzení resetování hesla (odeslání e-mailu)
    path('reset_password_sent/', auth_views.PasswordResetDoneView.as_view(), name='password_reset_done'),
    
    # URL pro zadání nového hesla (po kliknutí na odkaz v e-mailu)
    path('reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(), name='password_reset_confirm'),
    
    # URL pro potvrzení, že heslo bylo úspěšně změněno
    path('reset_password_complete/', auth_views.PasswordResetCompleteView.as_view(), name='password_reset_complete'),
]