"""
    HRM module customisations for RLPPTM

    License: MIT
"""

from gluon import current
from core import get_form_record_id

# -------------------------------------------------------------------------
def human_resource_onvalidation(form):
    """
        Form validation for human resources
            - make sure there is only one HR record per person
    """

    db = current.db
    s3db = current.s3db

    form_vars = form.vars
    record_id = get_form_record_id(form)

    person_id = form_vars.get("person_id")
    table = s3db.hrm_human_resource

    if person_id:
        query = (table.person_id == person_id) & \
                (table.deleted == False)
        if record_id:
            query &= (table.id != record_id)
        duplicate = db(query).select(table.id, limitby=(0, 1)).first()
        if duplicate:
            form.errors.person_id = current.T("Person already has a staff record")
            return

    if "org_contact" in form_vars and form_vars["org_contact"]:

        if not person_id and record_id:
            # Lookup the person_id
            record = db(table.id == record_id).select(table.person_id,
                                                      limitby = (0, 1),
                                                      ).first()
            if record:
                person_id = record.person_id

        if person_id:
            # Check completeness of data
            from ..models.org import ProviderRepresentative
            accepted, missing = ProviderRepresentative.check_data(person_id)
            if not accepted and missing:
                msg = current.T("Data incomplete (%(details)s)") % \
                        {"details": ", ".join(missing)}
                form.errors["org_contact"] = msg

# -------------------------------------------------------------------------
def human_resource_onaccept(form):
    """
        Onaccept-routine for human resources:
            - auto-create/update representative record if org contact
    """

    db = current.db
    s3db = current.s3db

    record_id = get_form_record_id(form)
    if not record_id:
        return

    # Get the record
    table = s3db.hrm_human_resource
    query = (table.id == record_id)
    record = db(query).select(table.id,
                              table.person_id,
                              table.organisation_id,
                              table.org_contact,
                              table.status,
                              limitby = (0, 1),
                              ).first()
    if not record:
        return

    if record.org_contact and record.status != 1:
        # Only active staff can be org contacts
        record.update_record(org_contact=False)

    # Get corresponding representative record
    rtable = s3db.org_representative
    query = (rtable.person_id == record.person_id) & \
            (rtable.deleted == False)
    representative = db(query).select(rtable.id,
                                      rtable.organisation_id,
                                      limitby = (0, 1),
                                      ).first()

    representative_id = representative.id if representative else None

    if record.org_contact and not representative:
        # Create new record with defaults
        representative = {"person_id": record.person_id,
                          "organisation_id": record.organisation_id,
                          }
        representative_id = representative["id"] = rtable.insert(**representative)

        # Postprocess new record
        s3db.update_super(rtable, representative)
        current.auth.s3_set_record_owner(rtable, representative_id)
        s3db.onaccept(rtable, representative, method="create")

    if representative_id:
        # Update verification status
        from ..models.org import ProviderRepresentative
        ProviderRepresentative(representative_id).update_verification()

# -------------------------------------------------------------------------
def human_resource_ondelete(row):
    """
        Ondelete of staff record
            - update representative verification if one exists
    """

    rtable = current.s3db.org_representative
    query = (rtable.person_id == row.person_id) & \
            (rtable.deleted == False)
    row = current.db(query).select(rtable.id,
                                   limitby = (0, 1),
                                   ).first()
    if row:
        from ..models.org import ProviderRepresentative
        ProviderRepresentative(row.id).update_verification()

