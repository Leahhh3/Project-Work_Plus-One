from django.urls import path

from . import views

urlpatterns = [
    path("", views.discover, name="discover"),
    path("login/", views.login_demo, name="login"),
    path("profile/setup/", views.profile_setup, name="profile_setup"),
    path("about/", views.about, name="about"),
    path("create/", views.create_post, name="create_post"),
    path("posts/<int:post_id>/", views.post_detail, name="post_detail"),
    path("posts/<int:post_id>/edit/", views.edit_post, name="edit_post"),
    path("posts/<int:post_id>/swipe/", views.swipe_post, name="swipe_post"),
    path("matches/", views.dashboard, name="dashboard"),
    path("chat/<int:match_id>/", views.chat, name="chat"),
    path("demo/switch/<str:username>/", views.switch_demo_user, name="switch_demo_user"),
]
