from .models import Node, Effects, TeamNode
from .serializers import NodeSerializer
from rest_framework import viewsets
from rest_framework.response import Response
from rest_framework.decorators import action
from drf_spectacular.utils import extend_schema, OpenApiParameter
from .services import process_submit, target_attack
from .models import Node, Effects, Team
from .serializers import (
    NodeSerializer,
    SubmitRequestSerializer,
    SubmitResponseSerializer,
    TargetAttackSerializer,
    TargetTeamsResponseSerializer,
    BasicTeamSerializer,
)

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

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name='path',
                type=int,
                location=OpenApiParameter.QUERY,
                description='ID of a node to start traversal from',
                required=False,
            ),
        ],
        responses={200: NodeSerializer(many=True)},
    )
    @action(detail=False, methods=['get'], url_path='visited')
    def visited(self, request):
        """Return visited nodes starting from head (or passed path node), traversing next_node up to the next junction."""
        from .models import Effects
        team = request.user.team
        if not team:
            return Response({'detail': 'User is not part of any team.'}, status=400)

        visited_team_nodes = TeamNode.objects.filter(team=team)
        team_node_map = {tn.node_id: tn.created_at for tn in visited_team_nodes}
        visited_node_ids = set(team_node_map.keys())

        if not visited_node_ids:
            return Response([])

        visited_nodes_by_id = {
            node.id: node
            for node in Node.objects.filter(id__in=visited_node_ids).select_related('next_node', 'alt_next_node')
        }

        path_id = request.query_params.get('path')
        if path_id:
            try:
                path_id_int = int(path_id)
            except ValueError:
                return Response({'detail': 'Invalid path parameter.'}, status=400)

            if path_id_int not in visited_nodes_by_id:
                return Response({'detail': 'Path node not found in visited nodes.'}, status=404)

            start_node = visited_nodes_by_id[path_id_int]
        else:
            start_node = visited_nodes_by_id.get(team.head_id) if team.head_id else None
            if not start_node:
                first_tn = visited_team_nodes.order_by('created_at').first()
                start_node = visited_nodes_by_id.get(first_tn.node_id) if first_tn else None

        if not start_node:
            return Response([])

        selected_nodes = []
        visited_in_loop = set()
        current = start_node

        while current and current.id not in visited_in_loop:
            selected_nodes.append(current)
            visited_in_loop.add(current.id)

            if current.effects == Effects.JUNCTION:
                break

            if current.next_node_id and current.next_node_id in visited_nodes_by_id:
                current = visited_nodes_by_id[current.next_node_id]
            else:
                break

        current_node_created_at = team_node_map.get(team.current_node_id) if team.current_node_id else None

        serializer = self.get_serializer(
            selected_nodes,
            many=True,
            context={
                'request': request,
                'team': team,
                'team_node_map': team_node_map,
                'current_node_created_at': current_node_created_at,
            }
        )
        return Response(serializer.data)


    @extend_schema(
        summary="Get Target Teams",
        description=(
            "Return a list of teams that can be attacked by the user's team. "
            "The list excludes the user's own team and any teams with no lives left."
        ),
        responses={
            200: TargetTeamsResponseSerializer,
            400: SubmitResponseSerializer,
        },
    )
    @action(detail=False, methods=["get"], url_path="target-teams")
    def get_target_teams(self, request):
        """Return a list of teams that can be attacked by the user's team."""
        user_team = request.user.team
        if not user_team:
            return Response({'detail': 'User is not part of any team.'}, status=400)

        target_teams = Team.objects.exclude(id=user_team.id).filter(life__gt=0)
        serializer = BasicTeamSerializer(target_teams, many=True)
        return Response(
            {"detail": "Details fetched successfully", "data": serializer.data}
        )

    @extend_schema(
        summary="Target Attack",
        description=(
            "Attack another team by deducting their life based on the attack value. "
            "The attacking team must have enough attack points to perform the attack."
        ),
        request=TargetAttackSerializer,
        responses={
            200: SubmitResponseSerializer,
            400: SubmitResponseSerializer,
        },
    )
    @action(detail=False, methods=['post'], url_path='target-attack')
    def target_attack(self, request):
        """ Attack another team by deducting their life based on the attack value. 
        The attacking team must have enough attack points to perform the attack. """

        serializer = TargetAttackSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        status_code, serializer = target_attack(
            attacking_team=request.user.team,
            target_team_id=serializer.validated_data["target_team"],
            attack_value=serializer.validated_data["attack_value"],
        )

        return Response(
            serializer.data,
            status=status_code,
        )

    @action(detail=False, methods=['get'], url_path='current')
    def get_current_node(self, request):
        """ Get current node details"""
        user_team = request.user.team
        if not user_team:
            return Response({'detail': 'User is not part of any team.'}, status=400)

        current_node = user_team.current_node
        if current_node:
            serializer = self.get_serializer(current_node)
            return Response(
                {"detail": "Details fetched successfully", "data": serializer.data}
            )
        else:
            return Response({"detail": "Game not started yet."}, status=400)
