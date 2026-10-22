"""Immutable administrative penalty adjustments; identities survive account deletion."""
import uuid

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q


class PenaltyAuditQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError('Penalty history cannot be edited.')

    def delete(self):
        raise ValidationError('Penalty history cannot be deleted.')

    def bulk_update(self, objs, fields, batch_size=None):
        raise ValidationError('Penalty history cannot be edited.')


class PenaltyAdjustment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    request_id = models.UUIDField(unique=True, editable=False)
    user_id_snapshot = models.UUIDField(db_index=True, editable=False)
    user_name = models.CharField(max_length=255)
    user_role = models.CharField(max_length=20)
    user_barangay = models.CharField(max_length=255, blank=True)
    barangay_key = models.CharField(max_length=255, blank=True)
    city_key = models.CharField(max_length=255, blank=True)
    province_key = models.CharField(max_length=255, blank=True)
    admin_id_snapshot = models.UUIDField(editable=False)
    admin_name = models.CharField(max_length=255)
    admin_role = models.CharField(max_length=50)
    points_delta = models.SmallIntegerField()
    points_before = models.PositiveSmallIntegerField()
    points_after = models.PositiveSmallIntegerField()
    penalty_month = models.DateField()
    reason = models.TextField(max_length=2000)
    report_verified = models.BooleanField(default=False)
    incident_reference = models.CharField(max_length=100, blank=True)
    booking_id_snapshot = models.UUIDField(null=True, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = PenaltyAuditQuerySet.as_manager()

    class Meta:
        db_table = 'tbl_penalty_adjustment'
        ordering = ['-created_at', '-id']
        default_permissions = ('view',)
        indexes = [models.Index(fields=['barangay_key', 'city_key', 'province_key'], name='penalty_audit_scope_idx')]
        constraints = [
            models.CheckConstraint(condition=Q(points_before__lte=3, points_after__lte=3), name='penalty_audit_score_range'),
            models.CheckConstraint(condition=Q(points_delta__in=[-3, -2, -1, 1, 2, 3]), name='penalty_audit_nonzero_delta'),
            models.CheckConstraint(condition=Q(points_after=F('points_before') + F('points_delta')), name='penalty_audit_score_matches'),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding or kwargs.get('update_fields') or kwargs.get('force_update'):
            raise ValidationError('Penalty history cannot be edited.')
        kwargs['force_insert'] = True
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('Penalty history cannot be deleted.')
