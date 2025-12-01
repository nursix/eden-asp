"""
    Helper functions and classes for RLPPTM

    License: MIT
"""

import json

from dateutil import rrule

from gluon import current, Field, URL, \
                  CRYPT, IS_EMAIL, IS_IN_SET, IS_LOWER, IS_NOT_IN_DB, \
                  SQLFORM, A, DIV, H4, H5, I, INPUT, LI, P, SPAN, TABLE, TD, TH, TR, UL

from core import ICON, IS_FLOAT_AMOUNT, JSONERRORS, S3DateTime, CRUDMethod, \
                 S3Represent, WorkflowOptions, \
                 s3_fullname, s3_mark_required, s3_str

from s3db.pr import pr_PersonRepresentContact

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

# -----------------------------------------------------------------------------
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
                               cache = s3db.cache,
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
                  "representative": representative status,
                  "account": account status,
                  "status": verification status (for legal representatives),
                  }

        Note:
            all data returned are represented (no raw data)
    """

    T = current.T

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
        rrows = rrows.filter(lambda row: row.status == 1) or rrows
        rrows = rrows.filter(lambda row: row.org_contact) or rrows
        human_resource = rrows.first()
    else:
        human_resource = rows.first()

    output = {"organisation": None,
              "representative": None,
              "account": account_status(record),
              "status": None,
              }

    if human_resource:
        otable = s3db.org_organisation
        rtable = s3db.org_representative

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

        # Representative/verification status
        query = (rtable.person_id == person_id) & \
                (rtable.organisation_id == human_resource.organisation_id) & \
                (rtable.deleted == False)
        representative = db(query).select(rtable.active,
                                          rtable.status,
                                          limitby = (0, 1),
                                          ).first()

        if representative:
            output["representative"] = T("active") if representative.active else T("inactive")
            output["status"] = rtable.status.represent(representative.status)

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
def can_cancel_debit(debit):
    """
        Check whether the current user is entitled to cancel a certain
        voucher debit:
        * User must have the VOUCHER_PROVIDER role for the organisation
          that originally accepted the voucher (not even ADMIN-role can
          override this requirement)

        Args:
            debit: the debit (Row, must contain the debit pe_id)

        Returns:
            True|False
    """

    auth = current.auth

    user = auth.user
    if user:
        # Look up the role ID
        gtable = auth.settings.table_group
        query = (gtable.uuid == "VOUCHER_PROVIDER")
        role = current.db(query).select(gtable.id,
                                        cache = current.s3db.cache,
                                        limitby = (0, 1),
                                        ).first()
        if not role:
            return False

        # Get the realms they have this role for
        realms = user.realms
        if role.id in realms:
            role_realms = realms.get(role.id)
        else:
            # They don't have the role at all
            return False

        if not role_realms:
            # User has a site-wide VOUCHER_PROVIDER role, however
            # for cancellation of debits they must be affiliated
            # with the debit owner organisation
            role_realms = current.s3db.pr_default_realms(user["pe_id"])

        return debit.pe_id in role_realms

    else:
        # No user
        return False

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

# -----------------------------------------------------------------------------
def applicable_org_types(organisation_id, group=None, represent=False):
    """
        Look up organisation types by OrgGroup-tag

        Args:
            organisation_id: the record ID of an existing organisation
            group: alternatively, the organisation group name
            represent: include type labels in the result

        Returns:
            a list of organisation type IDs, for filtering,
            or a dict {type_id: label}, for selecting
    """

    db = current.db
    s3db = current.s3db

    ttable = s3db.org_organisation_type_tag

    if organisation_id:
        # Look up the org groups of this record
        gtable = s3db.org_group
        mtable = s3db.org_group_membership
        join = gtable.on(gtable.id == mtable.group_id)
        query = (mtable.organisation_id == organisation_id) & \
                (mtable.deleted == False)
        rows = db(query).select(gtable.name, join=join)
        groups = {row.name for row in rows}
        q = (ttable.value.belongs(groups))

        # Look up the org types the record is currently linked to
        ltable = s3db.org_organisation_organisation_type
        query = (ltable.organisation_id == organisation_id) & \
                (ltable.deleted == False)
        rows = db(query).select(ltable.organisation_type_id)
        current_types = {row.organisation_type_id for row in rows}

    elif group:
        # Use group name as-is
        q = (ttable.value == group)

    # Look up all types tagged for this group
    query = (ttable.tag == "OrgGroup") & q & \
            (ttable.deleted == False)
    rows = db(query).select(ttable.organisation_type_id,
                            cache = s3db.cache,
                            )
    type_ids = {row.organisation_type_id for row in rows}

    if organisation_id:
        # Add the org types the record is currently linked to
        type_ids |= current_types

    if represent:
        labels = ttable.organisation_type_id.represent
        if hasattr(labels, "bulk"):
            labels.bulk(list(type_ids))
        output = {str(t): labels(t) for t in type_ids}
    else:
        output = list(type_ids)

    return output

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

# =============================================================================
def update_daily_report(site_id, result_date, disease_id):
    """
        Update daily testing activity report (without subtotals per demographic)
        - called when a new individual test result is registered

        Args:
            site_id: the test station site ID
            result_date: the result date of the test
            disease_id: the disease ID
    """

    db = current.db
    s3db = current.s3db

    table = s3db.disease_case_diagnostics

    # Count records grouped by result
    query = (table.site_id == site_id) & \
            (table.disease_id == disease_id) & \
            (table.result_date == result_date) & \
            (table.deleted == False)
    cnt = table.id.count()
    rows = db(query).select(table.result,
                            cnt,
                            groupby = table.result,
                            )
    total = positive = 0
    for row in rows:
        num = row[cnt]
        total += num
        if row.disease_case_diagnostics.result == "POS":
            positive += num

    # Look up the daily report
    rtable = s3db.disease_testing_report
    query = (rtable.site_id == site_id) & \
            (rtable.disease_id == disease_id) & \
            (rtable.date == result_date) & \
            (rtable.deleted == False)
    report = db(query).select(rtable.id,
                              rtable.tests_total,
                              rtable.tests_positive,
                              limitby = (0, 1),
                              ).first()

    if report:
        # Update report if actual numbers are greater
        if report.tests_total < total or report.tests_positive < positive:
            report.update_record(tests_total = total,
                                 tests_positive = positive,
                                 )
    else:
        # Create report
        report = {"site_id": site_id,
                  "disease_id": disease_id,
                  "date": result_date,
                  "tests_total": total,
                  "tests_positive": positive,
                  }
        report_id = rtable.insert(**report)
        if report_id:
            current.auth.s3_set_record_owner(rtable, report_id)
            report["id"] = report_id
            s3db.onaccept(rtable, report, method="create")

# -----------------------------------------------------------------------------
def update_daily_report_by_demographic(site_id, result_date, disease_id):
    """
        Update daily testing activity report (with subtotals per demographic)
        - called when a new individual test result is registered

        Args:
            site_id: the test station site ID
            result_date: the result date of the test
            disease_id: the disease ID
    """

    db = current.db
    s3db = current.s3db
    set_record_owner = current.auth.s3_set_record_owner

    table = s3db.disease_case_diagnostics
    rtable = s3db.disease_testing_report
    dtable = s3db.disease_testing_demographic

    # Count individual results by demographic and result
    query = (table.site_id == site_id) & \
            (table.disease_id == disease_id) & \
            (table.result_date == result_date) & \
            (table.deleted == False)
    cnt = table.id.count()
    rows = db(query).select(table.demographic_id,
                            table.result,
                            cnt,
                            groupby = (table.demographic_id, table.result),
                            )

    # Generate recorded-subtotals matrix
    subtotals = {}
    total = positive = 0
    for row in rows:
        record = row.disease_case_diagnostics
        demographic_id = record.demographic_id
        item = subtotals.get(demographic_id)
        if not item:
            item = subtotals[demographic_id] = {"tests_total": 0,
                                                "tests_positive": 0,
                                                }
        num = row[cnt]
        total += num
        item["tests_total"] += num
        if record.result == "POS":
            positive += num
            item["tests_positive"] += num

    # Look up the daily report
    query = (rtable.site_id == site_id) & \
            (rtable.disease_id == disease_id) & \
            (rtable.date == result_date) & \
            (rtable.deleted == False)
    report = db(query).select(rtable.id,
                              rtable.tests_total,
                              rtable.tests_positive,
                              limitby = (0, 1),
                              ).first()

    if not report:
        # Create a report with the recorded totals
        report = {"site_id": site_id,
                  "disease_id": disease_id,
                  "date": result_date,
                  "tests_total": total,
                  "tests_positive": positive,
                  }
        report["id"] = report_id = rtable.insert(**report)
        if report_id:
            set_record_owner(rtable, report_id)
            s3db.onaccept(rtable, report, method="create")

            # Add subtotals per demographic
            for demographic_id, item in subtotals.items():
                subtotal = {"report_id": report_id,
                            "demographic_id": demographic_id,
                            "tests_total": item["tests_total"],
                            "tests_positive": item["tests_positive"]
                            }
                subtotal_id = subtotal["id"] = dtable.insert(**subtotal)
                set_record_owner(dtable, subtotal_id)
                # We've already set the correct totals in the report:
                #s3db.onaccept(dtable, subtotal, method="create")

    else:
        # Update the existing report with revised subtotals
        report_id = report.id

        # Get all current (reported) subtotals of this report
        query = (dtable.report_id == report_id) & \
                (dtable.deleted == False)
        rows = db(query).select(dtable.id,
                                dtable.demographic_id,
                                dtable.tests_total,
                                dtable.tests_positive,
                                orderby = ~dtable.modified_on,
                                )

        # For each demographic, determine the recorded and reported subtotals
        for demographic_id, item in subtotals.items():

            # Recorded totals
            recorded_total = item["tests_total"]
            recorded_positive = item["tests_positive"]

            # Reported totals
            last_report = None
            reported_total = reported_positive = 0
            for row in rows:
                if row.demographic_id == demographic_id:
                    reported_total += row.tests_total
                    reported_positive += row.tests_positive
                    if not last_report:
                        last_report = row

            if not last_report:
                # No subtotal for this demographic yet => create one
                subtotal = {"report_id": report_id,
                            "demographic_id": demographic_id,
                            "tests_total": recorded_total,
                            "tests_positive": recorded_positive,
                            }
                subtotal_id = subtotal["id"] = dtable.insert(**subtotal)
                set_record_owner(dtable, subtotal_id)
                # We do this in-bulk at the end:
                #s3db.onaccept(dtable, subtotal, method="create")

            elif reported_total < recorded_total or \
                 reported_positive < recorded_positive:
                # Update the last subtotal with the differences
                last_report.update_record(
                    tests_total = last_report.tests_total + \
                                  max(recorded_total - reported_total, 1),
                    tests_positive = last_report.tests_positive + \
                                     max(recorded_positive - reported_positive, 0),
                    )

        # Get subtotals for all demographics under this report
        query = (dtable.report_id == report_id) & \
                (dtable.deleted == False)
        total = dtable.tests_total.sum()
        positive = dtable.tests_positive.sum()
        row = db(query).select(total, positive).first()

        # Update the overall report
        query = (rtable.id == report_id) & \
                (rtable.deleted == False)
        db(query).update(tests_total = row[total],
                         tests_positive = row[positive],
                         )

# =============================================================================
def rlp_holidays(start, end):
    """
        Date rules set for holidays in RLP

        Args:
            start: the start date
            end: the end date

        Returns:
            a dateutil.rrule rule set for all holidays within the interval
    """

    rules = rrule.rruleset()
    addrule = rules.rrule
    newrule = rrule.rrule

    # Fixed-date holidays
    addrule(newrule(rrule.YEARLY, dtstart=start, until=end, bymonth=1, bymonthday=1))
    addrule(newrule(rrule.YEARLY, dtstart=start, until=end, bymonth=5, bymonthday=1))
    addrule(newrule(rrule.YEARLY, dtstart=start, until=end, bymonth=10, bymonthday=3))
    addrule(newrule(rrule.YEARLY, dtstart=start, until=end, bymonth=11, bymonthday=1))
    addrule(newrule(rrule.YEARLY, dtstart=start, until=end, bymonth=12, bymonthday=(25, 26)))

    # Easter-related holidays:
    # (Karfreitag, Ostermontag, Christi Himmelfahrt, Pfingstmontag, Fronleichnam)
    addrule(newrule(rrule.YEARLY, dtstart=start, until=end, byeaster=(-2, 1, 39, 50, 60)))

    # Exclude holidays on weekends
    rules.exrule(newrule(rrule.WEEKLY, dtstart=start, until=end, byweekday=(rrule.SA,rrule.SU)))

    return rules

# =============================================================================
class ServiceListRepresent(S3Represent):

    always_list = True

    def render_list(self, value, labels, show_link=True):
        """
            Helper method to render list-type representations from
            bulk()-results.

            Args:
                value: the list
                labels: the labels as returned from bulk()
                show_link: render references as links, should
                           be the same as used with bulk()
        """

        show_link = show_link and self.show_link

        values = [v for v in value if v is not None]
        if not len(values):
            return ""

        if show_link:
            labels_ = (labels[v] if v in labels else self.default for v in values)
        else:
            labels_ = sorted(s3_str(labels[v]) if v in labels else self.default for v in values)

        html = UL(_class="service-list")
        for label in labels_:
            html.append(LI(label))

        return html

# =============================================================================
class OrganisationRepresent(S3Represent):
    """
        Custom representation of organisations showing the organisation type
        - relevant for facility approval
    """

    def __init__(self, show_type=True, show_link=True):

        super().__init__(lookup = "org_organisation",
                         fields = ["name",],
                         show_link = show_link,
                         )
        self.show_type = show_type
        self.org_types = {}
        self.type_names = {}

    # -------------------------------------------------------------------------
    def lookup_rows(self, key, values, fields=None):
        """
            Custom lookup method for organisation rows, does a
            left join with the parent organisation. Parameters
            key and fields are not used, but are kept for API
            compatibility reasons.

            Args:
                values: the organisation IDs
        """

        db = current.db
        s3db = current.s3db

        otable = s3db.org_organisation

        count = len(values)
        if count == 1:
            query = (otable.id == values[0])
        else:
            query = (otable.id.belongs(values))

        rows = db(query).select(otable.id,
                                otable.name,
                                limitby = (0, count),
                                )

        if self.show_type:
            ltable = s3db.org_organisation_organisation_type
            if count == 1:
                query = (ltable.organisation_id == values[0])
            else:
                query = (ltable.organisation_id.belongs(values))
            query &= (ltable.deleted == False)
            types = db(query).select(ltable.organisation_id,
                                     ltable.organisation_type_id,
                                     )

            all_types = set()
            org_types = self.org_types = {}

            for t in types:

                type_id = t.organisation_type_id
                all_types.add(type_id)

                organisation_id = t.organisation_id
                if organisation_id not in org_types:
                    org_types[organisation_id] = {type_id}
                else:
                    org_types[organisation_id].add(type_id)

            if all_types:
                ttable = s3db.org_organisation_type
                query = ttable.id.belongs(all_types)
                types = db(query).select(ttable.id,
                                         ttable.name,
                                         limitby = (0, len(all_types)),
                                         )
                self.type_names = {t.id: t.name for t in types}

        return rows

    # -------------------------------------------------------------------------
    def represent_row(self, row):
        """
            Represent a single Row

            Args:
                row: the org_organisation Row
        """

        name = s3_str(row.name)

        if self.show_type:

            T = current.T

            type_ids = self.org_types.get(row.id)
            if type_ids:
                type_names = self.type_names
                types = [s3_str(T(type_names[t]))
                         for t in type_ids if t in type_names
                         ]
                name = "%s (%s)" % (name, ", ".join(types))

        return name

# =============================================================================
class InviteUserOrg(CRUDMethod):
    """ Custom Method Handler to invite User Organisations """

    # -------------------------------------------------------------------------
    def apply_method(self, r, **attr):
        """
            Page-render entry point for REST interface.

            Args:
                r: the CRUDRequest instance
                attr: controller attributes
        """

        output = {}

        if r.http in ("GET", "POST"):
            if not r.record:
                r.error(400, current.ERROR.BAD_REQUEST)
            if r.interactive:
                output = self.invite(r, **attr)
            else:
                r.error(415, current.ERROR.BAD_FORMAT)
        else:
            r.error(405, current.ERROR.BAD_METHOD)

        return output

    # -------------------------------------------------------------------------
    def invite(self, r, **attr):
        """
            Prepare and process invitation form

            Args:
                r: the CRUDRequest instance
                attr: controller attributes
        """

        T = current.T

        db = current.db
        s3db = current.s3db

        response = current.response
        request = current.request
        session = current.session

        settings = current.deployment_settings
        auth = current.auth
        auth_settings = auth.settings
        auth_messages = auth.messages

        output = {"title": T("Invite Organization"),
                  }

        # Check for existing accounts
        active, disabled, invited = get_org_accounts(r.record.id)
        if active or disabled:
            response.error = T("There are already user accounts registered for this organization")

            from core import s3_format_fullname

            fullname = lambda user: s3_format_fullname(fname = user.first_name,
                                                    lname = user.last_name,
                                                    truncate = False,
                                                    )
            account_list = DIV(_class="org-account-list")
            if active:
                account_list.append(H4(T("Active Accounts")))
                accounts = UL()
                for user in active:
                    accounts.append(LI("%s <%s>" % (fullname(user), user.email)))
                account_list.append(accounts)
            if disabled:
                account_list.append(H4(T("Disabled Accounts")))
                accounts = UL()
                for user in disabled:
                    accounts.append(LI("%s <%s>" % (fullname(user), user.email)))
                account_list.append(accounts)

            output["item"] = account_list
            response.view = self._view(r, "display.html")
            return output

        account = invited[0] if invited else None

        # Look up email to use for invitation
        email = None
        if account:
            email = account.email
        else:
            ctable = s3db.pr_contact
            query = (ctable.pe_id == r.record.pe_id) & \
                    (ctable.contact_method == "EMAIL") & \
                    (ctable.deleted == False)
            contact = db(query).select(ctable.value,
                                       orderby = ctable.priority,
                                       limitby = (0, 1),
                                       ).first()
            if contact:
                email = contact.value

        # Form Fields
        utable = auth_settings.table_user
        dbset = db(utable.id != account.id) if account else db
        formfields = [Field("email",
                            default = email,
                            requires = [IS_EMAIL(error_message = auth_messages.invalid_email),
                                        IS_LOWER(),
                                        IS_NOT_IN_DB(dbset, "%s.email" % utable._tablename,
                                                     error_message = auth_messages.duplicate_email,
                                                     ),
                                        ]
                            ),
                      ]

        # Generate labels (and mark required fields in the process)
        labels, has_required = s3_mark_required(formfields)
        response.s3.has_required = has_required

        # Form buttons
        SEND_INVITATION = T("Send New Invitation") if account else T("Send Invitation")
        buttons = [INPUT(_type = "submit",
                         _value = SEND_INVITATION,
                         ),
                   # TODO cancel-button?
                   ]

        # Construct the form
        response.form_label_separator = ""
        form = SQLFORM.factory(table_name = "invite",
                               record = None,
                               hidden = {"_next": request.vars._next},
                               labels = labels,
                               separator = "",
                               showid = False,
                               submit_button = SEND_INVITATION,
                               #delete_label = auth_messages.delete_label,
                               formstyle = settings.get_ui_formstyle(),
                               buttons = buttons,
                               *formfields)

        # Identify form for CSS & JS Validation
        form.add_class("send_invitation")

        if form.accepts(request.vars,
                        session,
                        formname = "invite",
                        #onvalidation = auth_settings.register_onvalidation,
                        ):

            error = self.invite_account(r.record, form.vars.email, account=account)
            if error:
                response.error = T("Could not send invitation (%(reason)s)") % {"reason": error}
            else:
                response.confirmation = T("Invitation sent")
        else:
            if account:
                response.warning = T("This organization has been invited before!")

        output["form"] = form

        response.view = self._view(r, "update.html")

        return output

    # -------------------------------------------------------------------------
    @classmethod
    def invite_account(cls, organisation, email, account=None):

        data = {"first_name": organisation.name,
                "email": email,
                # TODO language => use default language
                "link_user_to": ["staff"],
                "organisation_id": organisation.id,
                }

        # Generate registration key and activation code
        from uuid import uuid4
        key = str(uuid4())
        code = uuid4().hex[-6:].upper()

        # Add hash to data
        data["registration_key"] = cls.keyhash(key, code)

        if account:
            success = account.update_record(**data)
            if not success:
                return "could not update preliminary account"
        else:
            utable = current.auth.settings.table_user

            # Catch email addresses already used in existing accounts
            if current.db(utable.email == email).select(utable.id,
                                                        limitby = (0, 1),
                                                        ).first():
                return "email address %s already in use" % email

            user_id = utable.insert(**data)
            if user_id:
                ltable = current.s3db.org_organisation_user
                ltable.insert(organisation_id = organisation.id,
                              user_id = user_id,
                              )
            else:
                return "could not create preliminary account"

        # Compose and send invitation email
        app_url = current.deployment_settings.get_base_app_url()
        data = {"url": "%s/default/index/register_invited/%s" % (app_url, key),
                "code": code,
                }

        from .notifications import CMSNotifications
        return CMSNotifications.send(email, "InviteOrg", data,
                                     module = "auth",
                                     resource = "user",
                                     )

    # -------------------------------------------------------------------------
    @staticmethod
    def keyhash(key, code):
        """
            Generate a hash of the activation code using
            the registration key

            Args:
                key: the registration key
                code: the activation code

            Returns:
                the hash as string
        """

        crypt = CRYPT(key=key, digest_alg="sha512", salt=None)
        return str(crypt(code.upper())[0])

# =============================================================================
class InvoicePDF(CRUDMethod):
    """
        REST Method to generate an invoice PDF
        - for external accounting archives
    """

    # -------------------------------------------------------------------------
    def apply_method(self, r, **attr):
        """
            Generate a PDF of an Invoice

            Args:
                r: the CRUDRequest instance
                attr: controller attributes
        """

        if r.representation != "pdf":
            r.error(415, current.ERROR.BAD_FORMAT)
        if not r.record or r.http != "GET":
            r.error(400, current.ERROR.BAD_REQUEST)

        T = current.T

        # Filename to include invoice number if available
        invoice_no = r.record.invoice_no

        from core import DataExporter
        exporter = DataExporter.pdf
        return exporter(r.resource,
                        request = r,
                        method = "read",
                        pdf_title = T("Invoice"),
                        pdf_filename = invoice_no if invoice_no else None,
                        pdf_header = self.invoice_header,
                        pdf_callback = self.invoice,
                        pdf_footer = self.invoice_footer,
                        pdf_hide_comments = True,
                        pdf_header_padding = 12,
                        pdf_orientation = "Portrait",
                        pdf_table_autogrow = "B",
                        **attr
                        )

    # -------------------------------------------------------------------------
    @classmethod
    def invoice_header(cls, r):
        """
            Generate the invoice header

            Args:
                r: the CRUDRequest
        """

        T = current.T

        table = r.resource.table
        invoice = r.record
        pdata = cls.lookup_header_data(invoice)

        place = [pdata.get(k) for k in ("addr_postcode", "addr_place")]

        header = TABLE(TR(TD(DIV(H4(T("Invoice")), P(" ")),
                             _colspan = 4,
                             ),
                          ),
                       TR(TH(T("Invoicing Party")),
                          TD(pdata.get("organisation", "-")),
                          TH(T("Invoice No.")),
                          TD(table.invoice_no.represent(invoice.invoice_no)),
                          ),
                       TR(TH(T("Address")),
                          TD(pdata.get("addr_street", "-")),
                          TH(table.date.label),
                          TD(table.date.represent(invoice.date)),
                          ),
                       TR(TH(T("Place")),
                          TD(" ".join(v for v in place if v)),
                          TH(T("Payers")),
                          TD(pdata.get("payers")),
                          ),
                       TR(TH(T("Email")),
                          TD(pdata.get("email", "-")),
                          TH(T("Billing Date")),
                          TD(table.date.represent(pdata.get("billing_date"))),
                          ),
                       )

        return header

    # -------------------------------------------------------------------------
    @classmethod
    def invoice(cls, r):
        """
            Generate the invoice body

            Args:
                r: the CRUDRequest
        """

        T = current.T

        table = r.table

        invoice = r.record
        pdata = cls.lookup_body_data(invoice)

        # Lambda to format currency amounts
        amt = lambda v: IS_FLOAT_AMOUNT.represent(v, precision=2, fixed=True)
        currency = invoice.currency

        # Specification of costs
        costs = TABLE(TR(TH(T("No.")),
                         TH(T("Description")),
                         TH(T("Number##count")),
                         TH(T("Unit")),
                         TH(table.price_per_unit.label),
                         TH(T("Total")),
                         TH(table.currency.label),
                         ),
                      TR(TD("1"), # only one line item here
                         TD(pdata.get("title", "-")),
                         TD(str(invoice.quantity_total)),
                         TD(pdata.get("unit", "-")),
                         TD(amt(invoice.price_per_unit)),
                         TD(amt(invoice.amount_receivable)),
                         TD(currency),
                         ),
                      TR(TD(H5(T("Total")), _colspan=5),
                         TD(H5(amt(invoice.amount_receivable))),
                         TD(H5(currency)),
                         ),
                      )

        # Payment Details
        an_field = table.account_number
        an = an_field.represent(invoice.account_number)
        payment_details = TABLE(TR(TH(table.account_holder.label),
                                   TD(invoice.account_holder),
                                   ),
                                TR(TH(an_field.label),
                                   TD(an),
                                   ),
                                TR(TH(table.bank_name.label),
                                   TD(invoice.bank_name),
                                   ),
                                )

        return DIV(H4(" "),
                   H5(T("Specification of Costs")),
                   costs,
                   H4(" "),
                   H4(" "),
                   H5(T("Payable within %(num)s days to") % {"num": 30}),
                   payment_details,
                   )

    # -------------------------------------------------------------------------
    @staticmethod
    def invoice_footer(r):
        """
            Generate the invoice footer

            Args:
                r: the CRUDRequest
        """

        T = current.T

        invoice = r.record

        # Details about who generated the document and when
        user = current.auth.user
        if not user:
            username = T("anonymous user")
        else:
            username = s3_fullname(user)
        now = S3DateTime.datetime_represent(current.request.utcnow, utc=True)
        note = T("Document generated by %(user)s on %(date)s") % {"user": username,
                                                                  "date": now,
                                                                  }
        # Details about the data source
        vhash = invoice.vhash
        try:
            verification = vhash.split("$$")[1][:7]
        except (AttributeError, IndexError):
            verification = T("invalid")

        settings = current.deployment_settings
        source = TABLE(TR(TH(T("System Name")),
                          TD(settings.get_system_name()),
                          ),
                       TR(TH(T("Web Address")),
                          TD(settings.get_base_public_url()),
                          ),
                       TR(TH(T("Data Source")),
                          TD("%s [%s]" % (invoice.uuid, verification)),
                          ),
                       )

        return DIV(P(note), source)

    # -------------------------------------------------------------------------
    @staticmethod
    def lookup_header_data(invoice):
        """
            Look up data for the invoice header

            Args:
                invoice: the invoice record

            Returns:
                dict with header data
        """

        db = current.db
        s3db = current.s3db

        data = {}

        btable = s3db.fin_voucher_billing
        ptable = s3db.fin_voucher_program
        otable = s3db.org_organisation
        ftable = s3db.org_facility
        ltable = s3db.gis_location
        ctable = s3db.pr_contact

        # Look up the billing date
        query = (btable.id == invoice.billing_id)
        billing = db(query).select(btable.date,
                                   limitby = (0, 1),
                                   ).first()
        if billing:
            data["billing_date"] = billing.date

        # Use the program admin org as "payers"
        query = (ptable.id == invoice.program_id)
        join = otable.on(otable.id == ptable.organisation_id)
        admin_org = db(query).select(otable.name,
                                     join = join,
                                     limitby = (0, 1),
                                     ).first()
        if admin_org:
            data["payers"] = admin_org.name

        # Look up details of the invoicing party
        query = (otable.pe_id == invoice.pe_id) & \
                (otable.deleted == False)
        organisation = db(query).select(otable.id,
                                        otable.name,
                                        limitby = (0, 1),
                                        ).first()
        if organisation:

            data["organisation"] = organisation.name

            # Email address
            query = (ctable.pe_id == invoice.pe_id) & \
                    (ctable.contact_method == "EMAIL") & \
                    (ctable.deleted == False)
            email = db(query).select(ctable.value,
                                     limitby = (0, 1),
                                     ).first()
            if email:
                data["email"] = email.value

            # Facility address
            query = (ftable.organisation_id == organisation.id) & \
                    (ftable.obsolete == False) & \
                    (ftable.deleted == False)
            left = ltable.on(ltable.id == ftable.location_id)
            facility = db(query).select(ftable.email,
                                        ltable.addr_street,
                                        ltable.addr_postcode,
                                        ltable.L3,
                                        ltable.L4,
                                        left = left,
                                        limitby = (0, 1),
                                        orderby = ftable.created_on,
                                        ).first()
            if facility:
                if data.get("email"):
                    # Fallback
                    data["email"] = facility.org_facility.email

                location = facility.gis_location
                data["addr_street"] = location.addr_street or "-"
                data["addr_postcode"] = location.addr_postcode or "-"
                data["addr_place"] = location.L4 or location.L3 or "-"

        return data

    # -------------------------------------------------------------------------
    @staticmethod
    def lookup_body_data(invoice):
        """
            Look up additional data for invoice body

            Args:
                invoice: the invoice record

            Returns:
                dict with invoice data
        """

        db = current.db
        s3db = current.s3db

        ptable = s3db.fin_voucher_program

        query = (ptable.id == invoice.program_id) & \
                (ptable.deleted == False)
        program = db(query).select(ptable.id,
                                   ptable.name,
                                   ptable.unit,
                                   limitby = (0, 1),
                                   ).first()
        if program:
            data = {"title": program.name,
                    "unit": program.unit,
                    }
        else:
            data = {}

        return data

# =============================================================================
class ClaimPDF(CRUDMethod):
    """
        REST Method to generate a claim PDF
        - for external accounting archives
    """

    # -------------------------------------------------------------------------
    def apply_method(self, r, **attr):
        """
            Generate a PDF of a Claim

            Args:
                r: the CRUDRequest instance
                attr: controller attributes
        """

        if r.representation != "pdf":
            r.error(415, current.ERROR.BAD_FORMAT)
        if not r.record or r.http != "GET":
            r.error(400, current.ERROR.BAD_REQUEST)

        T = current.T

        # Filename to include invoice number if available
        invoice_no = self.invoice_number(r.record)

        from core import DataExporter
        exporter = DataExporter.pdf
        return exporter(r.resource,
                        request = r,
                        method = "read",
                        pdf_title = T("Compensation Claim"),
                        pdf_filename = invoice_no if invoice_no else None,
                        pdf_header = self.claim_header,
                        pdf_callback = self.claim,
                        pdf_footer = self.claim_footer,
                        pdf_hide_comments = True,
                        pdf_header_padding = 12,
                        pdf_orientation = "Portrait",
                        pdf_table_autogrow = "B",
                        **attr
                        )

    # -------------------------------------------------------------------------
    @staticmethod
    def invoice_number(record):

        invoice_id = record.invoice_id
        if invoice_id:
            s3db = current.s3db
            itable = s3db.fin_voucher_invoice
            query = (itable.id == invoice_id)
            invoice = current.db(query).select(itable.invoice_no,
                                               cache = s3db.cache,
                                               limitby = (0, 1),
                                               ).first()
        else:
            invoice = None

        return invoice.invoice_no if invoice else None

    # -------------------------------------------------------------------------
    @classmethod
    def claim_header(cls, r):
        """
            Generate the claim header

            Args:
                r: the CRUDRequest
        """

        T = current.T

        table = r.resource.table
        itable = current.s3db.fin_voucher_invoice

        claim = r.record
        pdata = cls.lookup_header_data(claim)

        place = [pdata.get(k) for k in ("addr_postcode", "addr_place")]

        status = " " if claim.invoice_id else "(%s)" % T("not invoiced yet")

        header = TABLE(TR(TD(DIV(H4(T("Compensation Claim")), P(status)),
                             _colspan = 4,
                             ),
                          ),
                       TR(TH(T("Invoicing Party")),
                          TD(pdata.get("organisation", "-")),
                          TH(T("Invoice No.")),
                          TD(itable.invoice_no.represent(pdata.get("invoice_no"))),
                          ),
                       TR(TH(T("Address")),
                          TD(pdata.get("addr_street", "-")),
                          TH(itable.date.label),
                          TD(itable.date.represent(pdata.get("invoice_date"))),
                          ),
                       TR(TH(T("Place")),
                          TD(" ".join(v for v in place if v)),
                          TH(T("Payers")),
                          TD(pdata.get("payers")),
                          ),
                       TR(TH(T("Email")),
                          TD(pdata.get("email", "-")),
                          TH(T("Billing Date")),
                          TD(table.date.represent(pdata.get("billing_date"))),
                          ),
                       )

        return header

    # -------------------------------------------------------------------------
    @classmethod
    def claim(cls, r):
        """
            Generate the claim body

            Args:
                r: the CRUDRequest
        """

        T = current.T

        table = r.table

        claim = r.record
        pdata = cls.lookup_body_data(claim)

        # Lambda to format currency amounts
        amt = lambda v: IS_FLOAT_AMOUNT.represent(v, precision=2, fixed=True)
        currency = claim.currency

        # Specification of costs
        costs = TABLE(TR(TH(T("No.")),
                         TH(T("Description")),
                         TH(T("Number##count")),
                         TH(T("Unit")),
                         TH(table.price_per_unit.label),
                         TH(T("Total")),
                         TH(table.currency.label),
                         ),
                      TR(TD("1"), # only one line item here
                         TD(pdata.get("title", "-")),
                         TD(str(claim.quantity_total)),
                         TD(pdata.get("unit", "-")),
                         TD(amt(claim.price_per_unit)),
                         TD(amt(claim.amount_receivable)),
                         TD(currency),
                         ),
                      TR(TD(H5(T("Total")), _colspan=5),
                         TD(H5(amt(claim.amount_receivable))),
                         TD(H5(currency)),
                         ),
                      )

        # Payment Details
        an_field = table.account_number
        an = an_field.represent(claim.account_number)
        payment_details = TABLE(TR(TH(table.account_holder.label),
                                   TD(claim.account_holder),
                                   ),
                                TR(TH(an_field.label),
                                   TD(an),
                                   ),
                                TR(TH(table.bank_name.label),
                                   TD(claim.bank_name),
                                   ),
                                )

        return DIV(H4(" "),
                   H5(T("Specification of Costs")),
                   costs,
                   H4(" "),
                   H4(" "),
                   H5(T("Payable within %(num)s days to") % {"num": 30}),
                   payment_details,
                   )

    # -------------------------------------------------------------------------
    @staticmethod
    def claim_footer(r):
        """
            Generate the claim footer

            Args:
                r: the CRUDRequest
        """

        T = current.T

        claim = r.record

        # Details about who generated the document and when
        user = current.auth.user
        if not user:
            username = T("anonymous user")
        else:
            username = s3_fullname(user)
        now = S3DateTime.datetime_represent(current.request.utcnow, utc=True)
        note = T("Document generated by %(user)s on %(date)s") % {"user": username,
                                                                  "date": now,
                                                                  }
        # Details about the data source
        vhash = claim.vhash
        try:
            verification = vhash.split("$$")[1][:7]
        except (AttributeError, IndexError):
            verification = T("invalid")

        settings = current.deployment_settings
        source = TABLE(TR(TH(T("System Name")),
                          TD(settings.get_system_name()),
                          ),
                       TR(TH(T("Web Address")),
                          TD(settings.get_base_public_url()),
                          ),
                       TR(TH(T("Data Source")),
                          TD("%s [%s]" % (claim.uuid, verification)),
                          ),
                       )

        return DIV(P(note), source)

    # -------------------------------------------------------------------------
    @staticmethod
    def lookup_header_data(claim):
        """
            Look up data for the claim header

            Args:
                claim: the claim record

            Returns:
                dict with header data
        """

        db = current.db
        s3db = current.s3db

        data = {}

        btable = s3db.fin_voucher_billing
        itable = s3db.fin_voucher_invoice
        ptable = s3db.fin_voucher_program
        otable = s3db.org_organisation
        ftable = s3db.org_facility
        ltable = s3db.gis_location
        ctable = s3db.pr_contact

        # Look up the billing date
        query = (btable.id == claim.billing_id)
        billing = db(query).select(btable.date,
                                   limitby = (0, 1),
                                   ).first()
        if billing:
            data["billing_date"] = billing.date

        # Look up invoice details
        if claim.invoice_id:
            query = (itable.id == claim.invoice_id)
            invoice = db(query).select(itable.date,
                                       itable.invoice_no,
                                       limitby = (0, 1),
                                       ).first()
            if invoice:
                data["invoice_no"] = invoice.invoice_no
                data["invoice_date"] = invoice.date

        # Use the program admin org as "payers"
        query = (ptable.id == claim.program_id)
        join = otable.on(otable.id == ptable.organisation_id)
        admin_org = db(query).select(otable.name,
                                     join = join,
                                     limitby = (0, 1),
                                     ).first()
        if admin_org:
            data["payers"] = admin_org.name

        # Look up details of the invoicing party
        query = (otable.pe_id == claim.pe_id) & \
                (otable.deleted == False)
        organisation = db(query).select(otable.id,
                                        otable.name,
                                        limitby = (0, 1),
                                        ).first()
        if organisation:

            data["organisation"] = organisation.name

            # Email address
            query = (ctable.pe_id == claim.pe_id) & \
                    (ctable.contact_method == "EMAIL") & \
                    (ctable.deleted == False)
            email = db(query).select(ctable.value,
                                     limitby = (0, 1),
                                     ).first()
            if email:
                data["email"] = email.value

            # Facility address
            query = (ftable.organisation_id == organisation.id) & \
                    (ftable.obsolete == False) & \
                    (ftable.deleted == False)
            left = ltable.on(ltable.id == ftable.location_id)
            facility = db(query).select(ftable.email,
                                        ltable.addr_street,
                                        ltable.addr_postcode,
                                        ltable.L3,
                                        ltable.L4,
                                        left = left,
                                        limitby = (0, 1),
                                        orderby = ftable.created_on,
                                        ).first()
            if facility:
                if data.get("email"):
                    # Fallback
                    data["email"] = facility.org_facility.email

                location = facility.gis_location
                data["addr_street"] = location.addr_street or "-"
                data["addr_postcode"] = location.addr_postcode or "-"
                data["addr_place"] = location.L4 or location.L3 or "-"

        return data

    # -------------------------------------------------------------------------
    @staticmethod
    def lookup_body_data(claim):
        """
            Look up additional data for claim body

            Args:
                claim: the claim record

            Returns:
                dict with claim data
        """

        db = current.db
        s3db = current.s3db

        ptable = s3db.fin_voucher_program

        query = (ptable.id == claim.program_id) & \
                (ptable.deleted == False)
        program = db(query).select(ptable.id,
                                   ptable.name,
                                   ptable.unit,
                                   limitby = (0, 1),
                                   ).first()
        if program:
            data = {"title": program.name,
                    "unit": program.unit,
                    }
        else:
            data = {}

        return data

# =============================================================================
class TestFacilityInfo(CRUDMethod):
    """
        REST Method to report details/activities of a test facility
    """

    # -------------------------------------------------------------------------
    def apply_method(self, r, **attr):
        """
            Report test facility information

            Args:
                r: the CRUDRequest instance
                attr: controller attributes
        """

        if r.http == "POST":
            if r.representation == "json":
                output = self.facility_info(r, **attr)
            else:
                r.error(415, current.ERROR.BAD_FORMAT)
        else:
            r.error(405, current.ERROR.BAD_METHOD)

        return output

    # -------------------------------------------------------------------------
    @staticmethod
    def facility_info(r, **attr):
        """
            Respond to a POST .json request, request body format:

                {"client": "CLIENT",        - the client identity (ocert)
                 "appkey": "APPKEY",        - the client app key (ocert)
                 "code": "FACILITY-CODE",   - the facility code
                 "report": ["start","end"], - the date interval to report
                                              activities for (optional)
                                              (ISO-format dates YYYY-MM-DD)
                }

            Output format:
                {"code": "FACILITY-CODE",   - echoed from input
                 "name": "FACILITY-NAME",   - the facility name
                 "phone": "phone #",        - the facility phone number
                 "email": "email",          - the facility email address
                 "public": True|False,      - whether the facility is listed in the public registry
                 "organisation":
                    {"id": "ORG-ID",        - the organisation ID tag
                     "name": "ORG-NAME",    - the organisation name
                     "type": "ORG-TYPE",    - the organisation type
                     "website": "URL"       - the organisation website URL
                     "commission": [        - commissioning details
                        {"start": YYYY-MM-DD,
                        "end": YYYY-MM-DD,
                        "status": CURRENT|SUSPENDED|REVOKED|EXPIRED,
                        "status_date": YYYY-MM-DD,
                        }, ...
                       ]
                     },
                 "location":
                    {"L1": "L1-NAME",       - the L1 name (state)
                     "L2": "L2-NAME",       - the L2 name (district)
                     "L3": "L3-NAME",       - the L3 name (commune/city)
                     "L4": "L4-NAME",       - the L4 name (village/town)
                     "address": "STREET",   - the street address
                     "postcode": "XXXXX"    - the postcode
                     },
                 "report": ["start","end"], - echoed from input, ISO-format dates YYYY-MM-DD
                 "activity":
                    {"tests": NN            - the total number of tests reported for the period
                    },
                 }
        """

        settings = current.deployment_settings

        # Get the configured, permitted clients
        ocert = settings.get_custom("ocert")
        if not ocert:
            r.error(501, current.ERROR.METHOD_DISABLED)

        # Read the body JSON of the request
        body = r.body
        body.seek(0)
        try:
            s = body.read().decode("utf-8")
        except (ValueError, AttributeError, UnicodeDecodeError):
            r.error(400, current.ERROR.BAD_REQUEST)
        try:
            ref = json.loads(s)
        except JSONERRORS:
            r.error(400, current.ERROR.BAD_REQUEST)

        # Verify the client
        client = ref.get("client")
        if not client or client not in ocert:
            r.error(403, current.ERROR.NOT_PERMITTED)
        key, _ = ocert.get(client)
        if key:
            appkey = ref.get("appkey")
            if not appkey or appkey.upper() != key.upper():
                r.error(403, current.ERROR.NOT_PERMITTED)

        # Identify the facility
        db = current.db
        s3db = current.s3db

        table = s3db.org_facility
        record = r.record
        if record:
            query = (table.id == record.id)
        else:
            code = ref.get("code")
            if not code:
                r.error(400, current.ERROR.BAD_REQUEST)
            query = (table.code.upper() == code.upper())

        atable = s3db.org_site_approval
        left = atable.on((atable.site_id == table.site_id) & \
                         (atable.deleted == False))

        query &= (table.deleted == False)
        row = db(query).select(table.code,
                               table.name,
                               table.phone1,
                               table.email,
                               table.website,
                               table.organisation_id,
                               table.location_id,
                               table.site_id,
                               atable.public,
                               left = left,
                               limitby = (0, 1),
                               ).first()

        if not row:
            r.error(404, current.ERROR.BAD_RECORD)
        else:
            facility = row.org_facility
            approval = row.org_site_approval

        # Prepare facility info
        output = {"code": facility.code,
                  "name": facility.name,
                  "phone": facility.phone1,
                  "email": facility.email,
                  "public": approval.public == "Y",
                  }

        # Look up organisation data
        otable = s3db.org_organisation
        ttable = s3db.org_organisation_type
        ltable = s3db.org_organisation_organisation_type
        ottable = s3db.org_organisation_tag
        left = [ttable.on((ltable.organisation_id == otable.id) & \
                          (ltable.deleted == False) & \
                          (ttable.id == ltable.organisation_type_id)),
                ottable.on((ottable.organisation_id == otable.id) & \
                           (ottable.tag == "OrgID") & \
                           (ottable.deleted == False)),
                ]
        query = (otable.id == facility.organisation_id) & \
                (otable.deleted == False)
        row = db(query).select(otable.id,
                               otable.name,
                               otable.website,
                               ttable.name,
                               ottable.value,
                               left = left,
                               limitby = (0, 1),
                               ).first()
        if row:
            organisation = row.org_organisation
            orgtype = row.org_organisation_type
            orgid = row.org_organisation_tag
            orgdata = {"id": orgid.value,
                       "name": organisation.name,
                       "type": orgtype.name,
                       "website": organisation.website,
                       }

            # Add commission data
            ctable = s3db.org_commission
            query = (ctable.organisation_id == organisation.id) & \
                    (ctable.deleted == False)
            commissions = db(query).select(ctable.date,
                                           ctable.end_date,
                                           ctable.status,
                                           ctable.status_date,
                                           )
            dtfmt = lambda dt: dt.isoformat() if dt else '--'
            clist = []
            for commission in commissions:
                clist.append({"start": dtfmt(commission.date),
                              "end": dtfmt(commission.end_date),
                              "status": commission.status,
                              "status_date": dtfmt(commission.status_date),
                              })
            orgdata["commission"] = clist

            output["organisation"] = orgdata

        # Look up location data
        ltable = s3db.gis_location
        query = (ltable.id == facility.location_id) & \
                (ltable.deleted == False)
        row = db(query).select(ltable.L1,
                               ltable.L2,
                               ltable.L3,
                               ltable.L4,
                               ltable.addr_street,
                               ltable.addr_postcode,
                               limitby = (0, 1),
                               ).first()
        if row:
            locdata = {"L1": row.L1,
                       "L2": row.L2,
                       "L3": row.L3,
                       "L4": row.L4,
                       "address": row.addr_street,
                       "postcode": row.addr_postcode,
                       }
            output["location"] = locdata

        # Look up activity data
        report = ref.get("report")
        if report:
            if isinstance(report, list) and len(report) == 2:

                start, end = report

                # Parse the dates, if any
                parse_date = current.calendar.parse_date
                start = parse_date(start) if start else False
                end = parse_date(end) if end else False
                if start is None or end is None:
                    r.error(400, "Invalid date format in report parameter")
                if start and end and start > end:
                    start, end = end, start

                # Extract the totals from the database
                table = s3db.disease_testing_report
                query = (table.site_id == facility.site_id)
                if start:
                    query &= (table.date >= start)
                if end:
                    query &= (table.date <= end)
                query &= (table.deleted == False)
                total = table.tests_total.sum()
                positive = table.tests_positive.sum()
                row = db(query).select(total, positive).first()
                tests_total = row[total]
                tests_positive = row[positive]

                # Add to output
                output["report"] = [start.isoformat() if start else None,
                                    end.isoformat() if end else None,
                                    ]
                output["activity"] = {"tests": tests_total if tests_total else 0,
                                      "positive": tests_positive if tests_positive else 0,
                                      }
            else:
                r.error(400, "Invalid report parameter format")

        # Return as JSON
        response = current.response
        if response:
            response.headers["Content-Type"] = "application/json; charset=utf-8"
        return json.dumps(output, separators=(",", ":"), ensure_ascii=False)

# =============================================================================
class TestProviderInfo(CRUDMethod):
    """
        REST Method to report details/activities of a test provider
    """

    # -------------------------------------------------------------------------
    def apply_method(self, r, **attr):
        """
            Report test provider information

            Args:
                r: the CRUDRequest instance
                attr: controller attributes
        """

        if r.http == "POST":
            if r.representation == "json":
                output = self.provider_info(r, **attr)
            else:
                r.error(415, current.ERROR.BAD_FORMAT)
        else:
            r.error(405, current.ERROR.BAD_METHOD)

        return output

    # -------------------------------------------------------------------------
    @classmethod
    def provider_info(cls, r, **attr):
        """
            Respond to a POST .json request, request body format:

                {"client": "CLIENT",        - the client identity (ocert)
                 "appkey": "APPKEY",        - the client app key  (ocert)
                 "providerCode": "ORGANISATION-ID",
                 "siteCode": "TESTSTATION-ID",
                 "bsnr": "BSNR",
                 "report": ["start","end"], - the date interval to report
                                              activities for (optional)
                                              (ISO-format dates YYYY-MM-DD)
                 }

            Output format:

                {
                "provider": {
                    "name": "ORG-NAME",    - the provider name
                    "type": "ORG-TYPE",    - the provider organisation type
                    "code": "ORG-ID",      - the provider organisation ID
                    "bsnr": "BSNR",        - the provider BSNR
                    "website": "URL"       - the provider website
                    "commission": [        - commissioning details
                        {"start": YYYY-MM-DD,
                         "end": YYYY-MM-DD,
                         "status": CURRENT|SUSPENDED|REVOKED|EXPIRED,
                         "statusDate": YYYY-MM-DD,
                         }, ...
                        ],
                    "activity": {           - activity totals for all sites
                        "interval": ["start", "end"],
                        "testsTotal": NN,
                        "testsPositive": NN,
                        },
                    },

                 "sites": [
                    {"name": "FACILITY-NAME",   - the facility name
                     "code": "FACILITY-ID",     - the facility ID
                     "phone": "phone #",        - the facility phone number
                     "email": "email",          - the facility email address
                     "location":
                        {"L1": "L1-NAME",       - the L1 name (state)
                         "L2": "L2-NAME",       - the L2 name (district)
                         "L3": "L3-NAME",       - the L3 name (commune/city)
                         "L4": "L4-NAME",       - the L4 name (village/town)
                         "address": "STREET",   - the street address
                         "postcode": "XXXXX"    - the postcode
                         },
                     "activity": {              - activity data for this site
                        "interval": ["start", "end"],
                        "testsTotal": NN,
                        "testsPositive": NN,
                        }
                     }, ...
                    ],
                 }
        """

        settings = current.deployment_settings

        # Get the configured, permitted clients
        ocert = settings.get_custom("ocert")
        if not ocert:
            r.error(501, current.ERROR.METHOD_DISABLED)

        # Read the body JSON of the request
        body = r.body
        body.seek(0)
        try:
            s = body.read().decode("utf-8")
        except (ValueError, AttributeError, UnicodeDecodeError):
            r.error(400, current.ERROR.BAD_REQUEST)
        try:
            ref = json.loads(s)
        except JSONERRORS:
            r.error(400, current.ERROR.BAD_REQUEST)

        # Verify the client
        client = ref.get("client")
        if not client or client not in ocert:
            r.error(403, current.ERROR.NOT_PERMITTED)
        key, _ = ocert.get(client)
        if key:
            appkey = ref.get("appkey")
            if not appkey or appkey.upper() != key.upper():
                r.error(403, current.ERROR.NOT_PERMITTED)

        # Identify the organisation from providerCode, siteCode or bsnr or combinations thereof
        organisation_id = r.record.id if r.record else None
        provider_id = ref.get("providerCode")
        site_code = ref.get("siteCode")
        bsnr = ref.get("bsnr")

        # Look up provider
        organisation_id, provider_info = cls.lookup_provider(organisation_id,
                                                             provider_id = provider_id,
                                                             site_code = site_code,
                                                             bsnr = bsnr,
                                                             )
        if not organisation_id:
            r.error(404, current.ERROR.BAD_RECORD)

        # Look up sites
        sites = cls.get_sites(organisation_id)

        # Retrieve activity data (if requested)
        report = ref.get("report")
        activity = interval = None
        if report:
            if isinstance(report, list) and len(report) == 2:

                start, end = report
                parse_date = current.calendar.parse_date

                start = parse_date(start) if start else False
                end = parse_date(end) if end else False

                if start is None or end is None:
                    r.error(400, "Invalid date format in report parameter")
                if start and end and start > end:
                    start, end = end, start

                site_ids = [site.org_facility.site_id for site in sites]

                activity = cls.get_site_activity(site_ids, start=start, end=end)
                interval = [start.isoformat() if start else None,
                            end.isoformat() if end else None,
                            ]
            else:
                r.error(400, "Invalid report parameter format")

        # Compile sites info
        sites_info = []
        total_tests, total_positive = 0, 0
        for site in sites:
            facility = site.org_facility
            location = site.gis_location

            site_data = {
                "name": facility.name,
                "code": facility.code,
                "phone": facility.phone1,
                "email": facility.email,
                }

            if location:
                site_data["location"] = {
                    "L1": location.L1,
                    "L2": location.L2,
                    "L3": location.L3,
                    "L4": location.L4,
                    "address": location.addr_street,
                    "postcode": location.addr_postcode,
                    }
            else:
                site_data["location"] = None

            if activity is not None:
                site_activity = activity.get(facility.site_id)
                if site_activity:
                    tests_total, tests_positive = site_activity
                else:
                    tests_total, tests_positive = 0, 0
                site_data["activity"] = {"interval": interval,
                                         "testsTotal": tests_total,
                                         "testsPositive": tests_positive,
                                         }
                total_tests += tests_total
                total_positive += tests_positive

            sites_info.append(site_data)

        if activity is not None:
            # Add provider activity (totals)
            provider_info["activity"] = {"interval": interval,
                                         "testsTotal": total_tests,
                                         "testsPositive": total_positive,
                                         }

        # Complete response
        output = {"provider": provider_info,
                  "sites": sites_info,
                  }

        # Return as JSON
        response = current.response
        if response:
            response.headers["Content-Type"] = "application/json; charset=utf-8"
        return json.dumps(output, separators=(",", ":"), ensure_ascii=False)

    # -------------------------------------------------------------------------
    @classmethod
    def lookup_provider(cls, organisation_id, provider_id=None, bsnr=None, site_code=None):
        """
            Identify a test provider organisation

            Args:
                organisation_id: the organisation record ID
                provider_id: the OrgID tag of the organisation
                bsnr: the BSNR tag of the organisation
                site_code: a test station ID of the organisation
            Returns:
                the organisation record, or None

            Notes:
                - at least one search parameter must be provided
                - if multiple parameters are provided, all of them must apply
                - multiple matches will be treated as no match
        """

        # Must have at least one search parameter
        if not any((organisation_id, provider_id, site_code, bsnr)):
            return None

        db = current.db
        s3db = current.s3db

        # Lookup the organisation
        otable = s3db.org_organisation
        gtable = s3db.org_group
        mtable = s3db.org_group_membership
        ttable = s3db.org_organisation_tag
        btable = s3db.org_bsnr

        # Organisation must belong to TESTSTATIONS group
        from .config import TESTSTATIONS
        join = [mtable.on((mtable.organisation_id == otable.id) & \
                          (mtable.deleted == False)),
                gtable.on((gtable.id == mtable.group_id) & \
                          (gtable.name == TESTSTATIONS) & \
                          (gtable.deleted == False)),
                ]

        # Base query
        query = (otable.deleted == False)
        if organisation_id:
            query = (otable.id == organisation_id) & query

        # Additional parameters
        if provider_id:
            join.append(
                ttable.on((ttable.organisation_id == otable.id) & \
                          (ttable.tag == "OrgID") & \
                          (ttable.value.upper() == provider_id.upper()) & \
                          (ttable.deleted == False))
                )
        if bsnr:
            join.append(
                btable.on((btable.organisation_id == otable.id) & \
                          (btable.bsnr.upper() == bsnr.upper()) & \
                          (btable.deleted == False))
                )
        if site_code:
            ftable = s3db.org_facility
            sites = db((ftable.code.upper() == site_code.upper()) & \
                       (ftable.deleted == False))._select(ftable.organisation_id)
            query &= otable.id.belongs(sites)


        rows = db(query).select(otable.id,
                                otable.name,
                                otable.website,
                                join = join,
                                limitby = (0, 2),
                                )
        organisation = rows.first() if len(rows) == 1 else None

        if organisation:
            organisation_id = organisation.id
            provider_info = {"name": organisation.name,
                             "website": organisation.website,
                             }

            provider_info["type"] = cls.get_provider_type(organisation_id)
            provider_info.update(cls.get_provider_tags(organisation_id))
            provider_info["commission"] = cls.get_commission_data(organisation_id)
        else:
            organisation_id = provider_info = None

        return organisation_id, provider_info

    # -------------------------------------------------------------------------
    @staticmethod
    def get_provider_tags(organisation_id):
        """
            Retrieves the organisation tags (OrgID, BSNR) of a provider

            Args:
                organisation_id: the provider organisation ID
            Returns:
                the tags as dict
        """

        db = current.db
        s3db = current.s3db

        values = {}

        ttable = s3db.org_organisation_tag
        query = (ttable.organisation_id == organisation_id) & \
                (ttable.tag == "OrgID") & \
                (ttable.deleted == False)
        row = db(query).select(ttable.value, limitby=(0, 1)).first()
        values["code"] = row.value if row else None

        btable = s3db.org_bsnr
        query = (btable.organisation_id == organisation_id) & \
                (btable.deleted == False)
        row = db(query).select(btable.bsnr, limitby=(0, 1)).first()
        values["bsnr"] = row.bsnr if row else None

        return values

    # -------------------------------------------------------------------------
    @staticmethod
    def get_provider_type(organisation_id):
        """
            Looks up the organisation type(s) of a provider

            Args:
                organisation_id: the provider organisation ID
            Returns:
                the type name(s) as string (comma-separated if multiple)
        """

        db = current.db
        s3db = current.s3db

        ttable = s3db.org_organisation_type
        ltable = s3db.org_organisation_organisation_type

        join = ttable.on(ttable.id == ltable.organisation_type_id)
        query = (ltable.organisation_id == organisation_id) & \
                (ltable.deleted == False)
        rows = db(query).select(ttable.id,
                                ttable.name,
                                join = join,
                                )
        return ", ".join(row.name for row in rows) if rows else None

    # -------------------------------------------------------------------------
    @staticmethod
    def get_commission_data(organisation_id):
        """
            Retrieves details of all commissions for a provider

            Args:
                organisation_id: the provider organisation ID
            Returns:
                a list of dicts with commission details
        """

        db = current.db
        s3db = current.s3db

        ctable = s3db.org_commission
        query = (ctable.organisation_id == organisation_id) & \
                (ctable.deleted == False)
        commissions = db(query).select(ctable.date,
                                       ctable.end_date,
                                       ctable.status,
                                       ctable.status_date,
                                       )
        dtfmt = lambda dt: dt.isoformat() if dt else '--'

        clist = []
        for commission in commissions:
            clist.append({"start": dtfmt(commission.date),
                          "end": dtfmt(commission.end_date),
                          "status": commission.status,
                          "statusDate": dtfmt(commission.status_date),
                          })

        return clist

    # -------------------------------------------------------------------------
    @staticmethod
    def get_sites(organisation_id):
        """
            Retrieves all sites (test stations) belonging to a provider

            Args:
                organisation_id: the provider organisation ID
            Returns:
                Rows (joined org_facility+gis_location)
        """

        s3db = current.s3db

        ftable = s3db.org_facility
        ltable = s3db.gis_location

        left = ltable.on(ltable.id == ftable.location_id)

        query = (ftable.organisation_id == organisation_id) & \
                (ftable.deleted == False)
        return current.db(query).select(ftable.id,
                                        ftable.name,
                                        ftable.code,
                                        ftable.phone1,
                                        ftable.email,
                                        ftable.site_id,
                                        ltable.id,
                                        ltable.L1,
                                        ltable.L2,
                                        ltable.L3,
                                        ltable.L4,
                                        ltable.addr_street,
                                        ltable.addr_postcode,
                                        left = left,
                                        )

    # -------------------------------------------------------------------------
    @staticmethod
    def get_site_activity(site_ids, start=None, end=None):
        """
            Reports the testing activity of sites in a certain date interval

            Args:
                site_ids: list|set of site IDs
                start: the start date
                end: the end date
            Returns:
                a dict {site_id: (tests_total, tests_positive)}

            Notes:
                - interval includes both start and end date
                - no start date means all available reports (before end)
                - no end date means all available reports (after start)
        """

        table = current.s3db.disease_testing_report

        query = (table.site_id.belongs(site_ids))
        if start:
            query &= (table.date >= start)
        if end:
            query &= (table.date <= end)
        query &= (table.deleted == False)

        site_id = table.site_id
        tests_total = table.tests_total.sum()
        tests_positive = table.tests_positive.sum()

        rows = current.db(query).select(site_id,
                                        tests_total,
                                        tests_positive,
                                        groupby=site_id,
                                        )

        activity = {}
        for row in rows:
            activity[row[site_id]] = (row[tests_total], row[tests_positive])

        return activity

# =============================================================================
class PersonRepresentDetails(pr_PersonRepresentContact):
    """
        Custom representation of person_id in read-perspective on
        representatives tab of organisations, includes additional
        person details like date and place of birth, address
    """

    # -------------------------------------------------------------------------
    def represent_row_html(self, row):
        """
            Represent a row with contact information, styleable HTML

            Args:
                row: the Row
        """

        T = current.T

        output = DIV(SPAN(s3_fullname(row),
                          _class = "person-name",
                          ),
                     _class = "person-repr",
                     )

        table = self.table

        try:
            dob = row.date_of_birth
        except AttributeError:
            dob = None
        dob = table.date_of_birth.represent(dob) if dob else "-"

        try:
            pob = row.place_of_birth
        except AttributeError:
            pob = None
        if not pob:
            pob = "-"

        addr_details = {"place": row.get("addr_place") or "-",
                        "postcode": row.get("addr_postcode") or "",
                        "street": row.get("addr_street") or "-",
                        }
        if any(value and value != "-" for value in addr_details.values()):
            address = "{street}, {postcode} {place}".format(**addr_details)
        else:
            address = "-"

        pe_id = row.pe_id
        email = self._email.get(pe_id) if self.show_email else None
        phone = self._phone.get(pe_id) if self.show_phone else None

        details = TABLE(TR(TH("%s:" % T("Date of Birth")),
                           TD(dob),
                           _class = "person-dob"
                           ),
                        TR(TH("%s:" % T("Place of Birth")),
                           TD(pob),
                           _class = "person-pob"
                           ),
                        TR(TH(ICON("mail")),
                           TD(A(email, _href="mailto:%s" % email) if email else "-"),
                           _class = "person-email"
                           ),
                        TR(TH(ICON("phone")),
                           TD(phone if phone else "-"),
                           _class = "person-phone",
                           ),
                        TR(TH(ICON("home")),
                           TD(address),
                           _class = "person-address",
                           ),
                        _class="person-details",
                        )
        output.append(details)

        return output

    # -------------------------------------------------------------------------
    def lookup_rows(self, key, values, fields=None):
        """
            Custom rows lookup

            Args:
                key: the key Field
                values: the values
                fields: unused (retained for API compatibility)
        """

        db = current.db
        s3db = current.s3db

        # Lookup person rows + store contact details in instance
        rows = super().lookup_rows(key, values, fields=fields)

        # Lookup dates of birth
        table = self.table
        count = len(values)
        query = (key == values[0]) if count == 1 else key.belongs(values)
        dob = db(query).select(table.id,
                               table.date_of_birth,
                               limitby = (0, count),
                               ).as_dict()

        # Lookup places of birth
        dtable = s3db.pr_person_details
        if count == 1:
            query = (dtable.person_id == values[0])
        else:
            query = (dtable.person_id.belongs(values))
        query &= (dtable.place_of_birth != None) & \
                 (dtable.deleted == False)

        details = db(query).select(dtable.person_id,
                                   dtable.place_of_birth,
                                   ).as_dict(key="person_id")

        # Lookup addresses
        atable = s3db.pr_address
        ltable = s3db.gis_location

        join = ltable.on(ltable.id == atable.location_id)
        query = (atable.pe_id.belongs({row.pe_id for row in rows})) & \
                (atable.type.belongs((1,2))) & \
                (atable.deleted == False)
        addresses = db(query).select(atable.pe_id,
                                     ltable.id,
                                     #ltable.L2,
                                     ltable.L3,
                                     ltable.L4,
                                     ltable.L5,
                                     ltable.addr_street,
                                     ltable.addr_postcode,
                                     join = join,
                                     orderby = (atable.type, atable.created_on),
                                     ).as_dict(key="pr_address.pe_id")

        # Extend person rows with additional details
        for row in rows:
            detail = dob.get(row.id)
            if detail:
                row.date_of_birth = detail["date_of_birth"]

            detail = details.get(row.id)
            if detail:
                row.place_of_birth = detail["place_of_birth"]

            address = addresses.get(row.pe_id)
            if address:
                location, place = address["gis_location"], None
                for level in ("L5", "L4", "L3"):
                    place = location[level]
                    if place:
                        break
                if place:
                    row.addr_place = place
                    row.addr_street = location["addr_street"]
                    row.addr_postcode = location["addr_postcode"]
                    #row.addr_adm = location["L2"]

        return rows

# END =========================================================================
