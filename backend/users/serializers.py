from rest_framework import serializers
from djoser.serializers import UserSerializer as DjoserUserSerializer
from .models import User, Team, Node



class NodeSerializer(serializers.ModelSerializer):
    clue = serializers.SerializerMethodField()
    
    class Meta:
        model = Node
        fields = ['id', 'data', 'clue', 'effects', 'score', 'bonus', 'created_at']

    def get_clue(self, obj):
        return ("_ " * len(obj.answer))[:-1]

class TeamMemberSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'email')

class TeamSerializer(serializers.ModelSerializer):
    members = TeamMemberSerializer(source='user_set', many=True, read_only=True)

    class Meta:
        model = Team
        fields = ('id', 'name', 'score', 'life', 'members')

class CustomUserSerializer(DjoserUserSerializer):
    team = TeamSerializer(read_only=True)

    class Meta(DjoserUserSerializer.Meta):
        fields = DjoserUserSerializer.Meta.fields + ('team',)
