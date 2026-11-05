from django.urls import path

from accounts import views

urlpatterns = [
    path("session/", views.SessionView.as_view(), name="auth-session"),
    path("google/", views.GoogleSignInView.as_view(), name="auth-google"),
    path("logout/", views.SignOutView.as_view(), name="auth-logout"),
]
