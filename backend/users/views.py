from .models import Node, Effects
from .serializers import NodeSerializer
from rest_framework import viewsets
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema


class NodeViewSet(viewsets.ModelViewSet):
    queryset = Node.objects.all()
    serializer_class = NodeSerializer
    http_method_names = ['get']

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
        return Response(serializer.data)

    @extend_schema(exclude=True)
    def list(self, request, *args, **kwargs):
        return Response({'detail': 'Method "GET" not allowed.'}, status=405)

