"""
    PR module customisations for GIMS

    License: MIT
"""

from gluon import current, IS_NOT_EMPTY

# -------------------------------------------------------------------------
def pr_person_resource(r, tablename):

    s3db = current.s3db

    # Configure components to inherit realm_entity from
    # the person record incl. on realm updates
    s3db.configure("pr_person",
                   realm_components = ("address",
                                       "contact",
                                       "contact_emergency",
                                       "group_membership",
                                       "image",
                                       "person_details",
                                       "person_tag",
                                       ),
                   )

# -------------------------------------------------------------------------
def pr_person_controller(**attr):

    settings = current.deployment_settings

    s3 = current.response.s3

    # Custom prep
    standard_prep = s3.prep
    def prep(r):

        controller = r.controller

        # Call standard prep
        result = standard_prep(r) if callable(standard_prep) else True

        resource = r.resource
        table = resource.table

        from core import StringTemplateParser, CustomForm

        # Determine order of name fields
        NAMES = ("first_name", "middle_name", "last_name")
        keys = StringTemplateParser.keys(settings.get_pr_name_format())
        name_fields = [fn for fn in keys if fn in NAMES]

        controller = r.controller
        if controller in ("default", "hrm") and not r.component:
            # Personal profile (default/person) or staff

            # Last name is required
            table = r.resource.table
            table.last_name.requires = IS_NOT_EMPTY()

            # Custom Form
            crud_fields = name_fields
            r.resource.configure(crud_form = CustomForm(*crud_fields),
                                 deletable = False,
                                 )
        return result
    s3.prep = prep

    #standard_postp = s3.postp
    #def custom_postp(r, output):
    #
    #    # Call standard postp
    #    if callable(standard_postp):
    #        output = standard_postp(r, output)
    #
    #    return output
    #s3.postp = custom_postp

    # Custom rheader
    c = current.request.controller
    if c == "default":
        from ..rheaders import profile_rheader
        attr["rheader"] = profile_rheader

    return attr

# END =========================================================================
