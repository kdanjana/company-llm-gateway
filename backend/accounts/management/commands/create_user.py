"""Create a dashboard user.

    python manage.py create_user priya --role admin
    python manage.py create_user ravi --role head --department Sales

The password is asked twice (hidden). For scripts you can pass --password instead.
A head's department is created if it does not exist yet.
"""
import getpass

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import Profile
from gateway.models import Department


class Command(BaseCommand):
    help = "Create a dashboard user: an admin, or a department head."

    def add_arguments(self, parser):
        parser.add_argument("username")
        parser.add_argument("--role", choices=[r.value for r in Profile.Role], required=True)
        parser.add_argument("--department", help="Required for --role head")
        parser.add_argument("--password", help="Optional; asked interactively if left out")

    def handle(self, *args, **options):
        User = get_user_model()
        username, role = options["username"], options["role"]

        if User.objects.filter(username=username).exists():
            raise CommandError(f"User '{username}' already exists.")
        if role == Profile.Role.HEAD and not options["department"]:
            raise CommandError("A department head needs --department.")

        password = options["password"] or self._ask_password()
        try:
            validate_password(password, User(username=username))
        except ValidationError as exc:
            raise CommandError(" ".join(exc.messages))

        with transaction.atomic():
            department = None
            if role == Profile.Role.HEAD:
                department, _ = Department.objects.get_or_create(name=options["department"])
            user = User.objects.create_user(username=username, password=password)
            Profile.objects.create(user=user, role=role, department=department)

        where = f" of {department.name}" if department else ""
        self.stdout.write(self.style.SUCCESS(f"Created {username}: {Profile.Role(role).label}{where}"))

    @staticmethod
    def _ask_password() -> str:
        first = getpass.getpass("Password: ")
        if first != getpass.getpass("Password (again): "):
            raise CommandError("The passwords do not match.")
        return first
