"""
    Person Registry, Controllers
"""

module = request.controller

# -----------------------------------------------------------------------------
def index():
    """ Module's Home Page """

    return settings.customise_home(module, alt_function="index_alt")

# -----------------------------------------------------------------------------
def index_alt():
    """ Default Module Homepage """

    from gluon import current
    if current.auth.s3_has_permission("read", "pr_person", c="pr", f="person"):
        # Just redirect to person list
        s3_redirect_default(URL(f="person"))

    return {"module_name": settings.modules[module].get("name_nice")}

# -----------------------------------------------------------------------------
def person():
    """ RESTful CRUD controller """

    # Enable this to allow migration of users between instances
    #s3.filter = (s3db.pr_person.pe_id == s3db.pr_person_user.pe_id) & \
                #(s3db.auth_user.id == s3db.pr_person_user.user_id) & \
                #(s3db.auth_user.registration_key != "disabled")

    def prep(r):
        if r.representation == "json" and \
           not r.component and session.s3.filter_staff:
            person_ids = session.s3.filter_staff
            session.s3.filter_staff = None
            r.resource.add_filter = (~(db.pr_person.id.belongs(person_ids)))

        elif r.interactive:
            if r.representation == "popup":
                # Hide "pe_label" and "missing" fields in person popups
                table = r.table
                table.pe_label.readable = table.pe_label.writable = False
                table.missing.readable = table.missing.writable = False

                # CustomForm breaks popup return, so disable
                s3db.clear_config("pr_person", "crud_form")

            if r.component:
                component_name = r.component_name
                if component_name == "config":
                    ctable = s3db.gis_config
                    s3db.gis_config_form_setup()
                    # Name will be generated from person's name.
                    field = ctable.name
                    field.readable = field.writable = False
                    # Hide Location
                    field = ctable.region_location_id
                    field.readable = field.writable = False

                elif component_name == "competency":
                    ctable = s3db.hrm_competency
                    ctable.organisation_id.writable = False
                    ctable.skill_id.comment = None

                elif component_name == "group_membership":
                    s3db.configure("pr_group_membership",
                                   list_fields = ["id",
                                                  "group_id",
                                                  "group_head",
                                                  "comments",
                                                  ],
                                   )

        return True
    s3.prep = prep

    # Address tab
    if settings.get_pr_use_address():
        address_tab = (T("Address"), "address")
    else:
        address_tab = None

    # Contacts Tabs
    contacts_tabs = []
    set_method = s3db.set_method
    setting = settings.get_pr_contacts_tabs()
    if "all" in setting:
        set_method("pr_person",
                   method = "contacts",
                   action = s3db.pr_Contacts)
        contacts_tabs.append((settings.get_pr_contacts_tab_label("all"),
                              "contacts",
                              ))
    if "public" in setting:
        set_method("pr_person",
                   method = "public_contacts",
                   action = s3db.pr_Contacts)
        contacts_tabs.append((settings.get_pr_contacts_tab_label("public_contacts"),
                              "public_contacts",
                              ))
    if "private" in setting and auth.is_logged_in():
        set_method("pr_person",
                   method = "private_contacts",
                   action = s3db.pr_Contacts)
        contacts_tabs.append((settings.get_pr_contacts_tab_label("private_contacts"),
                              "private_contacts",
                              ))

    # All tabs
    tabs = [(T("Basic Details"), None),
            address_tab,
            ]
    if contacts_tabs:
        tabs.extend(contacts_tabs)

    tabs.extend([(T("Images"), "image"),
                 (T("Identity"), "identity"),
                 (T("Education"), "education"),
                 (T("Groups"), "group_membership"),
                 (T("Journal"), "note"),
                 (T("Skills"), "competency"),
                 (T("Training"), "training"),
                 (T("Map Settings"), "config"),
                 ])

    s3db.configure("pr_person",
                   insertable = True,
                   listadd = False,
                   )

    return crud_controller(main = "first_name",
                           extra = "last_name",
                           rheader = lambda r: s3db.pr_rheader(r, tabs=tabs),
                           )

