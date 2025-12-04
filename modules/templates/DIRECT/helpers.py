"""
    Helper functions and classes for RLPPTM

    License: MIT
"""

from gluon import current, URL, \
                  IS_IN_SET, A, DIV, H4, I, SPAN, TABLE, TD, TR

from core import WorkflowOptions

# =============================================================================
def get_role_realms(role):
    """
        Get all realms for which a role has been assigned

        Args:
            role: the role ID or role UUID

        Returns:
            list of pe_ids the current user has the role for,
            None if the role is assigned site-wide, or an
            empty list if the user does not have the role, or
            no realm for the role
    """

    db = current.db
    auth = current.auth
    s3db = current.s3db

    if isinstance(role, str):
        gtable = auth.settings.table_group
        query = (gtable.uuid == role) & \
                (gtable.deleted == False)
        row = db(query).select(gtable.id,
                               cache = s3db.cache,
                               limitby = (0, 1),
                               ).first()
        role_id = row.id if row else None
    else:
        role_id = role

    role_realms = []
    user = auth.user
    if user:
        role_realms = user.realms.get(role_id, role_realms)

    return role_realms

# =============================================================================
def get_managed_facilities(role="ORG_ADMIN", public_only=True, cacheable=True):
    """
        Get test stations managed by the current user

        Args:
            role: the user role to consider
            public_only: only include sites with PUBLIC=Y tag

        Returns:
            list of site_ids
    """


    s3db = current.s3db

    ftable = s3db.org_facility
    query = (ftable.obsolete == False) & \
            (ftable.deleted == False)

    realms = get_role_realms(role)
    if realms:
        query = (ftable.realm_entity.belongs(realms)) & query
    elif realms is not None:
        # User does not have the required role, or at least not for any realms
        return realms

    if public_only:
        atable = s3db.org_site_approval
        join = atable.on((atable.site_id == ftable.site_id) & \
                         (atable.public == "Y") & \
                         (atable.deleted == False))
    else:
        join = None

    sites = current.db(query).select(ftable.site_id,
                                     cache = s3db.cache if cacheable else None,
                                     join = join,
                                     )
    return [s.site_id for s in sites]

# =============================================================================
def get_managed_orgs(group=None, cacheable=True):
    """
        Get organisations managed by the current user

        Args:
            group: the organisation group
            cacheable: whether the result can be cached

        Returns:
            list of organisation_ids
    """

    s3db = current.s3db

    otable = s3db.org_organisation
    query = (otable.deleted == False)

    realms = get_role_realms("ORG_ADMIN")
    if realms:
        query = (otable.realm_entity.belongs(realms)) & query
    elif realms is not None:
        # User does not have the required role, or at least not for any realms
        return []

    if group:
        gtable = s3db.org_group
        mtable = s3db.org_group_membership
        join = [gtable.on((mtable.organisation_id == otable.id) & \
                          (mtable.deleted == False) & \
                          (gtable.id == mtable.group_id) & \
                          (gtable.name == group)
                          )]
    else:
        join = None

    orgs = current.db(query).select(otable.id,
                                    cache = s3db.cache if cacheable else None,
                                    join = join,
                                    )
    return [o.id for o in orgs]

# =============================================================================
def get_org_accounts(organisation_id):
    """
        Get all user accounts linked to an organisation

        Args:
            organisation_id: the organisation ID

        Returns:
            tuple (active, disabled, invited), each being
            a list of user accounts (auth_user Rows)
    """

    auth = current.auth
    s3db = current.s3db

    utable = auth.settings.table_user
    oltable = s3db.org_organisation_user
    pltable = s3db.pr_person_user

    join = oltable.on((oltable.user_id == utable.id) & \
                      (oltable.deleted == False))
    left = pltable.on((pltable.user_id == utable.id) & \
                      (pltable.deleted == False))
    query = (oltable.organisation_id == organisation_id)
    rows = current.db(query).select(utable.id,
                                    utable.first_name,
                                    utable.last_name,
                                    utable.email,
                                    utable.registration_key,
                                    pltable.pe_id,
                                    join = join,
                                    left = left,
                                    )

    active, disabled, invited = [], [], []
    for row in rows:
        user = row[utable]
        person_link = row.pr_person_user
        if person_link.pe_id:
            if user.registration_key:
                disabled.append(user)
            else:
                active.append(user)
        else:
            invited.append(user)

    return active, disabled, invited

