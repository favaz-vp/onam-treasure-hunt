from collections import defaultdict
from rest_framework import viewsets
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.decorators import action
from drf_spectacular.utils import extend_schema, OpenApiParameter
from .services import process_submit, target_attack
from .models import Node, Effects, Team, TeamNode, NodeStatus
from .serializers import (
    NodeSerializer,
    SubmitRequestSerializer,
    SubmitResponseSerializer,
    TargetAttackSerializer,
    TargetTeamsResponseSerializer,
    BasicTeamSerializer,
    MapGraphResponseSerializer,
    NodeCreateSerializer
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
    
    @extend_schema(request=NodeCreateSerializer, responses={201: NodeCreateSerializer})
    def create(self, request, *args, **kwargs):
        serializer = NodeCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=400)
        serializer.save()
        return Response(serializer.data, status=201)

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
    
    @action(detail=False, methods=['get'], url_path='v2/visited')
    def new_visited(self, request):
        team = request.user.team
        if not team:
            return Response({'detail': 'User is not part of any team.'}, status=400)

        start_node = team.head
        current_node = team.current_node
        current_team_node = TeamNode.objects.filter(team=team, node=current_node).last()
        if not start_node:
            return Response([])
        
        ancestor_team_nodes  = (
            current_team_node
            .get_ancestors(include_self=True)
            .select_related("node")
        )
        ancestor_nodes = [team_node.node for team_node in ancestor_team_nodes ]
        response = self.get_serializer(ancestor_nodes, many=True)
        return Response(response.data)
 
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


class MapViewSet(viewsets.ViewSet):
    """
    API endpoint that returns the complete cyclic graph map of nodes.
    Django MPTT represents the tree hierarchy, while alt_parent and alt_child connect cycles at junction nodes.
    """
    permission_classes = [AllowAny]
    http_method_names = ['get']

    @extend_schema(
        summary="Get Cyclic Graph Map",
        description=(
            "Returns all nodes and directed edges in the cyclic question graph. "
            "Edges include primary tree connections (from MPTT parent-child relationships) "
            "as well as alternative cyclic connections (from alt_child and alt_parent at junction nodes). "
            "Also includes team progress states (completed, in-progress, locked) if the user is in a team."
        ),
        responses={200: MapGraphResponseSerializer},
    )
    def list(self, request, *args, **kwargs):
        nodes = Node.objects.all().order_by('tree_id', 'lft')
        node_map = {n.id: n for n in nodes}

        # Build children map from MPTT parent relation
        children_map = defaultdict(list)
        for n in nodes:
            if n.parent_id:
                children_map[n.parent_id].append(n.id)

        # Team context
        user_team = getattr(request.user, 'team', None) if request.user.is_authenticated else None
        visited_node_ids = set()
        if user_team:
            visited_node_ids = set(
                TeamNode.objects.filter(team=user_team).values_list('node_id', flat=True)
            )

        # Build nodes payload
        nodes_payload = []
        for n in nodes:
            if not user_team:
                status = "unlocked"
            elif user_team.current_node_id and n.id == user_team.current_node_id:
                status = NodeStatus.IN_PROGRESS
            elif n.id in visited_node_ids:
                status = NodeStatus.COMPLETED
            else:
                status = NodeStatus.LOCKED

            nodes_payload.append({
                "id": n.id,
                "data": n.data,
                "clue": n.clue,
                "effects": n.effects,
                "score": n.score,
                "bonus": n.bonus,
                "attack": n.attack,
                "life": n.life,
                "is_nearest": n.is_nearest,
                "parent_id": n.parent_id,
                "alt_parent_id": n.alt_parent_id,
                "alt_child_id": n.alt_child_id,
                "children_ids": children_map.get(n.id, []),
                "level": getattr(n, 'level', 0),
                "status": status,
                "is_current": bool(user_team and user_team.current_node_id == n.id),
                "is_head": bool(user_team and user_team.head_id == n.id),
                "is_checkpoint": bool(user_team and user_team.last_checkpoint_id == n.id),
                "created_at": n.created_at,
            })

        # Build edges payload
        edges_payload = []
        seen_edges = set()

        # 1. Primary tree edges (parent -> child)
        for n in nodes:
            for child_id in children_map.get(n.id, []):
                if child_id in node_map:
                    edge_key = (n.id, child_id)
                    if edge_key not in seen_edges:
                        seen_edges.add(edge_key)
                        edges_payload.append({
                            "id": f"e-{n.id}-{child_id}",
                            "source": n.id,
                            "target": child_id,
                            "type": "primary",
                            "is_cycle": False,
                        })

        # 2. Alternative child edges (n -> alt_child)
        for n in nodes:
            if n.alt_child_id and n.alt_child_id in node_map:
                edge_key = (n.id, n.alt_child_id)
                if edge_key not in seen_edges:
                    seen_edges.add(edge_key)
                    edges_payload.append({
                        "id": f"e-{n.id}-{n.alt_child_id}-alt",
                        "source": n.id,
                        "target": n.alt_child_id,
                        "type": "alternative",
                        "is_cycle": True,
                    })

        # 3. Alternative parent edges (alt_parent -> n)
        for n in nodes:
            if n.alt_parent_id and n.alt_parent_id in node_map:
                edge_key = (n.alt_parent_id, n.id)
                if edge_key not in seen_edges:
                    seen_edges.add(edge_key)
                    edges_payload.append({
                        "id": f"e-{n.alt_parent_id}-{n.id}-alt",
                        "source": n.alt_parent_id,
                        "target": n.id,
                        "type": "alternative",
                        "is_cycle": True,
                    })

        # Team state
        team_state = None
        if user_team:
            team_state = {
                "id": user_team.id,
                "name": user_team.name,
                "score": user_team.score,
                "life": user_team.life,
                "attack": user_team.attack,
                "is_won": user_team.is_won,
                "current_node_id": user_team.current_node_id,
                "head_id": user_team.head_id,
                "last_checkpoint_id": user_team.last_checkpoint_id,
            }

        response_data = {
            "nodes": nodes_payload,
            "edges": edges_payload,
            "total_nodes": len(nodes_payload),
            "total_edges": len(edges_payload),
            "team_state": team_state,
        }

        serializer = MapGraphResponseSerializer(response_data)
        return Response(serializer.data)

