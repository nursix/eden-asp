"""
    Helper functions and classes for BETRA

    License: MIT
"""

from gluon import current, URL, A, I, SPAN, TAG

from core import WorkflowOptions, s3_fullname

# =============================================================================
def get_role_realms(role):
    """
        Get all realms for which a role has been assigned

        Args:
            role: the role ID or role UUID

        Returns:
            - list of pe_ids the current user has the role for,
            - None if the role is assigned site-wide, or an
            - empty list if the user does not have the role, or has the role
              without realm
    """

    auth = current.auth

    if isinstance(role, str):
        role_id = auth.get_role_id(role)
    else:
        role_id = role

    role_realms = []
    user = auth.user
    if user and role_id:
        role_realms = user.realms.get(role_id, role_realms)

    return role_realms

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
def get_managed_orgs(role="ORG_ADMIN", group=None, cacheable=True):
    """
        Get organisations managed by the current user

        Args:
            role: the managing user role (default: ORG_ADMIN)
            group: the organisation group
            cacheable: whether the result can be cached

        Returns:
            list of organisation_ids
    """

    s3db = current.s3db

    otable = s3db.org_organisation
    query = (otable.deleted == False)

    realms = get_role_realms(role)
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
def get_user_orgs(roles=None, cacheable=True, limit=None):
    """
        Get the IDs of all organisations the user has any of the
        given roles for (default: STAFF|ORG_ADMIN)

        Args:
            roles: tuple|list of role IDs/UIDs
            cacheable: the result can be cached
            limit: limit to this number of organisation IDs

        Returns:
            list of organisation_ids (can be empty)
    """

    s3db = current.s3db

    if not roles:
        roles = ("STAFF", "ORG_ADMIN")

    realms = set()

    for role in roles:
        role_realms = get_role_realms(role)
        if role_realms is None:
            realms = None
            break
        if role_realms:
            realms.update(role_realms)

    otable = s3db.org_organisation
    query = (otable.deleted == False)
    if realms:
        query = (otable.pe_id.belongs(realms)) & query
    elif realms is not None:
        return []

    rows = current.db(query).select(otable.id,
                                    cache = s3db.cache if cacheable else None,
                                    limitby = (0, limit) if limit else None,
                                    )

    return [row.id for row in rows]

# -----------------------------------------------------------------------------
def permitted_orgs(permission, tablename):
    """
        Get the IDs of the organisations for which the user has
        a certain permission for a certain table

        Args:
            permission: the permission name
            tablename: the table name

        Returns:
            List of organisation IDs
    """

    db = current.db
    s3db = current.s3db
    auth = current.auth

    permissions = auth.permission
    permitted_realms = permissions.permitted_realms(tablename, permission)

    otable = s3db.org_organisation
    query = (otable.deleted == False)
    if permitted_realms is not None:
        query = (otable.pe_id.belongs(permitted_realms)) & query
    orgs = db(query).select(otable.id)

    return [o.id for o in orgs]

# =============================================================================
def get_default_organisation():
    """
        The organisation the user has the STAFF or ORG_ADMIN role for
        (if only one organisation)

        Returns:
            organisation ID
    """

    auth = current.auth
    if not auth.s3_logged_in() or auth.s3_has_roles("ADMIN", "ORG_GROUP_ADMIN"):
        return None

    s3 = current.response.s3
    organisation_id = s3.betra_default_organisation

    if organisation_id is None:

        organisation_ids = get_user_orgs(limit=2)
        if len(organisation_ids) == 1:
            organisation_id = organisation_ids[0]
        else:
            organisation_id = None
        s3.betra_default_organisation = organisation_id

    return organisation_id

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

# =============================================================================
# Helpers for DVR rheader
# =============================================================================
def client_name_age(record):
    """
        Represent a client as name, gender and age; for case file rheader

        Args:
            record: the client record (pr_person)

        Returns:
            HTML
    """

    T = current.T

    pr_age = current.s3db.pr_age

    age = pr_age(record)
    if age is None:
        age = "?"
        unit = T("years")
    elif age == 0:
        age = pr_age(record, months=True)
        unit = T("months") if age != 1 else T("month")
    else:
        unit = T("years") if age != 1 else T("year")

    icons = {2: "fa fa-venus",
             3: "fa fa-mars",
             4: "fa fa-transgender-alt",
             }
    icon = I(_class=icons.get(record.gender, "fa fa-genderless"))

    client = TAG[""](s3_fullname(record, truncate=False),
                     SPAN(icon, "%s %s" % (age, unit), _class="client-gender-age"),
                     )
    return client

# END =========================================================================