# -----------------------------------------------------------------------------
def address():
    """ RESTful CRUD controller """

    # CRUD pre-process
    def prep(r):
        person_id = get_vars.get("person", None)
        if person_id:
            # Coming from s3.contacts.js [s3db.pr_contacts()]
            # - currently not used as can't load Google Maps properly
            # Lookup the controller
            controller = get_vars.get("controller", "pr")
            # Lookup the access
            access = get_vars.get("access", None)
            if access is None:
                method = "contacts"
            elif access == "1":
                method = "private_contacts"
            elif access == "2":
                method = "public_contacts"
            s3db.configure("pr_address",
                            create_next = URL(c=controller,
                                              f="person",
                                              args=[person_id, method]),
                            update_next = URL(c=controller,
                                              f="person",
                                              args=[person_id, method])
                            )
            if r.method == "create":
                table = s3db.pr_person
                pe_id = db(table.id == person_id).select(table.pe_id,
                                                         limitby=(0, 1)
                                                         ).first().pe_id
                s3db.pr_address.pe_id.default = pe_id

        else:
            field = s3db.pr_address.pe_id
            if r.method == "create":
                pe_id = get_vars.get("~.pe_id", None)
                if pe_id:
                    # Coming from Profile page
                    field.default = pe_id
                else:
                    field.label = T("Entity")
                    field.readable = field.writable = True
            else:
                # No known workflow uses this
                field.label = T("Entity")
                field.readable = field.writable = True

        return True
    s3.prep = prep

    return crud_controller()

# -----------------------------------------------------------------------------
def contact():
    """ RESTful CRUD controller """

    # CRUD pre-process
    def prep(r):
        person_id = get_vars.get("person", None)
        if person_id:
            # Coming from s3.contacts.js [s3db.pr_Contacts()]
            # Lookup the controller
            controller = get_vars.get("controller", "pr")
            # Lookup the access
            access = get_vars.get("access", None)
            if access is None:
                method = "contacts"
            elif access == "1":
                method = "private_contacts"
            elif access == "2":
                method = "public_contacts"
            s3db.configure("pr_contact",
                           create_next = URL(c=controller,
                                             f="person",
                                             args=[person_id, method]),
                           update_next = URL(c=controller,
                                             f="person",
                                             args=[person_id, method])
                           )
            if r.method == "create":
                table = s3db.pr_person
                pe_id = db(table.id == person_id).select(table.pe_id,
                                                         limitby=(0, 1)
                                                         ).first().pe_id
                table = s3db.pr_contact
                table.pe_id.default = pe_id
                # Public or Private?
                if access:
                    table.access.default = access
        else:
            field = s3db.pr_contact.pe_id
            if r.method in ("create", "create.popup"):
                # Coming from Profile page
                pe_id = get_vars.get("~.pe_id", None)
                if pe_id:
                    field.default = pe_id
                else:
                    field.label = T("Entity")
                    field.readable = field.writable = True
            else:
                # @ToDo: Document which workflow uses this?
                field.label = T("Entity")
                field.readable = field.writable = True
                from core import TextFilter, OptionsFilter
                filter_widgets = [TextFilter(["value",
                                              "comments",
                                              ],
                                             label = T("Search"),
                                             comment = T("You can search by value or comments."),
                                             ),
                                  OptionsFilter("contact_method"),
                                  ]
                s3db.configure("pr_contact",
                               filter_widgets = filter_widgets,
                               )

        return True
    s3.prep = prep

    return crud_controller()

# -----------------------------------------------------------------------------
def contact_emergency():
    """
        RESTful controller to allow creating/editing of emergency contact
        records within contacts()
    """

    # CRUD pre-process
    def prep(r):
        person_id = get_vars.get("person", None)
        if person_id:
            controller = get_vars.get("controller", "pr")
            # Lookup the access
            access = get_vars.get("access", None)
            if access is None:
                method = "contacts"
            elif access == "1":
                method = "private_contacts"
            elif access == "2":
                method = "public_contacts"
            s3db.configure("pr_contact_emergency",
                           create_next = URL(c=controller,
                                             f="person",
                                             args=[person_id, method]),
                           update_next = URL(c=controller,
                                             f="person",
                                             args=[person_id, method])
                           )
            if r.method == "create":
                table = s3db.pr_person
                query = (table.id == person_id)
                pe_id = db(query).select(table.pe_id,
                                         limitby=(0, 1)).first().pe_id
                s3db.pr_contact_emergency.pe_id.default = pe_id
        else:
            field = s3db.pr_contact_emergency.pe_id
            if r.method == "create" and r.representation == "popup":
                # Coming from Profile page
                pe_id = get_vars.get("~.pe_id", None)
                if pe_id:
                    field.default = pe_id
                else:
                    field.label = T("Entity")
                    field.readable = field.writable = True

        return True
    s3.prep = prep

    return crud_controller()

# -----------------------------------------------------------------------------
def person_search():
    """
        Person REST controller
        - limited to just search_ac for use in Autocompletes
        - allows differential access permissions
    """

    s3.prep = lambda r: r.method == "search_ac"
    return crud_controller(module, "person")

