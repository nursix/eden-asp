"""
    HRM module customisations for MRCMS

    License: MIT
"""

from gluon import current

from core import get_form_record_id

# -------------------------------------------------------------------------
def human_resource_onaccept(form):
    """
        Onaccept of staff record:
            - disable user account when no longer active
            - auto-expire ID cards when no longer active
    """

    record_id = get_form_record_id(form)
    if not record_id:
        return

    table = current.s3db.hrm_human_resource
    query = (table.id == record_id) & \
            (table.deleted == False)
    record = current.db(query).select(table.id,
                                      table.person_id,
                                      table.status,
                                      limitby = (0, 1),
                                      ).first()
    if record and record.status != 1:
        disable_user_account(record.person_id)
        from ..idcards import IDCard
        IDCard(record.person_id).auto_expire()

# -------------------------------------------------------------------------
def human_resource_ondelete(row):
    """
        Ondelete of staff record
            - disable user account
            - auto-expire all ID cards
    """

    try:
        person_id = row.person_id
    except AttributeError:
        return

    disable_user_account(person_id)
    from ..idcards import IDCard
    IDCard(person_id).auto_expire()

# -------------------------------------------------------------------------
def disable_user_account(person_id):
    """
        Disable the user account for a person

        Args:
            person_id: the person_id
    """

    db = current.db
    s3db = current.s3db
    auth = current.auth

    utable = auth.settings.table_user
    ptable = s3db.pr_person
    ltable = s3db.pr_person_user

    join = [ltable.on((ltable.user_id == utable.id) & \
                      (ltable.deleted == False)),
            ptable.on((ptable.pe_id == ltable.pe_id) & \
                      (ptable.id == person_id) & \
                      (ptable.deleted == False)),
            ]
    query = (utable.registration_key == None) | \
            (utable.registration_key == "")
    accounts = db(query).select(utable.id,
                                join = join,
                                )
    for account in accounts:
        account.update_record(registration_key="disabled")
    if accounts:
        current.response.warning = current.T("User Account has been Disabled")

# -------------------------------------------------------------------------
def hrm_human_resource_resource(r, tablename):

    T = current.T
    s3db = current.s3db

    table = s3db.hrm_human_resource
    field = table.job_title_id
    field.comment = None

    phone_label = current.deployment_settings.get_ui_label_mobile_phone()
    list_fields = ["organisation_id",
                   "person_id",
                   "job_title_id",
                   "site_id",
                   (T("Email"), "person_id$email.value"),
                   (phone_label, "person_id$phone.value"),
                   "status",
                   ]

    s3db.configure("hrm_human_resource",
                   list_fields = list_fields,
                   )

    # Configure components to inherit realm_entity from person
    s3db.configure("pr_person",
                   realm_components = ("person_details",
                                       "contact",
                                       "address",
                                       "identity",
                                       ),
                   )

    s3db.add_custom_callback("hrm_human_resource",
                             "onaccept",
                             human_resource_onaccept,
                             )

# -------------------------------------------------------------------------
def hrm_human_resource_controller(**attr):

    s3 = current.response.s3

    # Custom prep
    standard_prep = s3.prep
    def prep(r):
        # Call standard prep
        result = standard_prep(r) if callable(standard_prep) else True

        if not r.component:
            current.deployment_settings.ui.open_read_first = True

            # TODO Adjust filters

            # Not insertable here, only from org-tab
            r.resource.configure(insertable=False)

        elif r.component_name == "identity" and r.method == "generate":
            # Require OrgAdmin role for staff ID generation
            if not current.auth.s3_has_role("ORG_ADMIN"):
                r.unauthorised()

        return result

    s3.prep = prep

    return attr

# END =========================================================================
