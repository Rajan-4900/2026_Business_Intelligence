from django.core.management.base import BaseCommand

from report_generator.services import fail_stale, purge_expired


class Command(BaseCommand):
    help = 'Delete expired PDF reports and mark interrupted report jobs as failed.'

    def handle(self, *args, **options):
        stale = fail_stale()
        deleted = purge_expired()
        self.stdout.write(f'Deleted {deleted} expired report(s); marked {stale} interrupted job(s) as failed.')
