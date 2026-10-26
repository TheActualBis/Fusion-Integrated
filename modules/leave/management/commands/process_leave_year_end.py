from django.core.management.base import BaseCommand, CommandError

from modules.leave.services import LeaveError, process_year_end


class Command(BaseCommand):
    help = "Run the ELM year-end leave account processing for a calendar year."

    def add_arguments(self, parser):
        parser.add_argument("year", type=int)

    def handle(self, *args, **options):
        year = options["year"]
        if not 2000 <= year <= 2100:
            raise CommandError("Year must be between 2000 and 2100.")
        try:
            result = process_year_end(year)
        except LeaveError as exc:
            raise CommandError(str(exc)) from exc
        if result.exceptions:
            self.stderr.write(self.style.ERROR(f"Completed with {len(result.exceptions)} exception(s)."))
            for item in result.exceptions:
                self.stderr.write(item)
        else:
            self.stdout.write(self.style.SUCCESS(f"ELM year-end processing for {year} completed."))
