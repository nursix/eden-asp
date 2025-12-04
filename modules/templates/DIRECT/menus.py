"""
    Custom Menus for DIRECT

    License: MIT
"""

from gluon import current, URL, TAG, SPAN
from core import IS_ISO639_2_LANGUAGE_CODE
from core.ui.layouts import MM, M, ML, MP, MA
try:
    from .layouts import OM
except ImportError:
    pass
import core.ui.menus as default

# =============================================================================
class MainMenu(default.MainMenu):
    """ Custom Application Main Menu """

    # -------------------------------------------------------------------------
    @classmethod
    def menu(cls):
        """ Compose Menu """

        # Modules menus
        main_menu = MM()(
            cls.menu_modules(),
        )

        # Additional menus
        current.menu.personal = cls.menu_personal()
        current.menu.lang = cls.menu_lang()
        current.menu.about = cls.menu_about()
        current.menu.org = cls.menu_org()

        return main_menu

    # -------------------------------------------------------------------------
    @classmethod
    def menu_modules(cls):
        """ Modules Menu """

        menu = [MM("Needs", c="req", f="need"),
                #MM("Beneficiaries", c="dvr", f="person"),
                MM("Shelters", c="cr", f="shelter"),
                #MM("Water Sources", c="water", f="index"),
                #MM("Inventory", c="inv", f="warehouse"),
                MM("Organizations", c="org", f="organisation"),
                ]

        return menu

    # -------------------------------------------------------------------------
    @classmethod
    def menu_org(cls):
        """ Organisation Logo and Name """

        #OM = OrgMenuLayout
        return OM()

    # -------------------------------------------------------------------------
    @classmethod
    def menu_lang(cls, **attr):
        """ Language Selector """

        languages = current.deployment_settings.get_L10n_languages()
        represent_local = IS_ISO639_2_LANGUAGE_CODE.represent_local

        menu_lang = ML("Language", right=True)

        for code in languages:
            # Show each language name in its own language
            lang_name = represent_local(code)
            menu_lang(
                ML(lang_name,
                   translate = False,
                   lang_code = code,
                   lang_name = lang_name,
                   )
            )

        return menu_lang

    # -------------------------------------------------------------------------
    @classmethod
    def menu_personal(cls):
        """ Personal Menu """

        auth = current.auth
        #s3 = current.response.s3
        settings = current.deployment_settings

        ADMIN = current.auth.get_system_roles().ADMIN

        if not auth.is_logged_in():
            request = current.request
            login_next = URL(args=request.args, vars=request.vars)
            if request.controller == "default" and \
               request.function == "user" and \
               "_next" in request.get_vars:
                login_next = request.get_vars["_next"]

            self_registration = settings.get_security_self_registration()
            menu_personal = MP()(
                        MP("Register", c="default", f="user",
                           m = "register",
                           check = self_registration,
                           ),
                        MP("Login", c="default", f="user",
                           m = "login",
                           vars = {"_next": login_next},
                           ),
                        )
            if settings.get_auth_password_retrieval():
                menu_personal(MP("Lost Password", c="default", f="user",
                                 m = "retrieve_password",
                                 ),
                              )
        else:
            s3_has_role = auth.s3_has_role
            is_org_admin = lambda i: s3_has_role("ORG_ADMIN", include_admin=False)
            menu_personal = MP()(
                        MP("Administration", c="admin", f="index",
                           restrict = ADMIN,
                           ),
                        MP("Administration", c="admin", f="user",
                           check = is_org_admin,
                           ),
                        MP("Profile", c="default", f="person"),
                        MP("Change Password", c="default", f="user",
                           m = "change_password",
                           ),
                        MP("Logout", c="default", f="user",
                           m = "logout",
                           ),
            )
        return menu_personal

    # -------------------------------------------------------------------------
    @classmethod
    def menu_about(cls):

        menu_about = MA(c="default")(
            MA("Help", f="help"),
            MA("Contact", f="contact"),
            MA("Privacy", f="index", args=["privacy"]),
            MA("Legal Notice", f="index", args=["legal"]),
            MA("Version", f="about", restrict = ("ORG_GROUP_ADMIN")),
        )
        return menu_about

# =============================================================================
class OptionsMenu(default.OptionsMenu):
    """ Custom Controller Menus """

    # -------------------------------------------------------------------------
    @staticmethod
    def admin():
        """ ADMIN menu """

        if not current.auth.s3_has_role("ADMIN"):
            # OrgAdmin: No Side-menu
            return None

        # NB: Do not specify a controller for the main menu to allow
        #     re-use of this menu by other controllers
        return M()(
                    M("Users and Roles", c="admin", link=False)(
                        M("Manage Users", f="user"),
                        M("Manage Roles", f="role"),
                    ),
                    M("CMS", c="cms", f="post"),
                    M("Database", c="appadmin", f="index")(
                        M("Raw Database access", c="appadmin", f="index")
                    ),
                    M("Scheduler", c="admin", f="task"),
                    M("Error Tickets", c="admin", f="errors"),
                    M("Event Log", c="admin", f="event"),
                )

    # -------------------------------------------------------------------------
    @classmethod
    def cms(cls):

        if not current.auth.s3_has_role("ADMIN"):
            return cls.org()

        return super().cms()

    # -------------------------------------------------------------------------
    @classmethod
    def hrm(cls):
        """ HRM / Human Resources Management """

        return cls.org()

    # -------------------------------------------------------------------------
    @staticmethod
    def org():
        """ ORG / Organization Registry """

        T = current.T
        auth = current.auth

        ADMIN = current.session.s3.system_roles.ADMIN

        # Newsletter menu
        author = auth.s3_has_permission("create", "cms_newsletter", c="cms", f="newsletter")
        inbox_label = T("Inbox") if author else T("Newsletters")
        unread = current.s3db.cms_unread_newsletters()
        if unread:
            inbox_label = TAG[""](inbox_label, SPAN(unread, _class="num-pending"))
        if author:
            cms_menu = M("Newsletters", c="cms", f="read_newsletter")(
                            M(inbox_label, f="read_newsletter", translate=False),
                            M("Compose and Send", f="newsletter", p="create"),
                            )
        else:
            cms_menu = M(inbox_label, c="cms", f="read_newsletter", translate=False)

        return M(c=("org", "hrm", "act"))(
                    M("Organizations", c="org", f="organisation")(
                        M("Create", m="create"),
                        ),
                    M("Organization Groups", f="group")(
                        M("Create", m="create"),
                        ),
                    M("Activities", c="act", f="activity"),
                    M("Staff", c="hrm", f="staff"),
                    cms_menu,
                    M("Administration", link=False, restrict=[ADMIN])(
                        M("Organization Types", c="org", f="organisation_type"),
                        M("Activity Types", c="act", f="activity_type"),
                        M("Job Titles", c="hrm", f="job_title"),
                        ),
                    )

    # -------------------------------------------------------------------------
    @staticmethod
    def req():
        """ REQ / Needs Management """

        return M(c="req")(
                    M("Needs", f="need")(
                        M("Register", m="create"),
                        M("Map", m="map"),
                        ),
                    )

    # -------------------------------------------------------------------------
    @staticmethod
    def water():
        """ Water: Wells, etc """

        return M(c="water")(
                    M("Wells", f="well")(
                        M("Create", m="create"),
                        M("Map", m="map"),
                        ),
                    )

# END =========================================================================
