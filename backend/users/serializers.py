from rest_framework import serializers
from djoser.serializers import UserSerializer as DjoserUserSerializer
from .models import User, Team, Node, Effects, NodeStatus, TeamNode


class NodeSerializer(serializers.ModelSerializer):
    encoded_answer = serializers.SerializerMethodField()
    answers = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()

    class Meta:
        model = Node
        fields = ['id', 'data', 'clue', 'encoded_answer', 'answers', 'effects', 'score', 'bonus', 'created_at', 'status']

    def get_encoded_answer(self, obj) -> str:
        return " ".join("*" * len(word) for word in obj.answer.split())

    def get_answers(self, obj) -> list:
        answers = []
        if obj.effects == Effects.JUNCTION:
            answers = [
                {
                    "id": obj.next_node.id,
                    "answer": obj.answer,           
                },
                {
                    "id": obj.alt_next_node.id,
                    "answer": obj.alt_answer,           
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
        fields = ('id', 'name', 'score', 'life', 'attack', 'members')

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
        fields = ("id", "name", "score", "life", "attack")


class TargetTeamsResponseSerializer(serializers.Serializer):
    detail = serializers.CharField()
    data = BasicTeamSerializer(many=True)


class TargetAttackSerializer(serializers.Serializer):
    target_team = serializers.IntegerField()
    attack_value = serializers.IntegerField(min_value=1)


class StreamTicketSerializer(serializers.Serializer):
    ticket = serializers.CharField()
