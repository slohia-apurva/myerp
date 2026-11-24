from django.urls import path

from accounts import list_columns, users_api

urlpatterns = [
    path("users/", users_api.UserListView.as_view(), name="users"),
    path("users/<int:pk>/", users_api.UserDetailView.as_view(), name="user"),
    path("users/<int:pk>/signature/", users_api.SignatureView.as_view(), name="user-signature"),
    path("my-columns/<str:key>/", list_columns.ListColumnsView.as_view(), name="my-columns"),
    path("roles/", users_api.RoleListView.as_view(), name="roles"),
    path("roles/<int:pk>/", users_api.RoleDetailView.as_view(), name="role"),
]
