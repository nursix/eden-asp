"""
    Custom rheaders for BETRA

    License: MIT
"""

from gluon import current, A, DIV, I, URL, SPAN

from core import S3ResourceHeader, s3_fullname, s3_rheader_resource

from .helpers import client_name_age, hr_details

# =============================================================================
def dvr_rheader(r, tabs=None):
    """ Custom resource headers for DVR module """

    auth = current.auth
    has_permission = auth.s3_has_permission

    if r.representation != "html":
        # Resource headers only used in interactive views
        return None

    tablename, record = s3_rheader_resource(r)
    if tablename != r.tablename:
        resource = current.s3db.resource(tablename, id=record.id)
    else:
        resource = r.resource

    rheader = None
    rheader_fields = []
    rheader_title = None

    if record:
        T = current.T

        if tablename == "pr_person":
            # Case file

            # "Case Archived" hint
            hint = lambda record: SPAN(T("Invalid Case"), _class="invalid-case")

            c = r.controller
            if not tabs:
                tabs = [(T("Basic Details"), None),
                        (T("Contact Information"), "contacts"),
                        (T("Needs"), "case_activity"),
                        (T("Tasks"), "case_task"),
                        (T("Photos"), "image"),
                        (T("Documents"), "document/"),
                        (T("Notes"), "case_note"),
                        ]

            case = resource.select(["dvr_case.status_id",
                                    "dvr_case.archived",
                                    "dvr_case.reference",
                                    "first_name",
                                    "last_name",
                                    "person_details.nationality",
                                    "shelter_registration.shelter_id",
                                    "shelter_registration.shelter_unit_id",
                                    #"absence",
                                    ],
                                    represent = True,
                                    raw_data = True,
                                    ).rows

            if case:
                # Extract case data
                case = case[0]
                raw = case["_row"]
                case_reference = lambda row: case["dvr_case.reference"]
                case_status = lambda row: case["dvr_case.status_id"]
            else:
                # Target record exists, but doesn't match filters
                return None

            rheader_fields = [[(T("ID"), "pe_label"),
                               (T("Principal Ref.No."), case_reference),
                               ],
                              ["date_of_birth",
                               (T("Case Status"), case_status),
                               ],
                              ]

            if raw["dvr_case.archived"]:
                rheader_fields.insert(0, [(None, hint)])
                links = None
            else:
                # Link to switch case file perspective
                links = DIV(_class="case-file-perspectives")
                render_switch = False
                record_id = record.id
                perspectives = (("dvr", T("Manage")),
                                )
                icon = "arrow-circle-left"
                for cntr, label in perspectives:
                    if c == cntr:
                        link = SPAN(I(_class = "fa fa-arrow-circle-down"),
                                    label,
                                    _class="current-perspective",
                                    )
                        icon = "arrow-circle-right"
                    elif has_permission("read", "pr_person", c=cntr, f="person", record_id=record_id):
                        render_switch = True
                        link = A(I(_class = "fa fa-%s" % icon),
                                    label,
                                    _href = URL(c=cntr, f="person", args=[record_id]),
                                    )
                    else:
                        continue
                    links.append(link)
                if not render_switch:
                    links = None

            rheader_title = client_name_age

            # Generate rheader XML
            rheader = S3ResourceHeader(rheader_fields, tabs, title=rheader_title)
            rheader = rheader(r, table=resource.table, record=record)

            # Add profile picture
            from core import s3_avatar_represent
            record_id = record.id
            # TODO this should only be a link in Manage-perspective
            rheader.insert(0, A(s3_avatar_represent(record_id,
                                                    "pr_person",
                                                    _class = "rheader-avatar",
                                                    ),
                                _href=URL(f = "person",
                                            args = [record_id, "image"],
                                            vars = r.get_vars,
                                            ),
                                )
                            )

            # Insert perspective switch
            if links:
                rheader.insert(0, links)

            return rheader

        elif tablename == "dvr_task":

            if not tabs:
                tabs = [(T("Basic Details"), None),
                        ]

            rheader_fields = [[(T("Client"), "person_id"), (T("Staff"), "human_resource_id")],
                              ["status", "due_date"],
                              ]
            rheader_title = "name"

        rheader = S3ResourceHeader(rheader_fields, tabs, title=rheader_title)
        rheader = rheader(r, table=resource.table, record=record)

    return rheader

