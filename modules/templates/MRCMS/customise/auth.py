"""
    AUTH module customisations for MRCMS

    License: MIT
"""

from gluon import current

from s3dal import original_tablename

from core import IS_ONE_OF

# -------------------------------------------------------------------------
def realm_entity(table, row):
    """
        Assign a Realm Entity to records
    """

    db = current.db
    s3db = current.s3db

    tablename = original_tablename(table)

    realm_entity = 0

    # PR ============================================================

    if tablename == "pr_person":

        organisation_id = None

        # NOTE these rules are only effective upon explicit realm
        #      update onaccept of the case/staff record - because
        #      the person record is, necessarily, written first!
        if not organisation_id:
            # Client records are owned by the case organisation
            ctable = s3db.dvr_case
            query = (ctable.person_id == row.id) & (ctable.deleted == False)
            case = db(query).select(ctable.organisation_id,
                                    limitby = (0, 1),
                                    ).first()
            if case:
                organisation_id = case.organisation_id

        if not organisation_id:
            # Staff records are owned by the employer organisation
            htable = s3db.hrm_human_resource
            query = (htable.person_id == row.id) & (htable.deleted == False)
            staff = db(query).select(htable.organisation_id,
                                     limitby = (0, 1),
                                     ).first()
            if staff:
                organisation_id = staff.organisation_id

        if organisation_id:
            realm_entity = s3db.pr_get_pe_id("org_organisation", organisation_id)

    elif tablename in ("pr_group_membership",
                       "pr_identity",
                       "pr_person_details",
                       "pr_person_tag",
                       ):
        # Inherit from person via person_id
        table = s3db.table(tablename)
        realm_entity = person_realm_entity(table, row, default=realm_entity)

    elif tablename in ("pr_address",
                       "pr_contact",
                       "pr_contact_emergency",
                       "pr_image",
                       ):
        # Inherit from person via pe_id
        table = s3db.table(tablename)
        realm_entity = person_realm_entity(table, row, key="pe_id", default=realm_entity)

    elif tablename == "pr_group":
         # No realm-entity for case groups
        table = s3db.pr_group
        query = table._id == row.id
        group = db(query).select(table.group_type, limitby=(0, 1)).first()
        if group and group.group_type == 7:
            realm_entity = None

    elif tablename == "pr_filter":
        realm_entity = None

    # DVR ===========================================================

    elif tablename in ("dvr_case_flag",
                       "dvr_appointment_type",
                       "dvr_case_event_type",
                       ):
        # Owned by the organisation for which they are defined (default okay)
        pass

    elif tablename == "dvr_case_flag_case":

        # Owned by the organisation defining the flag
        table = s3db.table(tablename)
        ftable = s3db.dvr_case_flag
        query = (table._id == row.id) & (ftable.id == table.flag_id)
        flag = db(query).select(ftable.organisation_id, limitby=(0, 1)).first()
        if flag and flag.organisation_id:
            realm_entity = s3db.pr_get_pe_id("org_organisation", flag.organisation_id)
        else:
            # Inherit from person via person_id
            realm_entity = person_realm_entity(table, row, default=realm_entity)

    elif tablename == "dvr_case_appointment":

        # Owned by the organisation defining the appointment type
        table = s3db.table(tablename)
        ttable = s3db.dvr_case_appointment_type
        query = (table._id == row.id) & (ttable.id == table.type_id)
        atype = db(query).select(ttable.organisation_id, limitby=(0, 1)).first()
        if atype and atype.organisation_id:
            realm_entity = s3db.pr_get_pe_id("org_organisation", atype.organisation_id)
        else:
            # Inherit from person via person_id
            realm_entity = person_realm_entity(table, row, default=realm_entity)

    elif tablename == "dvr_case_event":

        # Owned by the organisation defining the event type
        table = s3db.table(tablename)
        ttable = s3db.dvr_case_event_type
        query = (table._id == row.id) & (ttable.id == table.type_id)
        etype = db(query).select(ttable.organisation_id, limitby=(0, 1)).first()
        if etype and etype.organisation_id:
            realm_entity = s3db.pr_get_pe_id("org_organisation", etype.organisation_id)
        else:
            # Inherit from person via person_id
            realm_entity = person_realm_entity(table, row, default=realm_entity)

    elif tablename == "dvr_case_activity_update":
        realm_entity = inherit_realm(tablename, row, "dvr_case_activity", "case_activity_id")

    elif tablename == "dvr_response_action_theme":
        realm_entity = inherit_realm(tablename, row, "dvr_response_action", "action_id")

    elif tablename in ("dvr_vulnerability_case_activity",
                       "dvr_vulnerability_response_action",
                       ):
        realm_entity = inherit_realm(tablename, row, "dvr_vulnerability", "vulnerability_id")

    elif tablename in ("dvr_case_activity",
                       "dvr_case_details",
                       "dvr_case_language",
                       "dvr_note",
                       "dvr_task",
                       "dvr_residence_status",
                       "dvr_response_action",
                       "dvr_service_contact",
                       "dvr_vulnerability",
                       ):
        # Inherit from person via person_id
        table = s3db.table(tablename)
        realm_entity = person_realm_entity(table, row, default=realm_entity)

    elif tablename in ("dvr_case_activity_status",
                       "dvr_need",
                       "dvr_response_status",
                       "dvr_response_theme",
                       "dvr_response_type",
                       "dvr_service_contact_type",
                       "dvr_vulnerability_type",
                       ):
        realm_entity = None

    # CR ============================================================

    elif tablename == "cr_shelter":
        # Self-owned, controlled by OU hierarchy (default ok)
        pass

    elif tablename in ("cr_shelter_unit",
                       "cr_shelter_note",
                       ):
        realm_entity = inherit_realm(tablename, row, "cr_shelter", "shelter_id")

    elif tablename in ("cr_shelter_registration",
                       "cr_shelter_registration_history",
                       ):
        # Inherit from person via person_id
        table = s3db.table(tablename)
        realm_entity = person_realm_entity(table, row, default=realm_entity)

    # DOC ===========================================================

    elif tablename in ("doc_document",
                       "doc_image",
                       ):
        # Inherit from doc entity, alternatively context organisation
        table = s3db.table(tablename)
        realm_entity = doc_realm_entity(table, row)

    # ORG ====================================================

    elif tablename in ("org_group",
                       "org_organisation",
                       ):
        # Self-owned, controlled by OU hierarchy (default ok)
        pass

    elif tablename in ("org_site_presence",
                       "org_site_presence_event",
                       ):
        # Owned by the site, OU of managing organisation (default ok)
        pass

    # ACT ===========================================================

    elif tablename in ("act_activity",
                       "act_issue",
                       "act_task",
                       ):
        # Owned by the organisation registering them (default okay)
        pass

    elif tablename == "act_activity_type":
        # No realm entity
        realm_entity = None

    elif tablename in ("act_beneficiary",
                       ):
        # Inherit from person via person_id
        table = s3db.table(tablename)
        realm_entity = person_realm_entity(table, row, default=realm_entity)

    # MED ===================================================

    elif tablename == "med_unit":
        # Self-owned, controlled by OU hierarchy (default ok)
        pass

    elif tablename in ("med_area",
                       "med_patient",
                       ):
        realm_entity = inherit_realm(tablename, row, "med_unit", "unit_id")

    elif tablename in ("med_anamnesis",
                       "med_medication",
                       "med_vaccination",
                       ):
        # Inherit from person via person_id
        table = s3db.table(tablename)
        realm_entity = person_realm_entity(table, row, default=realm_entity)

    elif tablename in ("med_status",
                       "med_vitals",
                       "med_treatment",
                       "med_epicrisis",
                       ):
        realm_entity = inherit_realm(tablename, row, "med_patient", "patient_id")

    elif tablename in ("med_substance",
                       "med_vaccination_type",
                       ):
        realm_entity = None

    # SUPPLY ========================================================

    elif tablename in ("supply_catalog",
                       "supply_distribution_set",
                       "supply_distribution",
                       ):
        # Owned by the managing organisation (default ok)
        pass

    elif tablename in ("supply_item_category",
                       "supply_catalog_item",
                       ):
        # Inherit from catalog via catalog_id
        realm_entity = inherit_realm(tablename, row, "supply_catalog", "catalog_id")

    elif tablename == "supply_distribution_set_item":
        # Inherit from distribution set via distribution_set_id
        realm_entity = inherit_realm(tablename, row, "supply_distribution_set", "distribution_set_id")


    elif tablename == "supply_distribution_item":
        # Inherit from distribution via distribution_id
        realm_entity = inherit_realm(tablename, row, "supply_distribution", "distribution_id")

    # SECURITY ======================================================

    elif tablename == "security_seized_item_depository":
        # Owned by the managing organisation (default ok)
        pass

    elif tablename in ("security_seized_item",
                       ):
        # Inherit from person via person_id
        table = s3db.table(tablename)
        realm_entity = person_realm_entity(table, row, default=realm_entity)

    # ===============================================================

    return realm_entity

