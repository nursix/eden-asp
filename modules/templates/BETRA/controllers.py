"""
    Custom controllers for BETRA

    License: MIT
"""

from gluon import current, URL
from gluon.html import DIV, H3, H4, I, LI, TAG, UL, XML

from core import CustomController

from s3db.cms import CustomPage

# =============================================================================
class index(CustomController):
    """ Custom Home Page """

    def __call__(self):

        output = {}

        T = current.T

        auth = current.auth
        settings = current.deployment_settings


        # Defaults
        login_form = None
        login_div = None
        announcements = None
        announcements_title = None

        roles = current.session.s3.roles
        sr = auth.get_system_roles()
        if sr.AUTHENTICATED in roles:
            # Logged-in user
            # => display announcements

            from core import S3DateTime
            dtrepr = lambda dt: S3DateTime.datetime_represent(dt, utc=True)

            filter_roles = roles if sr.ADMIN not in roles else None
            posts = current.s3db.cms_announcements(roles=filter_roles)

            # Render announcements list
            announcements = UL(_class="announcements")
            if posts:
                announcements_title = T("Announcements")
                priority_classes = {2: "announcement-important",
                                    3: "announcement-critical",
                                    }
                priority_icons = {2: "fa-exclamation-circle",
                                  3: "fa-exclamation-triangle",
                                  }
                for post in posts:
                    # The header
                    header = H4(post.name)

                    # Priority
                    priority = post.priority
                    # Add icon to header?
                    icon_class = priority_icons.get(post.priority)
                    if icon_class:
                        header = TAG[""](I(_class="fa %s announcement-icon" % icon_class),
                                         header,
                                         )
                    # Priority class for the box
                    prio = priority_classes.get(priority, "")

                    row = LI(DIV(DIV(DIV(dtrepr(post.date),
                                        _class = "announcement-date",
                                        ),
                                    _class="fright",
                                    ),
                                 DIV(DIV(header,
                                         _class = "announcement-header",
                                         ),
                                     DIV(XML(post.body),
                                         _class = "announcement-body",
                                         ),
                                     _class="announcement-text",
                                    ),
                                 _class = "announcement-box %s" % prio,
                                 ),
                             )
                    announcements.append(row)
        else:
            # Anonymous user
            # => provide a login box
            login_div = DIV(H3(T("Login")),
                            )
            auth.messages.submit_button = T("Login")
            login_form = auth.login(inline=True)

        logo = settings.get_custom("homepage_logo")
        logo = URL(c="static", f="themes", args=list(logo)) if logo else ""
        logo_alt = settings.get_custom("context_org_name")

        output = {"login_div": login_div,
                  "login_form": login_form,
                  "announcements": announcements,
                  "announcements_title": announcements_title,
                  "logo": logo,
                  "logo_alt": logo_alt,
                  }

        # Custom view and homepage styles
        self._view(settings.get_theme_layouts(), "index.html")

        return output

# =============================================================================
class contact(CustomPage):
    """ Custom page for contact information """

    context = ("default", "Contact")

# =============================================================================
class privacy(CustomPage):
    """ Custom page for privacy notice """

    context = ("default", "Privacy")

# =============================================================================
class legal(CustomPage):
    """ Custom page for legal notice """

    context = ("default", "Legal")

# END =========================================================================
