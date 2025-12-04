"""
    Menu layouts for DIRECT

    License: MIT
"""

__all__ = ("OrgMenuLayout",
           "OM",
           )

from gluon import current, URL, IMG
from core import S3NavigationItem

# =============================================================================
class OrgMenuLayout(S3NavigationItem):
    """ Layout for the organisation-specific menu """

    @staticmethod
    def layout(item):

        settings = current.deployment_settings

        name = settings.get_custom("context_org_name")
        logo = settings.get_custom("org_menu_logo")

        current_user = current.auth.user
        if current_user:
            user_org_id = current_user.organisation_id
            if user_org_id:
                otable = current.s3db.org_organisation
                query = (otable.id == user_org_id) & \
                        (otable.deleted == False)
                row = current.db(query).select(otable.name,
                                               limitby = (0, 1),
                                               ).first()
                if row:
                    name = row.name

        if logo:
            path = URL(c="static", f="themes", args=list(logo))
            logo = IMG(_src=path, _alt=name, _height=49, _class="org-menu-logo")
        else:
            logo = ""

        # Note: render using current.menu.org.render()[0] + current.menu.org.render()[1]
        return (name, logo)

# -----------------------------------------------------------------------------
# Shortcut
OM = OrgMenuLayout

# END =========================================================================
