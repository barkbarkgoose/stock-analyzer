"""Create a login for the web app.

Self-registration is disabled, so this is how accounts are made::

    python manage.py add_user you@example.com --name "Your Name"
    python manage.py add_user you@example.com --name "Your Name" --admin

The password is prompted for (twice) and checked against the password
validators; it never appears in shell history.  Use the built-in
``changepassword EMAIL`` to reset it later.
"""

from __future__ import annotations

import getpass

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Create a user who can log in to the web app."

    def add_arguments(self, parser):
        parser.add_argument("email")
        parser.add_argument("--name", required=True)
        parser.add_argument(
            "--admin",
            action="store_true",
            help="Also allow access to the Django admin at /admin/.",
        )

    def handle(self, *args, email: str, name: str, admin: bool, **options):
        User = get_user_model()
        if User.objects.filter(email__iexact=email).exists():
            raise CommandError(f"A user with email {email} already exists.")

        password = getpass.getpass("Password: ")
        if password != getpass.getpass("Password (again): "):
            raise CommandError("Passwords did not match.")
        candidate = User(email=email, name=name)
        try:
            validate_password(password, user=candidate)
        except ValidationError as exc:
            raise CommandError(" ".join(exc.messages)) from exc

        if admin:
            User.objects.create_superuser(email=email, name=name, password=password)
        else:
            User.objects.create_user(email=email, name=name, password=password)
        self.stdout.write(self.style.SUCCESS(f"Created {'admin ' if admin else ''}user {email}."))
