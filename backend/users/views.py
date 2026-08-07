from .models import Node, Effects, TeamNode
from .serializers import NodeSerializer
from rest_framework import viewsets
from rest_framework.response import Response
from rest_framework.decorators import action
from drf_spectacular.utils import extend_schema
from .services import process_submit
from .models import Node, Effects
from .serializers import NodeSerializer, SubmitRequestSerializer, SubmitResponseSerializer


class NodeViewSet(viewsets.ModelViewSet):
    queryset = Node.objects.all()
    serializer_class = NodeSerializer
    http_method_names = ['get', 'post']

    def retrieve(self, request, *args, **kwargs):

        team = request.user.team
        if not team:
            return Response({'detail': 'User is not part of any team.'}, status=400)
        
        node_id = kwargs.get('pk')
        try:
            node = Node.objects.get(pk=node_id)
        except Node.DoesNotExist:
            return Response({'detail': 'Node not found.'}, status=404)

        current_node = team.current_node
        if current_node:
            if current_node.next_node_id != node_id:
                return Response(
                    {"detail": "You can only access the next node in sequence."},
                    status=400,
                )

        if node.effects == Effects.LOCKED:
            return Response(
                {
                    "detail": "This node is locked. You need a key to unlock and view the question."
                },
                status=400,
            )

        serializer = self.get_serializer(node)
        # Record node visit for this team
        TeamNode.objects.get_or_create(team=team, node=node)
        return Response(serializer.data)

    @extend_schema(exclude=True)
    def list(self, request, *args, **kwargs):
        return Response({'detail': 'Method "GET" not allowed.'}, status=405)
    
    @extend_schema(exclude=True)
    def create(self, request, *args, **kwargs):
        return Response({'detail': 'Method "POST" not allowed.'}, status=405)

    @action(detail=True, methods=['post'], url_path='submit')
    @extend_schema(
        request=SubmitRequestSerializer,
        responses={
            200: SubmitResponseSerializer,
            400: SubmitResponseSerializer,
            404: SubmitResponseSerializer,
        },
    )
    def submit(self, request, pk):
        serializer_req = SubmitRequestSerializer(data=request.data)
        if not serializer_req.is_valid():
            return Response(serializer_req.errors, status=400)
        status_code, resp_serializer = process_submit(request.user, pk)
        return Response(resp_serializer.data, status=status_code)