# -----------------------------------------------------------------------------
def get_role_users(role_uid, pe_id=None, organisation_id=None):
    """
        Look up users with a certain user role for a certain organisation

        Args:
            role_uid: the role UUID
            pe_id: the pe_id of the organisation, or
            organisation_id: the organisation_id

        Returns:
            a dict {user_id: pe_id} of all active users with this
            role for the organisation
    """

    db = current.db

    auth = current.auth
    s3db = current.s3db

    if not pe_id and organisation_id:
        # Look up the realm pe_id from the organisation
        otable = s3db.org_organisation
        query = (otable.id == organisation_id) & \
                (otable.deleted == False)
        organisation = db(query).select(otable.pe_id,
                                        limitby = (0, 1),
                                        ).first()
        pe_id = organisation.pe_id if organisation else None

    # Get all users with this realm as direct OU ancestor
    from s3db.pr import pr_realm_users
    users = pr_realm_users(pe_id) if pe_id else None
    if users:
        # Look up those among the realm users who have
        # the role for either pe_id or for their default realm
        gtable = auth.settings.table_group
        mtable = auth.settings.table_membership
        ltable = s3db.pr_person_user
        utable = auth.settings.table_user
        join = [mtable.on((mtable.user_id == ltable.user_id) & \
                          ((mtable.pe_id == None) | (mtable.pe_id == pe_id)) & \
                          (mtable.deleted == False)),
                gtable.on((gtable.id == mtable.group_id) & \
                          (gtable.uuid == role_uid)),
                # Only verified+active accounts:
                utable.on((utable.id == mtable.user_id) & \
                          ((utable.registration_key == None) | \
                           (utable.registration_key == "")))
                ]
        query = (ltable.user_id.belongs(set(users.keys()))) & \
                (ltable.deleted == False)
        rows = db(query).select(ltable.user_id,
                                ltable.pe_id,
                                join = join,
                                )
        users = {row.user_id: row.pe_id for row in rows}

    return users if users else None

# -----------------------------------------------------------------------------
def get_role_emails(role_uid, pe_id=None, organisation_id=None):
    """
        Look up the emails addresses of users with a certain user role
        for a certain organisation

        Args:
            role_uid: the role UUID
            pe_id: the pe_id of the organisation, or
            organisation_id: the organisation_id

        Returns:
            a list of email addresses
    """

    contacts = None

    users = get_role_users(role_uid,
                           pe_id = pe_id,
                           organisation_id = organisation_id,
                           )

    if users:
        # Look up their email addresses
        ctable = current.s3db.pr_contact
        query = (ctable.pe_id.belongs(set(users.values()))) & \
                (ctable.contact_method == "EMAIL") & \
                (ctable.deleted == False)
        rows = current.db(query).select(ctable.value,
                                        orderby = ~ctable.priority,
                                        )
        contacts = list(set(row.value for row in rows))

    return contacts if contacts else None

# -----------------------------------------------------------------------------
def get_role_hrs(role_uid, pe_id=None, organisation_id=None):
    """
        Look up the HR records of users with a certain user role
        for a certain organisation

        Args:
            role_uid: the role UUID
            pe_id: the pe_id of the organisation, or
            organisation_id: the organisation_id

        Returns:
            a list of hrm_human_resource IDs
    """

    hr_ids = None

    users = get_role_users(role_uid,
                           pe_id = pe_id,
                           organisation_id = organisation_id,
                           )

    if users:
        # Look up their HR records
        s3db = current.s3db
        ptable = s3db.pr_person
        htable = s3db.hrm_human_resource
        join = htable.on((htable.person_id == ptable.id) & \
                         (htable.deleted == False))
        query = (ptable.pe_id.belongs(set(users.values()))) & \
                (ptable.deleted == False)
        rows = current.db(query).select(htable.id,
                                        join = join,
                                        )
        hr_ids = list(set(row.id for row in rows))

    return hr_ids if hr_ids else None

