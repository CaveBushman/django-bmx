from django.urls import path

from . import views

app_name = "todo"

urlpatterns = [
    path("", views.task_list_view, name="task-list"),
]

