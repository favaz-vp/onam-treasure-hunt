from django.urls import path
from .sse_views import TeamEventStreamView, TeamStreamTicketView

urlpatterns = [
    path('teams/stream/', TeamEventStreamView.as_view(), name='team-event-stream'),
    path('teams/stream-ticket/', TeamStreamTicketView.as_view(), name='team-stream-ticket'),
]