# -------------------------------------------------------------------------
def hrm_human_resource_resource(r, tablename):

    s3db = current.s3db

    from ..config import TESTSTATIONS

    # Determine user role
    has_role = current.auth.s3_has_role

    is_teststation_admin = has_role("ORG_ADMIN")
    managed_orgs = None

    if is_teststation_admin:
        from ..helpers import get_managed_orgs
        managed_orgs = get_managed_orgs(TESTSTATIONS)
        if not managed_orgs:
            is_teststation_admin = False

    is_org_group_admin = False if is_teststation_admin else has_role("ORG_GROUP_ADMIN")

    resource = organisation_id = None
    if is_teststation_admin or is_org_group_admin:
        # Determine organisation_id
        record = r.record
        master = r.tablename
        if master == "hrm_human_resource":
            resource = r.resource
            organisation_id = record.organisation_id if record else None

        elif master == "org_organisation":
            resource = r.component
            organisation_id = record.id

        elif master == "pr_person":
            resource = r.component
            table = resource.table
            if r.component_id:
                query = (table.id == r.component_id)
            else:
                query = (table.person_id == record.id)
            row = current.db(query).select(table.organisation_id,
                                           limitby = (0, 1),
                                           ).first()
            organisation_id = row.organisation_id if row else None

    table = resource.table if resource else s3db.hrm_human_resource

    if organisation_id:
        # Check if organisation is a (managed) test station
        if is_teststation_admin and organisation_id in managed_orgs:
            show_org_contact = org_contact_writable = True
        else:
            from ..helpers import is_org_group
            show_org_contact = is_org_group(organisation_id, TESTSTATIONS)
            org_contact_writable = False
    else:
        show_org_contact = org_contact_writable = False

    if show_org_contact:
        # Expose org_contact field
        org_contact = "org_contact"

        field = table.org_contact
        field.readable = True
        field.writable = org_contact_writable
        field.label = current.T("Legal Representative")

        if is_teststation_admin:
            from core import WithAdvice
            org_contact = WithAdvice("org_contact",
                                     text = ("hrm",
                                             "human_resource",
                                             "OrgContactIntro",
                                             ),
                                     below = True,
                                     cmsxml = True,
                                     )
    else:
        org_contact = None

    field = table.organisation_id
    field.writable = False
    field.comment = None

    # Use custom-form for HRs
    from core import CustomForm
    s3db.configure("hrm_human_resource",
                   crud_form = CustomForm(
                                    "person_id",
                                    "organisation_id",
                                    "site_id",
                                    org_contact,
                                    "job_title_id",
                                    "start_date",
                                    "end_date",
                                    "status",
                                    ),
                   )

    # Configure custom callbacks
    s3db.add_custom_callback("hrm_human_resource",
                             "onvalidation",
                             human_resource_onvalidation,
                             )
    s3db.add_custom_callback("hrm_human_resource",
                             "onaccept",
                             human_resource_onaccept,
                             )
    s3db.add_custom_callback("hrm_human_resource",
                             "ondelete",
                             human_resource_ondelete,
                             )

# -------------------------------------------------------------------------
def hrm_human_resource_controller(**attr):

    T = current.T
    s3db = current.s3db

    s3 = current.response.s3

    # Custom prep
    standard_prep = s3.prep
    def prep(r):
        # Restrict data formats
        from ..helpers import restrict_data_formats
        restrict_data_formats(r)

        # Call standard prep
        result = standard_prep(r) if callable(standard_prep) else True

        resource = r.resource

        is_org_group_admin = current.auth.s3_has_role("ORG_GROUP_ADMIN")

        # Configure components to inherit realm_entity from person
        s3db.configure("pr_person",
                       realm_components = ("person_details",
                                           "contact",
                                           "address",
                                           ),
                       )
        phone_label = current.deployment_settings.get_ui_label_mobile_phone()
        if r.representation in ("xlsx", "xls"):
            s3db.add_components("pr_pentity",
                                pr_address = ({"name": "home_address",
                                               "joinby": "pe_id",
                                               "filterby": {"type": 1},
                                               "multiple": False,
                                               }),
                                )

            # Site obsolete-flag representation
            stable = s3db.org_site
            field = stable.obsolete
            field.label = T("Closed")
            field.represent = lambda v, row=None: T("yes") if v else "-"

            list_fields = ["organisation_id",
                           "site_id",
                           "site_id$obsolete",
                           "site_id$location_id$addr_street",
                           "site_id$location_id$L4",
                           "site_id$location_id$L3",
                           "site_id$location_id$addr_postcode",
                           "person_id",
                           "job_title_id",
                           (T("Email"), "person_id$email.value"),
                           (phone_label, "person_id$phone.value"),
                           (T("Home Address"), "person_id$home_address.location_id"),
                           "status",
                           ]
        else:
            list_fields = ["organisation_id",
                           "person_id",
                           "job_title_id",
                           "site_id",
                           (T("Email"), "person_id$email.value"),
                           (phone_label, "person_id$phone.value"),
                           "status",
                           ]

        from core import OptionsFilter, TextFilter, get_filter_options
        filter_widgets = [
            TextFilter(["person_id$first_name",
                        "person_id$last_name",
                        "organisation_id$name",
                        "person_id$email.value",
                        "person_id$phone.value",
                        ],
                       label = T("Search"),
                       ),
            OptionsFilter("job_title_id",
                          options = lambda: get_filter_options("hrm_job_title"),
                          hidden = True,
                          ),
            ]
        if is_org_group_admin:
            filter_widgets[1:1] = [
                OptionsFilter(
                    "organisation_id$group__link.group_id",
                    label = T("Organization Group"),
                    options = lambda: get_filter_options("org_group"),
                    ),
                OptionsFilter(
                    "organisation_id$organisation_type__link.organisation_type_id",
                    label = T("Organization Type"),
                    options = lambda: get_filter_options("org_organisation_type"),
                    hidden = True,
                    ),
                ]

        resource.configure(filter_widgets = filter_widgets,
                           list_fields = list_fields,
                           )

        return result
    s3.prep = prep

    return attr

# END =========================================================================
