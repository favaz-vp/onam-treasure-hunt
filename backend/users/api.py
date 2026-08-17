"""The game endpoints: reading nodes, answering them, and attacking teams.

Plain routes rather than a ViewSet. The DRF original was a ModelViewSet, but
only because that was the shortest way to hang six unrelated endpoints off one
prefix — list and create were both switched off, and retrieve was overridden
outright. Written out, the routes say what they are.

Each route is an async handler wrapping a synchronous body: the queries stay
ordinary blocking ORM code, and config.concurrency.run_db puts it on a worker
thread. See that module for why the handlers do not simply stay sync.
"""
from django_bolt import JSON, Router
from django_bolt.exceptions import BadRequest, MethodNotAllowed, NotFound

from config.concurrency import run_db
from config.security import DEFAULT_AUTH, DEFAULT_GUARDS

from .models import Effects, Node, Team, TeamNode
from .schemas import (
    DetailOut,
    NodeOut,
    TargetAttackIn,
    TargetTeamsOut,
    basic_team_out,
    node_out,
)
from .services import process_submit, target_attack

node_router = Router(
    prefix="/api/nodes", tags=["nodes"],
    auth=DEFAULT_AUTH, guards=DEFAULT_GUARDS,
)


def _require_team(request):
    team = request.user.team
    if not team:
        raise BadRequest(detail="User is not part of any team.")
    return team


# DRF's router registered the collection endpoints and then refused them, so
# clients saw 405 rather than 404. Kept, so anything relying on the difference
# keeps working.
@node_router.get("/", include_in_schema=False)
async def nodes_list():
    raise MethodNotAllowed(detail='Method "GET" not allowed.')


@node_router.post("/", include_in_schema=False)
async def nodes_create():
    raise MethodNotAllowed(detail='Method "POST" not allowed.')


def _visited(request, path):
    team = _require_team(request)

    visited_team_nodes = TeamNode.objects.filter(team=team)
    team_node_map = {tn.node_id: tn.created_at for tn in visited_team_nodes}
    visited_node_ids = set(team_node_map.keys())

    if not visited_node_ids:
        return []

    visited_nodes_by_id = {
        node.id: node
        for node in Node.objects.filter(id__in=visited_node_ids).select_related(
            'next_node', 'alt_next_node'
        )
    }

    if path:
        try:
            path_id_int = int(path)
        except ValueError:
            raise BadRequest(detail="Invalid path parameter.") from None

        if path_id_int not in visited_nodes_by_id:
            raise NotFound(detail="Path node not found in visited nodes.")

        start_node = visited_nodes_by_id[path_id_int]
    else:
        start_node = visited_nodes_by_id.get(team.head_id) if team.head_id else None
        if not start_node:
            first_tn = visited_team_nodes.order_by('created_at').first()
            start_node = visited_nodes_by_id.get(first_tn.node_id) if first_tn else None

    if not start_node:
        return []

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

    current_node_created_at = (
        team_node_map.get(team.current_node_id) if team.current_node_id else None
    )

    return [
        node_out(node, team, team_node_map, current_node_created_at)
        for node in selected_nodes
    ]


@node_router.get("/visited/", summary="Visited nodes")
async def visited(request, path: str | None = None) -> list[NodeOut]:
    """Visited nodes from the head (or a given path node), following next_node
    up to and including the next junction."""
    return await run_db(_visited, request, path)


def _current_node(request):
    team = _require_team(request)

    if not team.current_node:
        raise BadRequest(detail="Game not started yet.")

    return DetailOut(
        detail="Details fetched successfully",
        data=node_out(team.current_node, team),
    )


@node_router.get("/current/", summary="Current node")
async def current_node(request) -> DetailOut:
    """Get current node details"""
    return await run_db(_current_node, request)


def _target_teams(request):
    team = _require_team(request)

    targets = Team.objects.exclude(id=team.id).filter(life__gt=0)
    return TargetTeamsOut(
        detail="Details fetched successfully",
        data=[basic_team_out(t) for t in targets],
    )


@node_router.get(
    "/target-teams/",
    summary="Get Target Teams",
    description=(
        "Return a list of teams that can be attacked by the user's team. "
        "The list excludes the user's own team and any teams with no lives left."
    ),
)
async def target_teams(request) -> TargetTeamsOut:
    return await run_db(_target_teams, request)


def _attack(request, payload):
    return target_attack(
        attacking_team=_require_team(request),
        target_team_id=payload.target_team,
        attack_value=payload.attack_value,
    )


@node_router.post(
    "/target-attack/",
    summary="Target Attack",
    description=(
        "Attack another team by deducting their life based on the attack value. "
        "The attacking team must have enough attack points to perform the attack."
    ),
    response_model=DetailOut,
    validate_response=False,  # the 400 bodies are not DetailOut
)
async def attack(request, payload: TargetAttackIn):
    # DRF rejected this with 400 via the serializer's min_value; Bolt would
    # answer a struct-level constraint with 422, so the check lives here.
    if payload.attack_value < 1:
        return JSON(
            {"attack_value": ["Ensure this value is greater than or equal to 1."]},
            status_code=400,
        )

    status_code, body = await run_db(_attack, request, payload)
    return JSON(body, status_code=status_code)


def _retrieve(request, pk):
    team = _require_team(request)

    try:
        node = Node.objects.get(pk=pk)
    except Node.DoesNotExist:
        raise NotFound(detail="Node not found.") from None

    current = team.current_node
    if current and current.next_node_id != pk:
        raise BadRequest(detail="You can only access the next node in sequence.")

    # Record node visit for this team
    TeamNode.objects.get_or_create(team=team, node=node)
    return node_out(node, team)


@node_router.get("/{pk}/", summary="Retrieve a node")
async def retrieve(request, pk: int) -> NodeOut:
    """Hand back a node, but only the one the team is actually up to.

    Reading it counts as visiting it, which is what later puts it in the
    visited listing.
    """
    return await run_db(_retrieve, request, pk)


@node_router.post(
    "/{pk}/submit/",
    summary="Submit an answer",
    response_model=DetailOut,
    validate_response=False,  # status varies, and JSON() carries it
)
async def submit(request, pk: int):
    status_code, body = await run_db(lambda: process_submit(request.user, pk))
    return JSON(body, status_code=status_code)