# -------------------------------------------------------------------------
def doc_realm_entity(table, row):
    """
        Realm rule for doc_document/doc_image
    """

    db = current.db
    s3db = current.s3db

    realm_entity = 0

    etable = s3db.doc_entity

    # Get the document record including instance type of doc_entity
    left = etable.on(etable.doc_id == table.doc_id)
    query = (table.id == row.id)
    row = db(query).select(table.id,
                           table.doc_id,
                           table.organisation_id,
                           etable.instance_type,
                           left = left,
                           limitby = (0, 1),
                           ).first()
    if not row:
        return realm_entity

    document = row[table]
    instance_type = row.doc_entity.instance_type

    # Newsletter attachments do not belong to any realm
    if instance_type == "cms_newsletter":
        return None

    # Inherit the realm entity from instance, if available
    if document.doc_id and instance_type and instance_type != "pr_group":
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
def person_realm_entity(table, row, key="person_id", default=0):
    """
        Returns the realm entity of the context person record

        Args:
            table: the Table
            row: the Row
            key: the key referencing pr_person (person_id|pe_id)
            default: the default to return if no context record is found

        Returns:
            the realm entity (pe_id) of the context person record
    """

    ptable = current.s3db.pr_person
    query = (table._id == row.id)
    if key == "person_id":
        query &= (ptable.id == table.person_id)
    elif key == "pe_id":
        query &= (ptable.pe_id == table.pe_id)
    else:
        return default

    person = current.db(query).select(ptable.realm_entity,
                                      limitby = (0, 1),
                                      ).first()
    return person.realm_entity if person else default

