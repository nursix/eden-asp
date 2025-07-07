"""
    AUTH module customisations for RLPPTM

    License: MIT
"""

from gluon import current, URL

from s3dal import original_tablename

# -------------------------------------------------------------------------
def rlpptm_realm_entity(table, row):
    """
        Assign a Realm Entity to records
    """

    db = current.db
    s3db = current.s3db
    settings = current.deployment_settings

    realm_entity = 0 # = use default
    tablename = original_tablename(table)

    #if tablename in ("org_group",
    #                 "org_organisation",
    #                 "org_facility",
    #                 "org_office",
    #                 ):
    #    # These entities own themselves by default, and form
    #    # a OU hierarchy (default ok)
    #    realm_entity = 0
    #
    if tablename == "pr_person":
        # Human resources belong to their org's realm
        htable = s3db.hrm_human_resource
        otable = s3db.org_organisation

        left = otable.on(otable.id == htable.organisation_id)
        query = (htable.person_id == row.id) & \
                (htable.deleted == False)
        org = db(query).select(otable.pe_id,
                               left = left,
                               limitby = (0, 1),
                               ).first()
        if org:
            realm_entity = org.pe_id

    elif tablename == "usr_filter":

        realm_entity = None

    elif tablename in ("disease_case_diagnostics",
                       "disease_testing_report",
                       ):
        # Test results / daily reports inherit realm-entity
        # from the testing site
        table = s3db.table(tablename)
        stable = s3db.org_site
        query = (table._id == row.id) & \
                (stable.site_id == table.site_id)
        site = db(query).select(stable.realm_entity,
                                limitby = (0, 1),
                                ).first()
        if site:
            realm_entity = site.realm_entity
        else:
            # Fall back to user organisation
            user = current.auth.user
            organisation_id = user.organisation_id if user else None
            if not organisation_id:
                # Fall back to default organisation
                organisation_id = settings.get_org_default_organisation()
            if organisation_id:
                realm_entity = s3db.pr_get_pe_id("org_organisation",
                                                 organisation_id,
                                                 )

    elif tablename == "disease_testing_demographic":
        # Demographics subtotals inherit the realm-entity from
        # the main report
        table = s3db.table(tablename)
        rtable = s3db.disease_testing_report
        query = (table._id == row.id) & \
                (rtable.id == table.report_id)
        report = db(query).select(rtable.realm_entity,
                                  limitby = (0, 1),
                                  ).first()
        if report:
            realm_entity = report.realm_entity
        else:
            # Fall back to user organisation
            user = current.auth.user
            organisation_id = user.organisation_id if user else None
            if not organisation_id:
                # Fall back to default organisation
                organisation_id = settings.get_org_default_organisation()
            if organisation_id:
                realm_entity = s3db.pr_get_pe_id("org_organisation",
                                                 organisation_id,
                                                 )

    elif tablename == "doc_document":

        realm_entity = doc_realm_entity(table, row)

    #elif tablename == "fin_voucher_program":
    #
    #    # Voucher programs are owned by the organisation managing
    #    # them (default ok)
    #    realm_entity = 0
    #
    #elif tablename == "fin_voucher":
    #
    #    # Vouchers are owned by the issuer PE (default ok)
    #    realm_entity = 0
    #
    #elif tablename == "fin_voucher_debit":
    #
    #    # Debits are owned by the provider PE (default ok)
    #    realm_entity = 0
    #
    #elif tablename == "fin_voucher_claim":
    #
    #    # Claims are owned by the provider PE (default ok)
    #    realm_entity = 0
    #
    elif tablename == "fin_voucher_invoice":
        # Invoices are owned by the accountant organization of the billing
        table = s3db.table(tablename)
        btable = s3db.fin_voucher_billing
        query = (table._id == row.id) & \
                (btable.id == table.billing_id)
        billing = db(query).select(btable.organisation_id,
                                   btable.realm_entity,
                                   limitby = (0, 1),
                                   ).first()
        if billing:
            organisation_id = billing.organisation_id
            if organisation_id:
                realm_entity = s3db.pr_get_pe_id("org_organisation",
                                                 organisation_id,
                                                 )
            else:
                realm_entity = billing.realm_entity

    elif tablename in ("fin_voucher_billing",
                       "fin_voucher_transaction",
                       ):
        # Billings and transactions inherit realm-entity of the program
        table = s3db.table(tablename)
        ptable = s3db.fin_voucher_program
        query = (table._id == row.id) & \
                (ptable.id == table.program_id)
        program = db(query).select(ptable.realm_entity,
                                   limitby = (0, 1),
                                   ).first()
        if program:
            realm_entity = program.realm_entity

    #elif tablename == "jnl_issue":
    #
    #    # Journal issues are owned by the organisation they are about (default ok)
    #    realm_entity = 0
    #
    elif tablename == "jnl_note":
        # Journal notes inherit from the issue they belong to
        table = s3db.table(tablename)
        itable = s3db.jnl_issue
        query = (table._id == row.id) & \
                (itable.id == table.issue_id)
        issue = db(query).select(itable.realm_entity,
                                 limitby = (0, 1),
                                 ).first()
        if issue:
            realm_entity = issue.realm_entity

    elif tablename in ("pr_person_details",
                       "pr_person_tag",
                       ):
        # Inherit from person via person_id
        table = s3db.table(tablename)
        ptable = s3db.pr_person
        query = (table._id == row.id) & \
                (ptable.id == table.person_id)
        person = db(query).select(ptable.realm_entity,
                                  limitby = (0, 1),
                                  ).first()
        if person:
            realm_entity = person.realm_entity

    elif tablename in ("pr_address",
                       "pr_contact",
                       "pr_contact_emergency",
                       ):
        # Inherit from person via PE
        table = s3db.table(tablename)
        ptable = s3db.pr_person
        query = (table._id == row.id) & \
                (ptable.pe_id == table.pe_id)
        person = db(query).select(ptable.realm_entity,
                                  limitby = (0, 1),
                                  ).first()
        if person:
            realm_entity = person.realm_entity

    elif tablename in ("inv_send", "inv_recv"):
        # Shipments inherit realm-entity from the sending/receiving site
        table = s3db.table(tablename)
        stable = s3db.org_site
        query = (table._id == row.id) & \
                (stable.site_id == table.site_id)
        site = db(query).select(stable.realm_entity,
                                limitby = (0, 1),
                                ).first()
        if site:
            realm_entity = site.realm_entity

    #elif tablename in ("org_bsnr",
    #                   "org_commission",
    #                   "org_representative",
    #                   "org_verification",
    #                   ):
    #   # BSNR/Commission/Representative/Verification
    #   # are owned by the subject organisation (default ok)
    #   realm_entity = 0

    return realm_entity

