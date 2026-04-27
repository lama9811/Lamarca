from django.conf import settings
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver


class Profile(models.Model):
    """Per-user billing state. Auto-created when a User is created."""
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='profile',
    )
    credit_balance = models.PositiveIntegerField(default=0)
    free_used = models.PositiveIntegerField(default=0)
    lifetime_credits_purchased = models.PositiveIntegerField(default=0)
    lifetime_generations = models.PositiveIntegerField(default=0)

    stripe_customer_id = models.CharField(max_length=64, blank=True, default='')

    # Voice cloning: list of up to 3 sample paragraphs of the user's writing.
    # When present, generation uses these as a style reference.
    voice_samples = models.JSONField(default=list, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def has_voice(self) -> bool:
        return bool(self.voice_samples) and any(s.strip() for s in self.voice_samples)

    @property
    def free_remaining(self) -> int:
        return max(0, settings.FREE_GENERATIONS - self.free_used)

    @property
    def total_remaining(self) -> int:
        return self.credit_balance + self.free_remaining

    def __str__(self) -> str:
        return f'Profile<{self.user_id}> credits={self.credit_balance} free_left={self.free_remaining}'


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def ensure_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)
