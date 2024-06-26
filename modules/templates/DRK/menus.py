"""
    Custom menus for DRK/Village

    License: MIT
"""

from gluon import current, URL
from core import IS_ISO639_2_LANGUAGE_CODE
from core.ui.layouts import MM, M, ML, MP, MA, SEP, homepage
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
        """ Custom Modules Menu """

        from .helpers import drk_default_shelter
        shelter_id = drk_default_shelter()

        has_role = current.auth.s3_has_role
        not_admin = not has_role("ADMIN")

        if not_admin and has_role("SECURITY"):
            return [
                MM("Residents", c="security", f="person"),
                MM("Dashboard", c="cr", f="shelter",
                   args = [shelter_id, "profile"],
                   check = shelter_id is not None,
                   ),
                #MM("ToDo", c="project", f="task"),
                MM("Check-In / Check-Out", c="cr", f="shelter",
                   args = [shelter_id, "check-in"],
                   check = shelter_id is not None,
                   ),
                MM("Confiscation", c="security", f="seized_item"),
            ]

        elif not_admin and has_role("QUARTIER"):
            return [
                MM("Residents", c=("dvr", "cr"), f=("person", "shelter_registration")),
                MM("Confiscation", c="security", f="seized_item"),
            ]

        else:
            return [
                MM("Residents", c=("dvr", "pr")),
                MM("Event Registration", c="dvr", f="case_event",
                   m = "register",
                   p = "create",
                   # Show only if not authorized to see "Residents"
                   check = lambda this: not this.preceding()[-1].check_permission(),
                   ),
                MM("Food Distribution", c="dvr", f="case_event",
                   m = "register_food",
                   p = "create",
                   # Show only if not authorized to see "Residents"
                   check = lambda this: not this.preceding()[-2].check_permission(),
                   ),
                MM("Food Distribution Statistics", c="dvr", f="case_event",
                   m = "report",
                   vars = {"code": "FOOD*"},
                   restrict = ("FOOD_STATS",),
                   # Show only if not authorized to see "Residents"
                   check = lambda this: not this.preceding()[-3].check_permission(),
                   ),
                MM("ToDo", c="project", f="task"),
                MM("Dashboard", c="cr", f="shelter",
                   args = [shelter_id, "profile"],
                   check = shelter_id is not None,
                   ),
                # @ToDO: Move to Dashboard Widget?
                MM("Housing Units", c="cr", f="shelter",
                   t = "cr_shelter_unit",
                   args = [shelter_id, "shelter_unit"],
                   check = shelter_id is not None,
                   ),
                homepage("vol"),
                homepage("hrm"),
                MM("More", link=False)(
                    MM("Facilities", c="org", f="facility"),
                    #homepage("req"),
                    homepage("inv"),
                    SEP(link=False),
                    MM("Confiscation", c="security", f="seized_item"),
                    SEP(link=False),
                    MM("Surplus Meals", c="default", f="index",
                       args = "surplus_meals",
                       t = "dvr_case_event",
                       restrict = ("ADMINISTRATION", "ADMIN_HEAD", "INFO_POINT", "RP"),
                       ),
                    ),
            ]

    # -------------------------------------------------------------------------
    @classmethod
    def menu_org(cls):
        """ Custom Organisation Menu """

        return OM()

    # -------------------------------------------------------------------------
    @classmethod
    def menu_lang(cls, **attr):

        languages = current.deployment_settings.get_L10n_languages()
        represent_local = IS_ISO639_2_LANGUAGE_CODE.represent_local

        # Language selector
        menu_lang = ML("Language", right=True)
        for code in languages:
            # Show Language in it's own Language
            lang_name = represent_local(code)
            menu_lang(
                ML(lang_name, translate=False, lang_code=code, lang_name=lang_name)
            )
        return menu_lang

    # -------------------------------------------------------------------------
    @classmethod
    def menu_personal(cls):
        """ Custom Personal Menu """

        auth = current.auth
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
            is_org_admin = lambda i: not s3_has_role(ADMIN) and \
                                     s3_has_role("ORG_ADMIN")
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

        ADMIN = current.auth.get_system_roles().ADMIN

        menu_about = MA(c="default")(
            MA("Help", f="help"),
            #MA("Contact", f="contact"),
            MA("Version", f="about", restrict = ADMIN),
        )
        return menu_about