# -------------------------------------------------------------------------
def doc_realm_entity(table, row):
    """
        Realm rule for doc_document
    """

    db = current.db
    s3db = current.s3db

    realm_entity = 0

    dtable = s3db.doc_document
    etable = s3db.doc_entity

    # Get the document record including instance type of doc_entity
    left = etable.on(etable.doc_id == dtable.doc_id)
    query = (dtable.id == row.id)
    row = db(query).select(dtable.id,
                           dtable.doc_id,
                           dtable.organisation_id,
                           etable.instance_type,
                           left = left,
                           limitby = (0, 1),
                           ).first()
    if not row:
        return realm_entity

    document = row.doc_document
    instance_type = row.doc_entity.instance_type

    # Inherit the realm entity from instance, if available
    if document.doc_id and instance_type:
        itable = s3db.table(instance_type)
        if itable and "realm_entity" in itable.fields:
            query = (itable.doc_id == document.doc_id)
            instance = db(query).select(itable.realm_entity,
                                        limitby = (0, 1),
                                        ).first()
            if instance:
                realm_entity = instance.realm_entity

    # Fallback: use context organisation as realm entity
    if realm_entity == 0 and document.organisation_id:

        realm_entity = s3db.pr_get_pe_id("org_organisation",
                                         document.organisation_id,
                                         )
    return realm_entity

