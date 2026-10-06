from django.db import models
from mptt.models import MPTTModel, TreeForeignKey


class Effects(models.TextChoices):
    JUNCTION = 'JUNCTION', 'Junction'
    UNLOCKED = 'UNLOCKED', 'Unlocked'


class Map(models.Model):
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class Node(MPTTModel):
    map = models.ForeignKey(Map, on_delete=models.CASCADE, null=True, blank=True, related_name='nodes')
    parent = TreeForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='child')
    alt_parent = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='alternative_child', default=None)
    data = models.TextField()
    answer = models.TextField(default="", blank=True)
    alt_answer = models.TextField(default="", blank=True)
    effects = models.CharField(default=Effects.UNLOCKED, max_length=20, choices=Effects.choices)
    score = models.IntegerField(default=10) # Junction nodes no score, handle manually when adding questions
    bonus = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    attack = models.IntegerField(default=0)
    life = models.IntegerField(default=0)
    clue = models.TextField(default="", blank=True, null=True)
    is_nearest = models.BooleanField(default=False)
    position = models.JSONField(default=dict, blank=True, null=True)
    
    def __str__(self):
        return f"{self.pk} - ({self.data})"


class GameSessionStatus(models.TextChoices):
    PENDING = 'PENDING', 'Pending'
    ACTIVE = 'ACTIVE', 'Active'
    PAUSED = 'PAUSED', 'Paused'
    COMPLETED = 'COMPLETED', 'Completed'


class GameSession(models.Model):
    name = models.CharField(max_length=150)
    map = models.ForeignKey(Map, on_delete=models.SET_NULL, null=True, blank=True, related_name='game_sessions')
    status = models.CharField(max_length=20, choices=GameSessionStatus.choices, default=GameSessionStatus.PENDING)
    is_active = models.BooleanField(default=False)
    start_time = models.DateTimeField(null=True, blank=True)
    end_time = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.status})"


class TeamNode(MPTTModel):
    team = models.ForeignKey('users.Team', on_delete=models.CASCADE, related_name='team_nodes')
    node = models.ForeignKey(Node, on_delete=models.CASCADE, related_name='team_nodes')
    parent = TreeForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='children')
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ('team', 'node', 'parent')
        ordering = ['created_at']

    def __str__(self):
        return f"{self.team.name} -> Node {self.node_id}"


class GameHistory(models.Model):
    team = models.ForeignKey('users.Team', on_delete=models.CASCADE, related_name='game_histories')
    node = models.ForeignKey(Node, on_delete=models.CASCADE, null=True, blank=True, related_name='game_histories')
    action = models.TextField(default="", blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "Game histories"
        ordering = ['-created_at']

    def __str__(self) -> str:
        return f"{self.team.name} - {self.action} - Q({self.node_id})"
