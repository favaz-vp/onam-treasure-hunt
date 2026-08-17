"""The game endpoints.

The DRF originals had no tests, so these are new. They exist because the port
rewrote the whole request path — routing, parameter binding, serialisation and
the sync/async boundary — while the rules in services.py stayed put, and the
only way to show the rules still behave is to drive them through the new path.
"""
from django.contrib.auth import get_user_model
from django.test import TransactionTestCase

from config.api import api
from django_bolt.testing import TestClient

from .models import Effects, Node, Team, TeamNode

User = get_user_model()


class GameTestCase(TransactionTestCase):
    """A three-node loop: start -> second -> junction, junction -> start.

    Small, but it covers every branch the endpoints care about — an ordinary
    step, a junction (which is also a checkpoint), and the wrap back to head
    that wins the game.
    """

    def setUp(self):
        self.client = self.enterContext(TestClient(api))

        self.start = Node.objects.create(data="start", answer="alpha", score=10)
        self.second = Node.objects.create(data="second", answer="beta", score=20)
        self.junction = Node.objects.create(
            data="junction", answer="left", alt_answer="right",
            effects=Effects.JUNCTION, score=0,
        )
        self.start.next_node = self.second
        self.start.save()
        self.second.next_node = self.junction
        self.second.save()
        self.junction.next_node = self.start
        self.junction.alt_next_node = self.second
        self.junction.save()

        self.user = User.objects.create_user(
            email="player@example.com", password="Password123!"
        )
        self.team = self.user.team
        self.other_team = Team.objects.exclude(pk=self.team.pk).first()

        response = self.client.post(
            "/api/auth/jwt/create/",
            json={"email": "player@example.com", "password": "Password123!"},
        )
        self.headers = {"Authorization": f"Bearer {response.json()['access']}"}

    def get(self, url, **kwargs):
        return self.client.get(url, headers=self.headers, **kwargs)

    def post(self, url, **kwargs):
        return self.client.post(url, headers=self.headers, **kwargs)

    def start_game(self):
        return self.post(f"/api/nodes/{self.start.id}/submit/")

    def refresh_team(self):
        self.team.refresh_from_db()
        return self.team


class CollectionMethodTests(GameTestCase):
    def test_listing_and_creating_nodes_stay_refused(self):
        self.assertEqual(self.get("/api/nodes/").status_code, 405)
        self.assertEqual(self.post("/api/nodes/").status_code, 405)


class SubmitTests(GameTestCase):
    def test_first_submit_starts_the_game(self):
        response = self.start_game()

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["detail"], "Game started successfully.")
        self.assertEqual(body["data"]["id"], self.start.id)

        team = self.refresh_team()
        self.assertEqual(team.current_node_id, self.start.id)
        self.assertEqual(team.head_id, self.start.id)
        self.assertEqual(team.last_checkpoint_id, self.start.id)

    def test_the_game_cannot_start_on_a_junction(self):
        response = self.post(f"/api/nodes/{self.junction.id}/submit/")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json(), {"detail": "You cannot start with a junction node."}
        )

    def test_a_correct_answer_advances_and_scores(self):
        self.start_game()

        response = self.post(f"/api/nodes/{self.second.id}/submit/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["detail"], "Correct answer")
        team = self.refresh_team()
        self.assertEqual(team.current_node_id, self.second.id)
        # Only the node just answered scores — starting the game places the
        # head node without awarding it.
        self.assertEqual(team.score, self.second.score)

    def test_a_wrong_answer_costs_a_life_and_rewinds(self):
        self.start_game()
        life_before = self.refresh_team().life

        response = self.post(f"/api/nodes/{self.junction.id}/submit/")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"detail": "Wrong answer"})
        team = self.refresh_team()
        self.assertEqual(team.life, life_before - 1)
        self.assertEqual(team.current_node_id, team.last_checkpoint_id)

    def test_resubmitting_the_current_node_is_refused(self):
        self.start_game()

        response = self.start_game()

        self.assertEqual(response.status_code, 400)
        self.assertIn("already submitted", response.json()["detail"])

    def test_a_node_scores_only_the_first_time(self):
        self.start_game()
        self.post(f"/api/nodes/{self.second.id}/submit/")
        self.post(f"/api/nodes/{self.junction.id}/submit/")
        # The junction's alt branch leads back to `second`, already visited.
        score_before = self.refresh_team().score

        response = self.post(f"/api/nodes/{self.second.id}/submit/")

        self.assertEqual(response.json()["data"]["score"], 0)
        self.assertEqual(self.refresh_team().score, score_before)

    def test_reaching_the_head_again_wins(self):
        self.start_game()
        self.post(f"/api/nodes/{self.second.id}/submit/")
        self.post(f"/api/nodes/{self.junction.id}/submit/")

        response = self.post(f"/api/nodes/{self.start.id}/submit/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["detail"], "You Win!")
        self.assertTrue(self.refresh_team().is_won)

    def test_a_dead_team_cannot_submit(self):
        self.team.life = 0
        self.team.save(update_fields=["life"])

        response = self.start_game()

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json(),
            {"detail": "Game Over! Your team has no lives left."},
        )

    def test_a_junction_becomes_the_checkpoint(self):
        self.start_game()
        self.post(f"/api/nodes/{self.second.id}/submit/")
        self.post(f"/api/nodes/{self.junction.id}/submit/")

        self.assertEqual(self.refresh_team().last_checkpoint_id, self.junction.id)

    def test_submitting_requires_a_token(self):
        response = self.client.post(f"/api/nodes/{self.start.id}/submit/")

        self.assertEqual(response.status_code, 401)