# -------------------------------------------------------------------------
def consent_check():
    """
        Check pending consent at login
    """

    auth = current.auth

    person_id = auth.s3_logged_in_person()
    if not person_id:
        return None

    required = None

    has_role = auth.s3_has_role
    if has_role("ADMIN"):
        required = None
    elif has_role("VOUCHER_ISSUER"):
        required = ["STORE", "RULES_ISS"]
    else:
        from ..helpers import get_managed_facilities
        if get_managed_facilities(cacheable=False):
            required = ["TPNDO"]

    if required:
        from core import ConsentTracking
        consent = ConsentTracking(required)
        pending = consent.pending_responses(person_id)
    else:
        pending = None

    return pending

# -----------------------------------------------------------------------------
def auth_consent_resource(r, tablename):

    T = current.T

    user_org = "person_id$user.user_id:org_organisation_user.organisation_id"

    from core import DateFilter, OptionsFilter, TextFilter

    filter_widgets = [TextFilter(["%s$name" % user_org,
                                  "person_id$first_name",
                                  "person_id$last_name",
                                  "option_id$name",
                                  ],
                                 label = T("Search"),
                                 ),
                      OptionsFilter("consenting", cols=2),
                      DateFilter("date", hidden=True),
                      ]

    # Custom list fields to include the user organisation
    list_fields = ["date",
                   user_org,
                   "person_id",
                   "option_id",
                   "consenting",
                   "expires_on",
                   ]

    current.s3db.configure("auth_consent",
                           filter_widgets = filter_widgets,
                           list_fields = list_fields,
                           orderby = "auth_consent.date desc",
                           )

# -------------------------------------------------------------------------
def approve_user(r, **args):

    T = current.T
    auth = current.auth

    from gluon import redirect
    from ..config import TESTSTATIONS

    db = current.db
    user = db(db.auth_user.id == r.id).select(limitby = (0, 1)
                                                ).first()
    org_group_id = user.org_group_id
    if org_group_id:
        # Check if this is a COVID-19 Test Station
        ogtable = current.s3db.org_group
        org_group = db(ogtable.id == org_group_id).select(ogtable.name,
                                                          limitby = (0, 1)
                                                          ).first()
        if org_group and org_group.name == TESTSTATIONS:
            # Custom Approval process
            redirect(URL(c= "default", f="index", args=["approve", r.id]))

    # Default Approval
    auth.s3_approve_user(user)
    current.session.confirmation = T("User Account has been Approved")
    redirect(URL(args=[r.id, "roles"]))

# -------------------------------------------------------------------------
def auth_user_resource(r, tablename):
    """
        Configure custom approvals function

    """

    current.s3db.configure("auth_user",
                            approve_user = approve_user,
                            )

# -------------------------------------------------------------------------
def pending_response():
    """
        Check for pending responses to mandatory data inquiry

        Returns:
            URL to redirect
    """

    if not current.deployment_settings.get_custom("daycare_testing_inquiry"):
        return None

    pending = None

    # Get pending responders
    managed_orgs = pending = None
    if current.auth.s3_has_role("ORG_ADMIN", include_admin=False):
        from ..config import TESTSTATIONS
        from ..helpers import get_managed_orgs
        managed_orgs = get_managed_orgs(TESTSTATIONS)
        if managed_orgs:
            pending = current.s3db.disease_daycare_testing_get_pending_responders(managed_orgs)

    request = current.request

    if pending:
        response_url = None
        # Only set a direct URL when not already there
        if request.controller != "disease" or request.function != "daycare_testing":
            next_url = request.get_vars.get("_next")
            if not next_url:
                next_url = URL()
            response_url = URL(c = "disease",
                               f = "daycare_testing",
                               args = ["create"],
                               vars = {"_next": next_url},
                               )
        # Return to this page until there are no more pending responders
        current.session.s3.mandatory_page = True
        return response_url

    else:
        # No further pending responses, moving on
        next_url = request.get_vars.get("_next")
        if not next_url:
            next_url = URL(c="default", f="index")
        current.session.s3.mandatory_page = False
        return next_url

# END =========================================================================
