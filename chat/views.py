from django.shortcuts import render
from django.views.generic import ListView
from .models import ChatLog

class ChatLogListView(ListView):
    model = ChatLog
    template_name = "chat/chatlog_list.html"
    context_object_name = "chatlogs"
    ordering = ["-created_at"]

# Create your views here.
