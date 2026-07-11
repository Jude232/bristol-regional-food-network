from rest_framework.permissions import BasePermission

from accounts.models import User


CUSTOMER_ROLES = {
    User.Role.CUSTOMER,
    User.Role.COMMUNITY_GROUP,
    User.Role.RESTAURANT,
}


class IsProducer(BasePermission):
    """Allow access only to authenticated producer accounts."""

    message = "A producer account is required."

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.role == User.Role.PRODUCER
            and hasattr(request.user, "producer_profile")
        )


class IsCustomerAccount(BasePermission):
    """Allow access only to authenticated customer account types."""

    message = "A customer account is required."

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.role in CUSTOMER_ROLES
        )
