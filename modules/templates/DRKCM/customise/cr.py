"""
    CR module customisations for DRKCM

    License: MIT
"""

from gluon import current

GIS_LEVELS = ("L1", "L2", "L3")

# -------------------------------------------------------------------------
def cr_shelter_onaccept(form):
    """
        Custom onaccept for shelters:
        * Update the Location for all linked Cases
          (in case the Address has been updated)
    """

    db = current.db
    s3db = current.s3db

    try:
        record_id = form.vars.id
    except AttributeError:
        return

    if not record_id:
        # Nothing we can do
        return

    # Reload the record (need site_id which is never in form.vars)
    table = s3db.cr_shelter
    shelter = db(table.id == record_id).select(table.location_id,
                                               table.site_id,
                                               limitby = (0, 1),
                                               ).first()

    # If shelter were None here, then this shouldn't have been called
    # in the first place => let it raise AttributeError
    location_id = shelter.location_id
    site_id = shelter.site_id

    ctable = s3db.dvr_case
    cases = db(ctable.site_id == site_id).select(ctable.person_id)
    if cases:
        person_ids = set(case.person_id for case in cases)
        ptable = s3db.pr_person
        db(ptable.id.belongs(person_ids)).update(
                                        location_id = location_id,
                                        # Indirect update by system rule,
                                        # do not change modified_* fields:
                                        modified_on = ptable.modified_on,
                                        modified_by = ptable.modified_by,
                                        )

# -------------------------------------------------------------------------
def cr_shelter_population():
    """
        Update the Population of all Shelters
        * called onaccept from dvr_case
    """

    db = current.db
    s3db = current.s3db

    # Get the number of open cases per site_id
    ctable = s3db.dvr_case
    dtable = s3db.dvr_case_details
    stable = s3db.dvr_case_status
    join = stable.on(stable.id == ctable.status_id)
    left = dtable.on((dtable.person_id == ctable.person_id) & \
                     (dtable.deleted == False))
    today = current.request.utcnow.date()
    query = (ctable.site_id != None) & \
            (ctable.deleted == False) & \
            (stable.is_closed == False) & \
            ((dtable.on_site_from == None) | (dtable.on_site_from <= today)) & \
            ((dtable.on_site_until == None) | (dtable.on_site_until >= today))

    site_id = ctable.site_id
    count = ctable.id.count()
    rows = db(query).select(site_id,
                            count,
                            groupby = site_id,
                            join = join,
                            left = left,
                            )

    # Update shelter population count
    stable = s3db.cr_shelter
    for row in rows:
        db(stable.site_id == row[site_id]).update(
           population = row[count],
           # Indirect update by system rule,
           # do not change modified_* fields:
           modified_on = stable.modified_on,
           modified_by = stable.modified_by,
           )

# -------------------------------------------------------------------------
def cr_shelter_resource(r, tablename):

    T = current.T
    s3db = current.s3db
    auth = current.auth

    from core import LocationSelector, \
                     CustomForm

    # Field configurations
    table = s3db.cr_shelter

    field = table.organisation_id
    user_org = auth.user.organisation_id if auth.user else None
    if user_org:
        field.default = user_org

    field = table.shelter_type_id
    field.comment = None

    # Hide L2 Government District
    field = table.location_id
    field.widget = LocationSelector(levels = GIS_LEVELS,
                                    show_address = True,
                                    )

    # Custom form
    crud_form = CustomForm("name",
                           "organisation_id",
                           "shelter_type_id",
                           "location_id",
                           "phone",
                           "status",
                           "comments",
                           )


    # Custom list fields
    list_fields = [(T("Name"), "name"),
                   (T("Type"), "shelter_type_id"),
                   "organisation_id",
                   (T("Number of Cases"), "population"),
                   "status",
                   ]

    # Which levels of Hierarchy are we using?
    #levels = current.gis.get_relevant_hierarchy_levels()
    lfields = ["location_id$%s" % level for level in GIS_LEVELS]
    list_fields[-1:-1] = lfields

    s3db.configure("cr_shelter",
                   crud_form = crud_form,
                   list_fields = list_fields,
                   )

    # Add custom onaccept
    s3db.add_custom_callback(tablename,
                             "onaccept",
                             cr_shelter_onaccept,
                             )

# -------------------------------------------------------------------------
def cr_shelter_controller(**attr):

    s3 = current.response.s3

    # Custom prep
    standard_prep = s3.prep
    def custom_prep(r):

        # Call standard prep
        result = standard_prep(r) if callable(standard_prep) else True

        if r.interactive:

            resource = r.resource

            # Customise filter widgets
            filter_widgets = resource.get_config("filter_widgets")
            if filter_widgets:

                from core import TextFilter

                custom_filters = []
                for fw in filter_widgets:
                    if fw.field == "capacity":
                        continue
                    if fw.field == "location_id":
                        fw.opts["levels"] = GIS_LEVELS
                    if not isinstance(fw, TextFilter) and \
                       fw.field != "shelter_type_id":
                        fw.opts["hidden"] = True
                    custom_filters.append(fw)

                resource.configure(filter_widgets = custom_filters)

        return result

    s3.prep = custom_prep

    # Custom rheader
    from ..rheaders import drk_cr_rheader
    attr["rheader"] = drk_cr_rheader

    return attr

# END =========================================================================
