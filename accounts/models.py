from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "admin", "Admin"
        STANDARD = "standard", "Standard user"

    email = models.EmailField(unique=True)
    role = models.CharField(
        max_length=20, choices=Role.choices, default=Role.STANDARD, db_index=True
    )

    @property
    def is_inventory_admin(self):
        return self.is_superuser or self.role == self.Role.ADMIN

    def save(self, *args, **kwargs):
        if self.is_superuser:
            self.role = self.Role.ADMIN
        super().save(*args, **kwargs)