# -----------------------------------------------------------------------------
def is_org_group(organisation_id, group, cacheable=True):
    """
        Check whether an organisation is member of an organisation group

        Args:
            organisation_id: the organisation ID
            group: the organisation group name

        Returns:
            boolean
    """

    s3db = current.s3db

    gtable = s3db.org_group
    mtable = s3db.org_group_membership
    join = [gtable.on((gtable.id == mtable.group_id) & \
                      (gtable.name == group)
                      )]
    query = (mtable.organisation_id == organisation_id) & \
            (mtable.deleted == False)
    row = current.db(query).select(mtable.id,
                                   cache = s3db.cache,
                                   join = join,
                                   limitby = (0, 1),
                                   ).first()
    return bool(row)

# -----------------------------------------------------------------------------
def is_org_type_tag(organisation_id, tag, value=None):
    """
        Check if a type of an organisation has a certain tag

        Args:
            organisation_id: the organisation ID
            tag: the tag name
            value: the tag value (optional)

        Returns:
            boolean
    """

    db = current.db
    s3db = current.s3db

    ltable = s3db.org_organisation_organisation_type
    ttable = s3db.org_organisation_type_tag

    joinq = (ttable.organisation_type_id == ltable.organisation_type_id) & \
            (ttable.tag == tag)
    if value is not None:
        joinq &= (ttable.value == value)

    join = ttable.on(joinq & (ttable.deleted == False))
    query = (ltable.organisation_id == organisation_id) & \
            (ltable.deleted == False)
    row = db(query).select(ttable.id, join=join, limitby=(0, 1)).first()
    return bool(row)

# =============================================================================
# Helpers for HRM rheader
# =============================================================================
def account_status(record, represent=True):
    """
        Checks the status of the user account for a person

        Args:
            record: the person record
            represent: represent the result as workflow option

        Returns:
            workflow option HTML if represent=True, otherwise boolean
    """

    db = current.db
    s3db = current.s3db

    ltable = s3db.pr_person_user
    utable = current.auth.table_user()

    query = (ltable.pe_id == record.pe_id) & \
            (ltable.deleted == False) & \
            (utable.id == ltable.user_id)

    account = db(query).select(utable.id,
                               utable.registration_key,
                               #cache = s3db.cache,
                               limitby = (0, 1),
                               ).first()

    if account:
        status = "DISABLED" if account.registration_key else "ACTIVE"
    else:
        status = "N/A"

    if represent:
        represent = WorkflowOptions(("N/A", "nonexistent", "grey"),
                                    ("DISABLED", "disabled##account", "red"),
                                    ("ACTIVE", "active", "green"),
                                    ).represent
        status = represent(status)

    return status

# -----------------------------------------------------------------------------
def hr_details(record):
    """
        Looks up relevant HR details for a person

        Args:
            record: the pr_person record in question

        Returns:
            dict {"organisation": organisation name,
                  "account": account status,
                  }

        Note:
            all data returned are represented (not raw data)
    """

    db = current.db
    s3db = current.s3db

    person_id = record.id

    # Get HR record
    htable = s3db.hrm_human_resource
    query = (htable.person_id == person_id)

    hr_id = current.request.get_vars.get("human_resource.id")
    if hr_id:
        query &= (htable.id == hr_id)
    query &= (htable.deleted == False)

    rows = db(query).select(htable.organisation_id,
                            htable.org_contact,
                            htable.status,
                            orderby = htable.created_on,
                            )
    if not rows:
        human_resource = None
    elif len(rows) > 1:
        rrows = rows
        rrows = rrows.find(lambda row: row.status == 1) or rrows
        rrows = rrows.find(lambda row: row.org_contact) or rrows
        human_resource = rrows.first()
    else:
        human_resource = rows.first()

    output = {"organisation": "",
              "account": account_status(record),
              }

    if human_resource:
        otable = s3db.org_organisation

        # Link to organisation
        query = (otable.id == human_resource.organisation_id)
        organisation = db(query).select(otable.id,
                                        otable.name,
                                        limitby = (0, 1),
                                        ).first()
        output["organisation"] = A(organisation.name,
                                   _href = URL(c = "org",
                                               f = "organisation",
                                               args = [organisation.id],
                                               ),
                                   )
    return output

