from rest_framework import serializers
from djoser.serializers import UserSerializer as DjoserUserSerializer
from .models import User, Team, Node, Effects, NodeStatus, TeamNode

class NodeCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Node
        fields = [
            "id",
            "data",
            "clue",
            "answer",
            "alt_answer",
            "effects",
            "score",
            "bonus",
            "life",
            "attack",
            "parent",
            "alt_parent",
            "is_nearest",
            "position",
        ]
        read_only_fields = ("id",)

class NodeUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Node
        fields = [
            "id",
            "data",
            "clue",
            "answer",
            "alt_answer",
            "effects",
            "score",
            "bonus",
            "life",
            "attack",
            "is_nearest",
            "position",
        ]
        read_only_fields = ("id",)

class NodeSerializer(serializers.ModelSerializer):
    encoded_answer = serializers.SerializerMethodField()
    answers = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()

    class Meta:
        model = Node
        fields = [
            "id",
            "data",
            "clue",
            "encoded_answer",
            "answers",
            "effects",
            "score",
            "bonus",
            "life",
            "attack",
            "position",
            "created_at",
            "status",
        ]

    def get_encoded_answer(self, obj) -> str:
        return " ".join("*" * len(word) for word in obj.answer.split())

    def get_answers(self, obj) -> list:
        answers = []
        if obj.effects == Effects.JUNCTION:
            direct_child = obj.get_children().first()
            alt_child = obj.alternative_child.first()
            answers = [
                {
                    "id": direct_child.id,
                    "answer": obj.answer,
                    "is_nearest": direct_child.is_nearest,
                },
                {
                    "id": getattr(alt_child, 'id', None),
                    "answer": obj.alt_answer,
                    "is_nearest": getattr(alt_child, 'is_nearest', False),
                },
            ]
        return answers

    def get_status(self, obj) -> str:
        team = self.context.get('team')
        if not team:
            request = self.context.get('request')
            if request and hasattr(request, 'user') and getattr(request.user, 'is_authenticated', False):
                team = getattr(request.user, 'team', None)

        if not team:
            return NodeStatus.COMPLETED

        if team.current_node_id and obj.id == team.current_node_id:
            return NodeStatus.IN_PROGRESS

        team_node_map = self.context.get('team_node_map')
        current_node_created_at = self.context.get('current_node_created_at')

        if team_node_map is None:
            tn = TeamNode.objects.filter(team=team, node=obj).first()
            if not tn:
                return NodeStatus.COMPLETED
            obj_created_at = tn.created_at

            if team.current_node_id:
                cur_tn = TeamNode.objects.filter(team=team, node_id=team.current_node_id).first()
                if cur_tn and obj_created_at > cur_tn.created_at:
                    return NodeStatus.LOCKED
            return NodeStatus.COMPLETED
        else:
            obj_created_at = team_node_map.get(obj.id)
            if obj_created_at and current_node_created_at and obj_created_at > current_node_created_at:
                return NodeStatus.LOCKED
            return NodeStatus.COMPLETED


class TeamMemberSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'email')

class TeamSerializer(serializers.ModelSerializer):
    members = TeamMemberSerializer(source='user_set', many=True, read_only=True)

    class Meta:
        model = Team
        fields = ('id', 'name', 'score', 'life', 'attack', 'is_won', 'members')

class CustomUserSerializer(DjoserUserSerializer):
    team = TeamSerializer(read_only=True)

    class Meta(DjoserUserSerializer.Meta):
        fields = DjoserUserSerializer.Meta.fields + ('team',)

class SubmitRequestSerializer(serializers.Serializer):
    # No body required
    pass

class SubmitResponseSerializer(serializers.Serializer):
    detail = serializers.CharField()
    data = serializers.JSONField(required=False)


class BasicTeamSerializer(serializers.ModelSerializer):
    class Meta:
        model = Team
        fields = ("id", "name", "score", "life", "attack", "is_won")


class TargetTeamsResponseSerializer(serializers.Serializer):
    detail = serializers.CharField()
    data = BasicTeamSerializer(many=True)


class TargetAttackSerializer(serializers.Serializer):
    target_team = serializers.IntegerField()
    attack_value = serializers.IntegerField(min_value=1)


class StreamTicketSerializer(serializers.Serializer):
    ticket = serializers.CharField()


class MapNodeSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    data = serializers.CharField()
    answer = serializers.CharField()
    alt_answer = serializers.CharField()
    clue = serializers.CharField(allow_blank=True, allow_null=True, required=False)
    effects = serializers.CharField()
    score = serializers.IntegerField()
    bonus = serializers.IntegerField()
    attack = serializers.IntegerField()
    life = serializers.IntegerField()
    is_nearest = serializers.BooleanField()
    position = serializers.JSONField(required=False, allow_null=True)
    parent_id = serializers.IntegerField(allow_null=True)
    alt_parent_id = serializers.IntegerField(allow_null=True)
    alt_child_id = serializers.IntegerField(allow_null=True)
    children_ids = serializers.ListField(child=serializers.IntegerField())
    level = serializers.IntegerField()
    status = serializers.CharField()
    is_current = serializers.BooleanField()
    is_head = serializers.BooleanField()
    is_checkpoint = serializers.BooleanField()
    created_at = serializers.DateTimeField()


class MapEdgeSerializer(serializers.Serializer):
    id = serializers.CharField()
    source = serializers.IntegerField()
    target = serializers.IntegerField()
    type = serializers.CharField()
    is_cycle = serializers.BooleanField()


class MapTeamStateSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    score = serializers.IntegerField()
    life = serializers.IntegerField()
    attack = serializers.IntegerField()
    is_won = serializers.BooleanField()
    current_node_id = serializers.IntegerField(allow_null=True)
    head_id = serializers.IntegerField(allow_null=True)
    last_checkpoint_id = serializers.IntegerField(allow_null=True)


class MapSkeletonNodeSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    position = serializers.JSONField(required=False, allow_null=True)
    effects = serializers.CharField()

class MapSkeletonResponseSerializer(serializers.Serializer):
    nodes = MapSkeletonNodeSerializer(many=True)
    edges = MapEdgeSerializer(many=True)
    total_nodes = serializers.IntegerField()
    total_edges = serializers.IntegerField()


class MapGraphResponseSerializer(serializers.Serializer):
    nodes = MapNodeSerializer(many=True)
    edges = MapEdgeSerializer(many=True)
    total_nodes = serializers.IntegerField()
    total_edges = serializers.IntegerField()
    team_state = MapTeamStateSerializer(allow_null=True)


class EstablishRelationRequestSerializer(serializers.Serializer):
    parent_id = serializers.IntegerField(required=True)
    child_id = serializers.IntegerField(required=True)

    def validate(self, attrs):
        parent_id = attrs.get('parent_id')
        child_id = attrs.get('child_id')

        try:
            attrs['parent'] = Node.objects.get(pk=parent_id)
        except Node.DoesNotExist:
            raise serializers.ValidationError({'parent_id': f'Parent node with id {parent_id} does not exist.'})

        try:
            attrs['child'] = Node.objects.get(pk=child_id)
        except Node.DoesNotExist:
            raise serializers.ValidationError({'child_id': f'Child node with id {child_id} does not exist.'})

        return attrs

class EstablishRelationResponseSerializer(serializers.Serializer):
    detail = serializers.CharField()
    relation_type = serializers.ChoiceField(choices=['parent', 'alt_parent'])
    parent_id = serializers.IntegerField()
    child_id = serializers.IntegerField()


class RemoveRelationRequestSerializer(serializers.Serializer):
    node1_id = serializers.IntegerField(required=False)
    node2_id = serializers.IntegerField(required=False)

    def validate(self, attrs):
        node1_id = attrs.get('node1_id') or self.initial_data.get('parent_id') or self.initial_data.get('node1')
        node2_id = attrs.get('node2_id') or self.initial_data.get('child_id') or self.initial_data.get('node2')

        if not node1_id or not node2_id:
            raise serializers.ValidationError("Both node1_id and node2_id are required.")

        try:
            attrs['node1'] = Node.objects.get(pk=node1_id)
        except Node.DoesNotExist:
            raise serializers.ValidationError({'node1_id': f'Node with id {node1_id} does not exist.'})

        try:
            attrs['node2'] = Node.objects.get(pk=node2_id)
        except Node.DoesNotExist:
            raise serializers.ValidationError({'node2_id': f'Node with id {node2_id} does not exist.'})

        return attrs


class RemoveRelationResponseSerializer(serializers.Serializer):
    detail = serializers.CharField()
    removed_relations = serializers.ListField(child=serializers.CharField())
    node1_id = serializers.IntegerField()
    node2_id = serializers.IntegerField()