# -----------------------------------------------------------------------------
def forum():
    """ RESTful CRUD controller """

    # CRUD pre-process
    def prep(r):
        if auth.s3_has_role("ADMIN"):
            # No restrictions
            return True

        from core import FS
        if r.id:
            if r.method == "join":
                # Only possible for Public Groups
                filter_ = FS("forum_type") == 1
            elif r.method == "request":
                # Only possible for Private Groups
                filter_ = FS("forum_type") == 2
            else:
                # Can only see Public Groups
                filter_ = FS("forum_type") == 1
                user = auth.user
                if user:
                    # unless the User is a Member of them
                    filter_ |= FS("forum_membership.person_id$pe_id") == user.pe_id
        else:
            # Cannot see Seceret Groups
            filter_ = FS("forum_type") != 3
            user = auth.user
            if user:
                # unless the User is a Member of them
                filter_ |= FS("forum_membership.person_id$pe_id") == user.pe_id

        r.resource.add_filter(filter_)

        return True
    s3.prep = prep

    return crud_controller(rheader = s3db.pr_rheader)

# -----------------------------------------------------------------------------
def group():
    """ RESTful CRUD controller """

    FS = s3base.S3FieldSelector
    s3.filter = (FS("group.system") == False) # do not show system groups

    # Modify list_fields for the component tab
    table = s3db.pr_group_membership
    s3db.configure("pr_group_membership",
                   list_fields = ["id",
                                  "person_id",
                                  "group_head",
                                  "comments"
                                  ],
                   )

    rheader = lambda r: \
        s3db.pr_rheader(r, tabs = [(T("Group Details"), None),
                                   (T("Address"), "address"),
                                   (T("Contact Data"), "contact"),
                                   (T("Members"), "group_membership")
                                   ])

    return crud_controller(rheader = rheader)

# -----------------------------------------------------------------------------
def group_member_role():
    """ Group Member Roles: RESTful CRUD Controller """

    return crud_controller()

# -----------------------------------------------------------------------------
def group_status():
    """ Group Statuses: RESTful CRUD Controller """

    return crud_controller()

# -----------------------------------------------------------------------------
def image():
    """ RESTful CRUD controller """

    return crud_controller()

# -----------------------------------------------------------------------------
def education():
    """ RESTful CRUD controller """

    def prep(r):
        if r.method in ("create", "create.popup", "update", "update.popup"):
            # Coming from Profile page?
            person_id = get_vars.get("~.person_id", None)
            if person_id:
                field = s3db.pr_education.person_id
                field.default = person_id
                field.readable = field.writable = False

        return True
    s3.prep = prep

    return crud_controller()

# -----------------------------------------------------------------------------
def education_level():
    """ RESTful CRUD controller """

    return crud_controller()

# -----------------------------------------------------------------------------
def language():
    """ RESTful CRUD controller """

    def prep(r):
        if r.method in ("create", "create.popup", "update", "update.popup"):
            # Coming from Profile page?
            person_id = get_vars.get("~.person_id", None)
            if person_id:
                field = s3db.pr_language.person_id
                field.default = person_id
                field.readable = field.writable = False

        return True
    s3.prep = prep

    return crud_controller()

# -----------------------------------------------------------------------------
def occupation_type():
    """ Occupation Types: RESTful CRUD Controller """

    return crud_controller()

# -----------------------------------------------------------------------------
def pentity():
    """
        RESTful CRUD controller
        - limited to just search_ac for use in Autocompletes
    """

    s3.prep = lambda r: r.method == "search_ac"
    return crud_controller()

# -----------------------------------------------------------------------------
def affiliation():
    """ RESTful CRUD controller """

    return crud_controller()

# -----------------------------------------------------------------------------
def role():
    """ RESTful CRUD controller """

    return crud_controller()

# -----------------------------------------------------------------------------
def slot():
    """ RESTful CRUD controller """

    return crud_controller()

# -----------------------------------------------------------------------------
def date_formula():
    """ RESTful CRUD controller """

    return crud_controller()

# -----------------------------------------------------------------------------
def time_formula():
    """ RESTful CRUD controller """

    return crud_controller()

# =============================================================================
def filters():
    """
        RESTful CRUD controller for saved filters
    """

    return crud_controller("pr", "filter")

# =============================================================================
# Messaging
# =============================================================================
def compose():
    """ Send message to people/teams """

    return s3db.pr_compose()

# END =========================================================================
