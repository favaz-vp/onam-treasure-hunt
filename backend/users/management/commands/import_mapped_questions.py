import csv

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from users.models import Effects, Node

REQUIRED_COLUMNS = {'id', 'next_node', 'question', 'answer', 'syn', 'alt_node', 'score', 'effects'}


class Command(BaseCommand):
    help = (
        "Create/update Node rows from a mapped-questions CSV "
        "(columns: id,next_node,question,answer,syn,alt_node,score,effects). "
        "Node.id is taken from the CSV 'id' column: existing nodes are updated, "
        "missing ones are created with that id."
    )

    def add_arguments(self, parser):
        parser.add_argument('csv_path', type=str)
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Report what would change without writing to the database.',
        )

    def handle(self, *args, **options):
        path = options['csv_path']
        dry_run = options['dry_run']

        try:
            with open(path, newline='', encoding='utf-8-sig') as f:
                rows = list(csv.DictReader(f))
        except OSError as e:
            raise CommandError(f"Could not read {path}: {e}")

        if not rows:
            raise CommandError("CSV has no data rows.")

        missing_cols = REQUIRED_COLUMNS - set(rows[0].keys())
        if missing_cols:
            raise CommandError(f"CSV missing columns: {sorted(missing_cols)}")

        with transaction.atomic():
            created, updated = self._import(rows)
            self._link_nodes(rows)
            dangling = self._check_dangling_refs(rows)

            verb_c = "Would create" if dry_run else "Created"
            verb_u = "would update" if dry_run else "updated"
            self.stdout.write(self.style.SUCCESS(
                f"{verb_c} {created} node(s), {verb_u} {updated} node(s)."
            ))
            if dangling:
                self.stdout.write(self.style.WARNING(
                    f"Referenced node ids not present in CSV or DB: {sorted(dangling)}"
                ))

            if dry_run:
                transaction.set_rollback(True)
                self.stdout.write(self.style.WARNING("Dry run — no changes were saved."))

    def _import(self, rows):
        created = updated = 0
        for row in rows:
            node_id = int(row['id'])
            question = (row['question'] or '').strip()
            is_junction = question.upper() == 'JUNCTION'

            defaults = {
                'data': question,
                'answer': (row['answer'] or '').strip(),
                'alt_answer': (row['syn'] or '').strip(),
                'effects': Effects.JUNCTION if is_junction else Effects.UNLOCKED,
            }
            if row['score']:
                defaults['score'] = int(row['score'])

            _, was_created = Node.objects.update_or_create(id=node_id, defaults=defaults)
            created += was_created
            updated += not was_created
        return created, updated

    def _link_nodes(self, rows):
        # Second pass: next_node/alt_next_node can point forward to rows not
        # yet created in the first pass, so only wire up FKs once every node
        # referenced by the CSV already exists.
        for row in rows:
            node_id = int(row['id'])
            next_id = int(row['next_node']) if row['next_node'] else None
            alt_id = int(row['alt_node']) if row['alt_node'] else None
            Node.objects.filter(id=node_id).update(
                next_node_id=next_id,
                alt_next_node_id=alt_id,
            )

    def _check_dangling_refs(self, rows):
        referenced = set()
        for row in rows:
            if row['next_node']:
                referenced.add(int(row['next_node']))
            if row['alt_node']:
                referenced.add(int(row['alt_node']))
        existing_ids = set(Node.objects.filter(id__in=referenced).values_list('id', flat=True))
        return referenced - existing_ids