# -----------------------------------------------------------------------------
def restrict_data_formats(r):
    """
        Restrict data exports (prevent S3XML/S3JSON of records)

        Args:
            r: the CRUDRequest
    """

    settings = current.deployment_settings
    allowed = ("html", "iframe", "popup", "aadata", "plain", "geojson", "pdf", "xlsx")
    if r.record:
        allowed += ("card",)
    if r.method in ("report", "timeplot", "filter", "lookup", "info", "validate", "verify"):
        allowed += ("json",)
    elif r.method == "options":
        allowed += ("s3json",)
    settings.ui.export_formats = ("pdf", "xlsx")
    if r.representation not in allowed:
        r.error(403, current.ERROR.NOT_PERMITTED)

# -----------------------------------------------------------------------------
def assign_pending_invoices(billing_id, organisation_id=None, invoice_id=None):
    """
        Auto-assign pending invoices in a billing to accountants,
        taking into account their current workload

        Args:
            billing_id: the billing ID
            organisation_id: the ID of the accountant organisation
            invoice_id: assign only this invoice
    """

    db = current.db
    s3db = current.s3db

    if not organisation_id:
        # Look up the accounting organisation for the billing
        btable = s3db.fin_voucher_billing
        query = (btable.id == billing_id)
        billing = db(query).select(btable.organisation_id,
                                   limitby = (0, 1),
                                   ).first()
        if not billing:
            return
        organisation_id = billing.organisation_id

    if organisation_id:
        # Look up the active accountants of the accountant org
        accountants = get_role_hrs("PROGRAM_ACCOUNTANT",
                                   organisation_id = organisation_id,
                                   )
    else:
        accountants = []

    # Query for any pending invoices of this billing cycle
    itable = s3db.fin_voucher_invoice
    if invoice_id:
        query = (itable.id == invoice_id)
    else:
        query = (itable.billing_id == billing_id)
    query &= (itable.status != "PAID") & (itable.deleted == False)

    if accountants:
        # Limit to invoices that have not yet been assigned to any
        # of the accountants in charge:
        query &= ((itable.human_resource_id == None) | \
                  (~(itable.human_resource_id.belongs(accountants))))

        # Get the invoices
        invoices = db(query).select(itable.id,
                                    itable.human_resource_id,
                                    )
        if not invoices:
            return

        # Look up the number of pending invoices assigned to each
        # accountant, to get a measure for their current workload
        workload = {hr_id: 0 for hr_id in accountants}
        query = (itable.status != "PAID") & \
                (itable.human_resource_id.belongs(accountants)) & \
                (itable.deleted == False)
        num_assigned = itable.id.count()
        rows = db(query).select(itable.human_resource_id,
                                num_assigned,
                                groupby = itable.human_resource_id,
                                )
        for row in rows:
            workload[row[itable.human_resource_id]] = row[num_assigned]

        # Re-assign invoices
        # - try to distribute workload evenly among the accountants
        for invoice in invoices:
            hr_id, num = min(workload.items(), key=lambda item: item[1])
            invoice.update_record(human_resource_id = hr_id)
            workload[hr_id] = num + 1

    elif not invoice_id:
        # Unassign all pending invoices
        db(query).update(human_resource_id = None)

# -----------------------------------------------------------------------------
def check_invoice_integrity(row):
    """
        Rheader-helper to check and report invoice integrity

        Args:
            row: the invoice record

        Returns:
            integrity check result
    """

    billing = current.s3db.fin_VoucherBilling(row.billing_id)
    try:
        checked = billing.check_invoice(row.id)
    except ValueError:
        checked = False

    T = current.T
    if checked:
        return SPAN(T("Ok"),
                    I(_class="fa fa-check"),
                    _class="record-integrity-ok",
                    )
    else:
        current.response.error = T("This invoice may be invalid - please contact the administrator")
        return SPAN(T("Failed"),
                    I(_class="fa fa-exclamation-triangle"),
                    _class="record-integrity-broken",
                    )

