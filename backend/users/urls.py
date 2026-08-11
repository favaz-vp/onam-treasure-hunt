from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import NodeViewSet
from .sse_views import TeamEventStreamView, TeamStreamTicketView


router = DefaultRouter()
router.register(r'nodes', NodeViewSet, basename='node')


urlpatterns = [
    path('teams/stream/', TeamEventStreamView.as_view(), name='team-event-stream'),
    path('teams/stream-ticket/', TeamStreamTicketView.as_view(), name='team-stream-ticket'),
] + router.urls
