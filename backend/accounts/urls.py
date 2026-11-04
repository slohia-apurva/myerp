from django.urls import path

from accounts import views

urlpatterns = [
    path("session/", views.SessionView.as_view(), name="auth-session"),
    path("login/", views.PasswordView.as_view(), name="auth-login"),
    path("totp/setup/", views.TotpSetupView.as_view(), name="auth-totp-setup"),
    path("totp/verify/", views.TotpVerifyView.as_view(), name="auth-totp-verify"),
    path("logout/", views.LogoutView.as_view(), name="auth-logout"),
    path("password-setup/", views.PasswordSetupView.as_view(), name="auth-password-setup"),
]