# -----------------------------------------------------------------------------
def get_stats_projects():
    """
        Find all projects the current user can report test results, i.e.
        - projects marked as STATS=Y where
        - the current user has the VOUCHER_PROVIDER role for a partner organisation

        @status: obsolete, test results shall be reported for all projects
    """

    permitted_realms = current.auth.permission.permitted_realms
    realms = permitted_realms("disease_case_diagnostics",
                              method = "create",
                              c = "disease",
                              f = "case_diagnostics",
                              )

    if realms is not None and not realms:
        return []

    s3db = current.s3db

    otable = s3db.org_organisation
    ltable = s3db.project_organisation
    ttable = s3db.project_project_tag

    oquery = otable.deleted == False
    if realms:
        oquery = otable.pe_id.belongs(realms) & oquery

    join = [ltable.on((ltable.project_id == ttable.project_id) & \
                      (ltable.deleted == False)),
            otable.on((otable.id == ltable.organisation_id) & oquery),
            ]

    query = (ttable.tag == "STATS") & \
            (ttable.value == "Y") & \
            (ttable.deleted == False)
    rows = current.db(query).select(ttable.project_id,
                                    cache = s3db.cache,
                                    join = join,
                                    groupby = ttable.project_id,
                                    )
    return [row.project_id for row in rows]

# -----------------------------------------------------------------------------
def configure_binary_tags(resource, tag_components):
    """
        Configure representation of binary tags

        Args:
            resource: the CRUDResource
            tag_components: tuple|list of filtered tag component aliases
    """

    T = current.T

    binary_tag_opts = {"Y": T("Yes"), "N": T("No")}

    for cname in tag_components:
        component = resource.components.get(cname)
        if component:
            ctable = component.table
            field = ctable.value
            field.default = "N"
            field.requires = IS_IN_SET(binary_tag_opts, zero=None)
            field.represent = lambda v, row=None: binary_tag_opts.get(v, "-")

# =============================================================================
def facility_map_popup(record):
    """
        Custom map popup for facilities

        Args:
            record: the facility record (Row)

        Returns:
            the map popup contents as DIV
    """

    db = current.db
    s3db = current.s3db

    T = current.T

    table = s3db.org_facility

    # Custom Map Popup
    title = H4(record.name, _class="map-popup-title")

    details = TABLE(_class="map-popup-details")
    append = details.append

    def formrow(label, value, represent=None):
        return TR(TD("%s:" % label, _class="map-popup-label"),
                  TD(represent(value) if represent else value),
                  )

    # Address
    gtable = s3db.gis_location
    query = (gtable.id == record.location_id)
    location = db(query).select(gtable.addr_street,
                                gtable.addr_postcode,
                                gtable.L4,
                                gtable.L3,
                                limitby = (0, 1),
                                ).first()

    if location.addr_street:
        append(formrow(gtable.addr_street.label, location.addr_street))
    place = location.L4 or location.L3 or "?"
    if location.addr_postcode:
        place = "%s %s" % (location.addr_postcode, place)
    append(formrow(T("Place"), place))

    # Phone number
    phone = record.phone1
    if phone:
        append(formrow(T("Phone"), phone))

    # Email address (as hyperlink)
    email = record.email
    if email:
        append(formrow(table.email.label, A(email, _href="mailto:%s" % email)))

    # Opening Times
    opening_times = record.opening_times
    if opening_times:
        append(formrow(table.opening_times.label, opening_times))

    # Site services
    stable = s3db.org_service
    ltable = s3db.org_service_site
    join = stable.on(stable.id == ltable.service_id)
    query = (ltable.site_id == record.site_id) & \
            (ltable.deleted == False)
    rows = db(query).select(stable.name, join=join)
    services = [row.name for row in rows]
    if services:
        append(formrow(T("Services"), ", ".join(services)))

    # Comments
    if record.comments:
        append(formrow(table.comments.label,
                        record.comments,
                        represent = table.comments.represent,
                        ))

    return DIV(title, details, _class="map-popup")

# END =========================================================================
