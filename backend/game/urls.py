from rest_framework.routers import DefaultRouter
from .views import NodeViewSet, MapViewSet

router = DefaultRouter()
router.register(r'nodes', NodeViewSet, basename='node')
router.register(r'maps', MapViewSet, basename='map')

urlpatterns = router.urls
