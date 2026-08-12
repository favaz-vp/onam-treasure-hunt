from django.contrib import admin
from .models import User, Team, Node, TeamNode, GameHistory
from .sse import publish


class UserAdmin(admin.ModelAdmin):
    list_display = ('email', 'team', 'is_captain', 'is_staff', 'is_superuser')
    list_filter = ('is_staff', 'is_superuser', 'is_captain')
    search_fields = ('email',)
    ordering = ('email',)
    filter_horizontal = ()

class UserInline(admin.TabularInline):
    model = User
    extra = 0
    fields = ('email', 'is_captain', 'is_staff')
    show_change_link = True


class TeamAdmin(admin.ModelAdmin):
    list_display = ('name', 'life', 'score', 'attack', 'created_at')
    search_fields = ('name',)
    ordering = ('name',)
    inlines = (UserInline,)

    # Team edits here bypass services.py, so live-connected clients would
    # otherwise never learn about admin-triggered life/score/attack changes
    # (e.g. kicking off the game by raising life above 0). Push the same
    # team_update event the attack flow uses.
    STREAMED_FIELDS = {'life', 'score', 'attack'}

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)

        if change and self.STREAMED_FIELDS.intersection(form.changed_data):
            publish(obj.id, "team_update", {
                "life": obj.life,
                "score": obj.score,
                "attack": obj.attack,
                "detail": "Team stats updated by game master.",
            })

class NodeAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "data",
        "next_node_id",
        "alt_next_node_id",
        "effects",
        "clue",
        "score",
        "bonus",
        "life",
        "attack",
        "created_at",
    )
    search_fields = ('data',)
    ordering = ('created_at',)

class TeamNodeAdmin(admin.ModelAdmin):
    list_display = ('team', 'node', 'created_at')
    search_fields = ('team__name', 'node__data')
    ordering = ('created_at',)

class GameHistoryAdmin(admin.ModelAdmin):
    list_display = ('team', 'node', 'action', 'created_at')
    search_fields = ('team__name', 'node__data')
    ordering = ('created_at',)

admin.site.register(User, UserAdmin)
admin.site.register(Team, TeamAdmin)
admin.site.register(Node, NodeAdmin)
admin.site.register(TeamNode, TeamNodeAdmin)
admin.site.register(GameHistory, GameHistoryAdmin)
