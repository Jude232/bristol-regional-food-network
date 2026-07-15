from rest_framework.permissions import BasePermission

from accounts.models import User

#This file restricts API endpoints according to the authenticated user’s role.
#Producer endpoints require a producer account and profile, while customer endpoints support customers, restaurants and community groups.

# These roles are allowed to use customer API endpoints.
#
# Restaurants and community groups use the same ordering features
# as normal customer accounts.
CUSTOMER_ROLES = {
    User.Role.CUSTOMER,
    User.Role.COMMUNITY_GROUP,
    User.Role.RESTAURANT,
}


class IsProducer(BasePermission):
    """
    Allows access only to authenticated producer accounts.

    This permission can be added to API views that should only be
    available to marketplace producers.
    """

    # This message is returned when access is refused.
    message = "A producer account is required."

    def has_permission(self, request, view):
        """
        Check whether the current user is allowed to access the view.
        """

        return (
            # The user must be logged in.
            request.user.is_authenticated

            # Their account role must be producer.
            and request.user.role == User.Role.PRODUCER

            # The account must also have a linked producer profile.
            and hasattr(request.user, "producer_profile")
        )


class IsCustomerAccount(BasePermission):
    """
    Allows access to authenticated customer-type accounts.

    This includes normal customers, community groups and restaurants.
    """

    # This message is returned when access is refused.
    message = "A customer account is required."

    def has_permission(self, request, view):
        """
        Check that the user is logged in and has a customer role.
        """

        return (
            # The user must be logged in.
            request.user.is_authenticated

            # Their role must be one of the permitted customer roles.
            and request.user.role in CUSTOMER_ROLES
        )