# =============================================================================
def org_rheader(r, tabs=None):
    """ Custom resource headers for ORG module """

    if r.representation != "html":
        # Resource headers only used in interactive views
        return None

    tablename, record = s3_rheader_resource(r)
    if tablename != r.tablename:
        resource = current.s3db.resource(tablename, id=record.id)
    else:
        resource = r.resource

    rheader = None
    rheader_fields = []

    if record:
        T = current.T
        auth = current.auth

        if tablename == "org_group":

            if not tabs:
                tabs = [(T("Basic Details"), None),
                        (T("Member Organizations"), "organisation"),
                        (T("Documents"), "document"),
                        ]

            rheader_fields = []
            rheader_title = "name"

        elif tablename == "org_organisation":

            if not tabs:
                # General tabs
                tabs = [(T("Basic Details"), None),
                        #(T("Offices"), "office"),
                        ]

                # Role/permission-dependent tabs
                if auth.s3_has_permission("read", "pr_person", c="hrm", f="person"):
                    tabs.append((T("Staff"), "human_resource"))

                # Documents tabs
                tabs += [(T("Documents"), "document"),
                         #(T("Templates"), "template"),
                         ]

            rheader_fields = []
            rheader_title = "name"

        elif tablename == "org_facility":

            if not tabs:
                tabs = [(T("Basic Details"), None),
                        ]

            rheader_fields = [["name", "email"],
                              ["organisation_id", "phone1"],
                              ["location_id", "phone2"],
                              ]
            rheader_title = None

        rheader = S3ResourceHeader(rheader_fields, tabs, title=rheader_title)
        rheader = rheader(r, table=resource.table, record=record)

    return rheader

# =============================================================================
def hrm_rheader(r, tabs=None):
    """ Custom resource headers for HRM """

    if r.representation != "html":
        # Resource headers only used in interactive views
        return None

    tablename, record = s3_rheader_resource(r)
    if tablename != r.tablename:
        resource = current.s3db.resource(tablename, id=record.id)
    else:
        resource = r.resource

    rheader = None
    rheader_fields = []

    if record:

        T = current.T

        if tablename == "pr_person":
            # Staff file

            tabs = [(T("Person Details"), None, {}, "read"),
                    (T("Contact Information"), "contacts"),
                    (T("Address"), "address"),
                    (T("ID"), "identity"),
                    (T("Staff Record"), "human_resource"),
                    (T("Photos"), "image"),
                    ]

            details = hr_details(record)
            rheader_fields = [[(T("User Account"), lambda i: details["account"])],
                              ]

            organisation = details["organisation"]
            if organisation:
                rheader_fields[0].insert(0, (T("Organization"), lambda i: organisation))

            rheader_title = s3_fullname

            rheader = S3ResourceHeader(rheader_fields, tabs, title=rheader_title)
            rheader = rheader(r, table=resource.table, record=record)

            # Add profile picture
            from core import s3_avatar_represent
            record_id = record.id
            rheader.insert(0, A(s3_avatar_represent(record_id,
                                                    "pr_person",
                                                    _class = "rheader-avatar",
                                                    ),
                                _href=URL(f = "person",
                                          args = [record_id, "image"],
                                          vars = r.get_vars,
                                          ),
                                ))

    return rheader

# =============================================================================
def default_rheader(r, tabs=None):
    """ Custom resource header for user profile """

    if r.representation != "html":
        # Resource headers only used in interactive views
        return None

    tablename, record = s3_rheader_resource(r)
    if tablename != r.tablename:
        resource = current.s3db.resource(tablename, id=record.id)
    else:
        resource = r.resource

    rheader = None
    rheader_fields = []

    if record:

        T = current.T

        if tablename == "pr_person":
            # Personal profile
            tabs = [(T("Person Details"), None),
                    (T("User Account"), "user_profile"),
                    (T("ID"), "identity"),
                    (T("Contact Information"), "contacts"),
                    (T("Address"), "address"),
                    (T("Staff Record"), "human_resource"),
                    ]
            rheader_fields = []
            rheader_title = s3_fullname

            rheader = S3ResourceHeader(rheader_fields, tabs, title=rheader_title)
            rheader = rheader(r, table=resource.table, record=record)

    return rheader

# END =========================================================================