# -------------------------------------------------------------------------
def inherit_realm(tablename, row, lookup, key):
    """
        Looks up the realm entity from a context record

        Args:
            tablename: the table name of the current record
            row: the current record (Row)
            lookup: the table name of the context entity
            key: the foreign key in the current record referencing
                 the context record
        Returns:
            pe_id
    """

    s3db = current.s3db
    table = s3db.table(tablename)
    lookup_table = s3db.table(lookup)

    query = (table._id == row.id) & \
            (lookup_table.id == table[key])
    row = current.db(query).select(lookup_table.realm_entity,
                                   limitby = (0, 1),
                                   ).first()

    return row.realm_entity if row else 0

# -------------------------------------------------------------------------
def auth_user_resource(r, tablename):

    db = current.db
    s3db = current.s3db
    auth = current.auth

    table = auth.settings.table_user
    field = table.organisation_id
    field.comment = None

    if not auth.s3_has_roles(("ADMIN", "ORG_GROUP_ADMIN")):
        # Limit OrgAdmins to their managed organisations
        from ..helpers import get_managed_orgs
        organisation_ids = get_managed_orgs()

        otable = s3db.org_organisation
        dbset = db(otable.id.belongs(organisation_ids))
        field.requires = IS_ONE_OF(dbset, "org_organisation.id",
                                   field.represent,
                                   orderby = "name",
                                   )

        # Default if single organisation
        if len(organisation_ids) == 1:
            field.default = organisation_ids[0]
            field.writable = False

# END =========================================================================
