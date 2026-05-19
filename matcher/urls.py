from django.urls import path

from . import views

app_name = "matcher"

urlpatterns = [
    path("", views.discover, name="home"),
    path("discover/", views.discover, name="discover"),
    path("create/", views.create_post, name="create"),
    path("chat/<int:match_id>/", views.chat, name="chat"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("api/swipe/", views.swipe, name="swipe"),
    path("api/chat/<int:match_id>/send/", views.send_message, name="send_message"),
    path("api/match/<int:match_id>/agree/", views.agree_to_meet, name="agree_to_meet"),
]