# =============================================================================
class OptionsMenu(default.OptionsMenu):
    """ Custom Controller Menus """

    # -------------------------------------------------------------------------
    @staticmethod
    def cr():
        """ CR / Shelter Registry """

        from .helpers import drk_default_shelter
        shelter_id = drk_default_shelter()

        if not shelter_id:
            return None

        #ADMIN = current.auth.get_system_roles().ADMIN

        return M(c="cr")(
                    M("Shelter", f="shelter", args=[shelter_id])(
                        M("Dashboard",
                          args = [shelter_id, "profile"],
                          ),
                        M("Housing Units",
                          t = "cr_shelter_unit",
                          args = [shelter_id, "shelter_unit"],
                          ),
                    ),
                    #M("Room Inspection", f = "shelter", link=False)(
                    #      M("Register",
                    #        args = [shelter_id, "inspection"],
                    #        t = "cr_shelter_inspection",
                    #        p = "create",
                    #        ),
                    #      M("Overview", f = "shelter_inspection"),
                    #      M("Defects", f = "shelter_inspection_flag"),
                    #      ),
                    #M("Administration",
                    #  link = False,
                    #  restrict = (ADMIN, "ADMIN_HEAD"),
                    #  selectable=False,
                    #  )(
                    #    M("Shelter Flags", f="shelter_flag"),
                    #    ),
                )

    # -------------------------------------------------------------------------
    @staticmethod
    def dvr():
        """ DVR / Disaster Victim Registry """

        due_followups = current.s3db.dvr_due_followups() or "0"
        follow_up_label = "%s (%s)" % (current.T("Due Follow-ups"),
                                       due_followups,
                                       )

        ADMIN = current.auth.get_system_roles().ADMIN

        return M(c="dvr")(
                    M("Current Cases", c=("dvr", "pr"), f="person",
                      vars = {"closed": "0"})(
                        M("Create", m="create", t="pr_person", p="create"),
                        M("All Cases", vars = {}),
                        ),
                    M("Reports", link=False)(
                        M("Check-in overdue", c=("dvr", "pr"), f="person",
                          restrict = (ADMIN, "ADMINISTRATION", "ADMIN_HEAD"),
                          vars = {"closed": "0", "overdue": "check-in"},
                          ),
                        M("Food Distribution overdue", c=("dvr", "pr"), f="person",
                          restrict = (ADMIN, "ADMINISTRATION", "ADMIN_HEAD"),
                          vars = {"closed": "0", "overdue": "FOOD*"},
                          ),
                        M("Residents Reports", c="dvr", f="site_activity",
                          ),
                        M("Food Distribution Statistics", c="dvr", f="case_event",
                          m = "report",
                          restrict = (ADMIN, "ADMINISTRATION", "ADMIN_HEAD", "SECURITY_HEAD", "RP"),
                          vars = {"code": "FOOD*"},
                          ),
                        ),
                    M("Activities", f="case_activity")(
                        M("Emergencies",
                          vars = {"~.emergency": "True"},
                          ),
                        M(follow_up_label, f="due_followups"),
                        M("All Activities"),
                        M("Report", m="report"),
                        ),
                    M("Appointments", f="case_appointment")(
                        M("Overview"),
                        M("Import Updates", m="import", p="create",
                          restrict = (ADMIN, "ADMINISTRATION", "ADMIN_HEAD"),
                          ),
                        M("Bulk Status Update", m="manage", p="update",
                          restrict = (ADMIN, "ADMINISTRATION", "ADMIN_HEAD"),
                          ),
                        ),
                    #M("Allowances", f="allowance")(
                    #    M("Overview"),
                    #    M("Payment Registration", m="register", p="update"),
                    #    M("Status Update", m="manage", p="update"),
                    #    M("Import", m="import", p="create"),
                    #    ),
                    M("Event Registration", c="dvr", f="case_event", m="register", p="create")(
                        ),
                    M("Food Distribution", c="dvr", f="case_event", m="register_food", p="create")(
                        ),
                    M("Archive", link=False)(
                        M("Closed Cases", f="person",
                          vars={"closed": "1"},
                          ),
                        M("Invalid Cases", f="person",
                          restrict = (ADMIN, "ADMINISTRATION", "ADMIN_HEAD"),
                          vars={"archived": "1"},
                          ),
                        ),
                    M("Administration", restrict=(ADMIN, "ADMIN_HEAD"))(
                        M("Flags", f="case_flag"),
                        M("Case Status", f="case_status"),
                        M("Need Types", f="need"),
                        M("Appointment Types", f="case_appointment_type"),
                        M("Event Types", f="case_event_type"),
                        M("Check Transferability", c="default", f="index",
                          args = ["transferability"],
                          ),
                        ),
                    )

    # -------------------------------------------------------------------------
    @staticmethod
    def org():
        """ ORG / Organization Registry """

        ADMIN = current.session.s3.system_roles.ADMIN

        return M(c="org")(
                    #M("Organizations", f="organisation")(
                        #M("Create", m="create"),
                        #M("Import", m="import")
                    #),
                    M("Facilities", f="facility")(
                        M("Create", m="create"),
                    ),
                    #M("Organization Types", f="organisation_type",
                      #restrict=[ADMIN])(
                        #M("Create", m="create"),
                    #),
                    M("Facility Types", f="facility_type",
                      restrict=[ADMIN])(
                        M("Create", m="create"),
                    ),
                 )

    # -------------------------------------------------------------------------
    @staticmethod
    def project():
        """ PROJECT / Project/Task Management """

        return M(c="project")(
                 M("Tasks", f="task")(
                    M("Create", m="create"),
                    M("My Open Tasks", vars={"mine":1}),
                 ),
                )

    # -------------------------------------------------------------------------
    @staticmethod
    def security():
        """ SECURITY / Security Management """

        return M(c="security")(
                M("Confiscation", f="seized_item")(
                    M("Create", m="create"),
                    M("Item Types", f="seized_item_type"),
                    M("Depositories", f="seized_item_depository"),
                    ),
                )

# END =========================================================================
