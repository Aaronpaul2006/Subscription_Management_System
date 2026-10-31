import re

from django.core.exceptions import ValidationError

SPECIAL = re.compile(r"[^A-Za-z0-9]")


class StrongPasswordValidator:
    """More than eight characters, with an uppercase letter, a lowercase letter
    and a special character (problem statement, "A new customer signs up")."""

    def validate(self, password, user=None):
        errors = []
        if len(password) <= 8:
            errors.append("Password must be more than 8 characters long.")
        if not re.search(r"[A-Z]", password):
            errors.append("Password must contain an uppercase letter.")
        if not re.search(r"[a-z]", password):
            errors.append("Password must contain a lowercase letter.")
        if not SPECIAL.search(password):
            errors.append("Password must contain a special character.")
        if errors:
            raise ValidationError(errors, code="password_weak")

    def get_help_text(self):
        return (
            "More than 8 characters, with an uppercase letter, a lowercase letter "
            "and a special character."
        )
