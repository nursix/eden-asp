"""
    PR module customisations for RLPPTM

    License: MIT
"""

from gluon import current, IS_NOT_EMPTY

from core import get_form_record_id

# -----------------------------------------------------------------------------
def person_postprocess(form):
    """
        Postprocess person-form
            - update representative verification status
    """

    record_id = get_form_record_id(form)
    if not record_id:
        return

    db = current.db
    s3db = current.s3db

    # Lookup all representative records for this person
    table = s3db.org_representative
    query = (table.person_id == record_id) & \
            (table.deleted == False)
    rows = db(query).select(table.id)

    from ..models.org import ProviderRepresentative
    for row in rows:
        ProviderRepresentative(row.id).update_verification()

# -----------------------------------------------------------------------------
def pr_person_resource(r, tablename):

    s3db = current.s3db

    # Configure components to inherit realm_entity from person
    s3db.configure("pr_person",
                    realm_components = ("person_details",
                                        "contact",
                                        "address",
                                        ),
                    )

# -----------------------------------------------------------------------------
def pr_person_controller(**attr):

    s3 = current.response.s3
    settings = current.deployment_settings

    T = current.T

    if current.request.controller == "hrm":
        current.s3db.add_components("pr_person",
                                    org_representative = {"joinby": "person_id",
                                                          "multiple": False,
                                                          },
                                    )

    # Custom prep
    standard_prep = s3.prep
    def prep(r):
        # Restrict data formats
        from ..helpers import restrict_data_formats
        restrict_data_formats(r)

        # Call standard prep
        result = standard_prep(r) if callable(standard_prep) else True

        from core import CustomForm, StringTemplateParser

        # Determine order of name fields
        NAMES = ("first_name", "middle_name", "last_name")
        keys = StringTemplateParser.keys(settings.get_pr_name_format())
        name_fields = [fn for fn in keys if fn in NAMES]

        controller = r.controller
        if controller in ("default", "hrm") and not r.component:
            # Personal profile (default/person) or staff
            resource = r.resource

            # Last name is required
            table = resource.table
            table.last_name.requires = IS_NOT_EMPTY()

            # Make place of birth accessible
            details = resource.components.get("person_details")
            if details:
                field = details.table.place_of_birth
                field.readable = field.writable = True

            # Custom Form
            crud_fields = name_fields + ["date_of_birth",
                                         "person_details.place_of_birth",
                                         "gender",
                                         ]

            r.resource.configure(crud_form = CustomForm(*crud_fields,
                                                        postprocess = person_postprocess,
                                                        ),
                                 deletable = False,
                                 )

        if r.component_name == "address":
            ctable = r.component.table

            # Configure location selector and geocoder
            from core import LocationSelector
            field = ctable.location_id
            field.widget = LocationSelector(levels = ("L1", "L2", "L3", "L4"),
                                            required_levels = ("L1", "L2", "L3"),
                                            show_address = True,
                                            show_postcode = True,
                                            show_map = True,
                                            )
            s3.scripts.append("/%s/static/themes/RLP/js/geocoderAllStates.js" % r.application)
            s3.scripts.append("/%s/static/themes/RLP/js/geocoderPlugin.js" % r.application)

        elif r.component_name == "human_resource":

            phone_label = settings.get_ui_label_mobile_phone()
            r.component.configure(list_fields= ["job_title_id",
                                                "site_id",
                                                (T("Email"), "person_id$email.value"),
                                                (phone_label, "person_id$phone.value"),
                                                "status",
                                                ],
                                  deletable = False,
                                  )
            s3.crud_strings["hrm_human_resource"]["label_list_button"] = T("List Staff Records")

        elif r.component_name == "representative":

            from ..models.org import ProviderRepresentative
            ProviderRepresentative.configure(r)

        return result
    s3.prep = prep

    # Custom rheader
    from ..rheaders import rlpptm_profile_rheader, rlpptm_hr_rheader
    controller = current.request.controller
    if controller == "default":
        attr["rheader"] = rlpptm_profile_rheader
    elif controller == "hrm":
        attr["rheader"] = rlpptm_hr_rheader

    return attr

# -----------------------------------------------------------------------------
def update_representative(tablename, record_id, pe_id=None):
    """
        Update representative verification status upon update of relevant
        component data (e.g. address, contact)

        Args:
            tablename: the name of the component table
            record_id: the component record ID
            pe_id: the pe_id of the person, if known (prevents lookup)
    """

    db = current.db
    s3db = current.s3db

    # Retrieve pe_id if not provided
    if not pe_id:
        table = s3db[tablename]
        row = db(table.id == record_id).select(table.pe_id,
                                               limitby = (0, 1),
                                               ).first()
        pe_id = row.pe_id if row else None
    if not pe_id:
        return

    # Get all representative records for this PE
    ptable = s3db.pr_person
    rtable = s3db.org_representative
    join = ptable.on((ptable.id == rtable.person_id) & \
                     (ptable.pe_id == pe_id))
    query = (rtable.deleted == False)
    rows = db(query).select(rtable.id, join=join)

    # Update verifications
    if rows:
        from ..models.org import ProviderRepresentative
        if tablename == "pr_address":
            show_errors = "address_data"
        elif tablename == "pr_contact":
            show_errors = "contact_data"
        else:
            show_errors = False
        for row in rows:
            ProviderRepresentative(row.id).update_verification(show_errors=show_errors)

# -----------------------------------------------------------------------------
def address_ondelete(row):

    update_representative(current.s3db.pr_address, row.id, pe_id=row.pe_id)

# -----------------------------------------------------------------------------
def address_onaccept(form):

    record_id = get_form_record_id(form)
    if not record_id:
        return
    update_representative(current.s3db.pr_address, record_id)

# -----------------------------------------------------------------------------
def pr_address_resource(r, tablename):

    s3db = current.s3db

    s3db.add_custom_callback("pr_address", "onaccept", address_onaccept)
    s3db.add_custom_callback("pr_address", "ondelete", address_ondelete)

# -----------------------------------------------------------------------------
def contact_ondelete(row):

    update_representative(current.s3db.pr_contact, row.id, pe_id=row.pe_id)

# -----------------------------------------------------------------------------
def contact_onaccept(form):

    record_id = get_form_record_id(form)
    if not record_id:
        return
    update_representative(current.s3db.pr_contact, record_id)

# -----------------------------------------------------------------------------
def pr_contact_resource(r, tablename):

    s3db = current.s3db

    s3db.add_custom_callback("pr_contact", "onaccept", contact_onaccept)
    s3db.add_custom_callback("pr_contact", "ondelete", contact_ondelete)

# END =========================================================================
