from django.core.management.base import BaseCommand

from modules.leave.services import process_sla


class Command(BaseCommand):
    help = "Process pending ELM reminder and escalation thresholds."

    def handle(self, *args, **options):
        result = process_sla()
        self.stdout.write(
            self.style.SUCCESS(
                f"Processed ELM SLA thresholds: {result['reminded']} reminders, "
                f"{result['escalated']} escalations."
            )
        )