class RetrieveTests(GameTestCase):
    def test_a_node_can_be_read_before_the_game_starts(self):
        response = self.get(f"/api/nodes/{self.start.id}/")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["id"], self.start.id)
        # The answer is only ever sent masked, one star per letter.
        self.assertEqual(body["encoded_answer"], "*****")
        self.assertNotIn("answer", body)

    def test_reading_a_node_records_the_visit(self):
        self.get(f"/api/nodes/{self.start.id}/")

        self.assertTrue(
            TeamNode.objects.filter(team=self.team, node=self.start).exists()
        )

    def test_only_the_next_node_in_sequence_is_readable(self):
        self.start_game()

        response = self.get(f"/api/nodes/{self.junction.id}/")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json(),
            {"detail": "You can only access the next node in sequence."},
        )

    def test_the_next_node_in_sequence_is_readable(self):
        self.start_game()

        response = self.get(f"/api/nodes/{self.second.id}/")

        self.assertEqual(response.status_code, 200)

    def test_an_unknown_node_is_a_404(self):
        response = self.get("/api/nodes/999999/")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "Node not found."})

    def test_a_junction_exposes_both_branches(self):
        self.start_game()
        self.post(f"/api/nodes/{self.second.id}/submit/")

        answers = self.get(f"/api/nodes/{self.junction.id}/").json()["answers"]

        self.assertEqual(
            [a["id"] for a in answers], [self.start.id, self.second.id]
        )
        self.assertEqual([a["answer"] for a in answers], ["left", "right"])

    def test_a_user_without_a_team_is_refused(self):
        self.user.team = None
        self.user.save(update_fields=["team"])

        response = self.get(f"/api/nodes/{self.start.id}/")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json(), {"detail": "User is not part of any team."}
        )


class CurrentNodeTests(GameTestCase):
    def test_before_the_game_starts(self):
        response = self.get("/api/nodes/current/")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"detail": "Game not started yet."})

    def test_after_the_game_starts(self):
        self.start_game()

        response = self.get("/api/nodes/current/")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["detail"], "Details fetched successfully")
        self.assertEqual(body["data"]["id"], self.start.id)
        self.assertEqual(body["data"]["status"], "in-progress")


class VisitedTests(GameTestCase):
    def test_nothing_visited_yet(self):
        self.assertEqual(self.get("/api/nodes/visited/").json(), [])

    def test_walks_from_the_head_up_to_the_junction(self):
        self.start_game()
        self.post(f"/api/nodes/{self.second.id}/submit/")
        self.post(f"/api/nodes/{self.junction.id}/submit/")

        body = self.get("/api/nodes/visited/").json()

        self.assertEqual(
            [node["id"] for node in body],
            [self.start.id, self.second.id, self.junction.id],
        )

    def test_a_path_node_picks_the_starting_point(self):
        self.start_game()
        self.post(f"/api/nodes/{self.second.id}/submit/")

        body = self.get(f"/api/nodes/visited/?path={self.second.id}").json()

        self.assertEqual([node["id"] for node in body], [self.second.id])

    def test_a_non_numeric_path_is_rejected(self):
        self.start_game()

        response = self.get("/api/nodes/visited/?path=abc")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"detail": "Invalid path parameter."})

    def test_an_unvisited_path_node_is_a_404(self):
        self.start_game()

        response = self.get(f"/api/nodes/visited/?path={self.junction.id}")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.json(), {"detail": "Path node not found in visited nodes."}
        )


class TargetTeamTests(GameTestCase):
    def test_lists_every_other_living_team(self):
        body = self.get("/api/nodes/target-teams/").json()

        self.assertEqual(body["detail"], "Details fetched successfully")
        listed = {team["id"] for team in body["data"]}
        self.assertNotIn(self.team.id, listed)
        self.assertEqual(
            listed,
            set(
                Team.objects.exclude(id=self.team.id)
                .filter(life__gt=0)
                .values_list("id", flat=True)
            ),
        )

    def test_dead_teams_are_not_targets(self):
        Team.objects.exclude(id=self.team.id).update(life=0)

        self.assertEqual(self.get("/api/nodes/target-teams/").json()["data"], [])


class TargetAttackTests(GameTestCase):
    def setUp(self):
        super().setUp()
        self.team.attack = 3
        self.team.save(update_fields=["attack"])

    def attack(self, **payload):
        return self.post("/api/nodes/target-attack/", json=payload)

    def test_a_successful_attack_moves_life_and_attack_points(self):
        life_before = self.other_team.life

        response = self.attack(target_team=self.other_team.id, attack_value=2)

        self.assertEqual(response.status_code, 200)
        self.other_team.refresh_from_db()
        self.assertEqual(self.other_team.life, life_before - 2)
        self.assertEqual(self.refresh_team().attack, 1)

    def test_life_does_not_go_negative(self):
        self.other_team.life = 1
        self.other_team.save(update_fields=["life"])

        self.attack(target_team=self.other_team.id, attack_value=3)

        self.other_team.refresh_from_db()
        self.assertEqual(self.other_team.life, 0)

    def test_attacking_yourself_is_refused(self):
        response = self.attack(target_team=self.team.id, attack_value=1)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["detail"], "You cannot attack your own team."
        )

    def test_spending_more_than_you_have_is_refused(self):
        response = self.attack(target_team=self.other_team.id, attack_value=99)

        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertEqual(
            body["detail"], "Not enough attack points to perform this attack."
        )
        self.assertEqual(body["data"], {"available_attack_points": 3})

    def test_an_unknown_target_is_refused(self):
        response = self.attack(target_team=999999, attack_value=1)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "Target team does not exist.")

    def test_a_non_positive_attack_value_is_refused(self):
        response = self.attack(target_team=self.other_team.id, attack_value=0)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json(),
            {"attack_value": ["Ensure this value is greater than or equal to 1."]},
        )
