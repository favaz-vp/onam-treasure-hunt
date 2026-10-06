from django.contrib import admin
from django.template.response import TemplateResponse
from django.urls import path
from .models import Map, Node, GameSession, TeamNode, GameHistory
from users.node_graph import render_node_graph_svg


class NodeInline(admin.TabularInline):
    model = Node
    extra = 0
    fields = ('id', 'data', 'answer', 'score', 'effects', 'parent', 'alt_parent')
    readonly_fields = ('id',)
    show_change_link = True


@admin.register(Map)
class MapAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'is_active', 'nodes_count', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('name', 'description')
    inlines = (NodeInline,)

    def nodes_count(self, obj):
        return obj.nodes.count()
    nodes_count.short_description = "Total Nodes"


@admin.register(Node)
class NodeAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "map",
        "data",
        "effects",
        "parent",
        "alt_parent",
        "clue",
        "score",
        "bonus",
        "life",
        "attack",
        "answer",
        "position",
    )
    list_filter = ("map", "effects")
    search_fields = ('data', 'answer', 'clue')
    ordering = ('created_at',)
    change_list_template = "admin/users/node/change_list.html"

    def get_urls(self):
        urls = [
            path('graph/', self.admin_site.admin_view(self.graph_view), name='game_node_graph'),
        ]
        return urls + super().get_urls()

    def graph_view(self, request):
        svg, width, height = render_node_graph_svg(self.get_queryset(request))
        context = {
            **self.admin_site.each_context(request),
            'title': 'Node graph',
            'svg': svg,
            'svg_width': width,
            'svg_height': height,
            'opts': self.model._meta,
        }
        return TemplateResponse(request, 'admin/users/node/graph.html', context)


@admin.register(GameSession)
class GameSessionAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'map', 'status', 'is_active', 'start_time', 'end_time', 'created_at')
    list_filter = ('status', 'is_active', 'map')
    list_editable = ('status', 'is_active')
    search_fields = ('name',)
    ordering = ('-created_at',)


@admin.register(TeamNode)
class TeamNodeAdmin(admin.ModelAdmin):
    list_display = ('team', 'node', 'created_at')
    list_filter = ('team',)
    search_fields = ('team__name', 'node__data')
    ordering = ('created_at',)


@admin.register(GameHistory)
class GameHistoryAdmin(admin.ModelAdmin):
    list_display = ('team', 'node', 'action', 'created_at')
    list_filter = ('team',)
    search_fields = ('team__name', 'node__data', 'action')
    ordering = ('-created_at',)
