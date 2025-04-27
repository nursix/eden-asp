"""
    SECURITY module customisations for DRK

    License: MIT
"""

from gluon import current

# -------------------------------------------------------------------------
def security_seized_item_resource(r, tablename):
    """
        Custom restrictions in seized items form
    """

    T = current.T

    from gluon import IS_IN_SET
    from core import DateFilter, \
                     OptionsFilter, \
                     S3Represent, \
                     CustomForm, \
                     InlineComponent, \
                     TextFilter, \
                     get_filter_options

    s3db = current.s3db

    table = s3db.security_seized_item

    # Include ID in person field representation, and link to resident's
    # file if permitted; +include ID in autocomplete-comment
    field = table.person_id
    fmt = "%(pe_label)s %(last_name)s, %(first_name)s"
    linkto = current.auth.permission.accessible_url(c = "dvr",
                                                    f = "person",
                                                    t = "pr_person",
                                                    args = ["[id]"],
                                                    extension = "",
                                                    )
    show_link = linkto is not False
    field.represent = s3db.pr_PersonRepresent(fields = ("pe_label",
                                                        "last_name",
                                                        "first_name",
                                                        ),
                                              labels = fmt,
                                              show_link = show_link,
                                              linkto = linkto or None,
                                              )
    field.comment = T("Enter some characters of the ID or name to start the search, then select from the drop-down")

    # Customise options for status field
    field = table.status
    status_opts = s3db.security_seized_item_status_opts
    status_opts["FWD"] = current.T("forwarded to RP")
    field.requires = IS_IN_SET(status_opts, zero=None)
    field.represent = S3Represent(options=status_opts)

    # Can't add item type from item form
    field = table.item_type_id
    field.comment = None

    # Confiscated by not writable (always default)
    field = table.confiscated_by
    field.writable = False

    # Default date for images
    itable = s3db.doc_image
    field = itable.date
    field.default = current.request.utcnow.date()

    if r.interactive:

        # CRUD form
        crud_form = CustomForm("person_id",
                               "item_type_id",
                               "number",
                               "date",
                               "confiscated_by",
                               "status",
                               "depository_id",
                               "status_comment",
                               "returned_on",
                               "returned_by",
                               InlineComponent("image",
                                               label = T("Photos"),
                                               fields = ["date",
                                                         "file",
                                                         "comments",
                                                         ],
                                               explicit_add = T("Add Photo"),
                                               ),
                               "comments",
                               )

        # Custom filter Widgets
        filter_widgets = [TextFilter(["person_id$pe_label",
                                      "person_id$first_name",
                                      "person_id$middle_name",
                                      "person_id$last_name",
                                      "status_comment",
                                      "comments",
                                      ],
                                      label = T("Search"),
                                      comment = T("Search by owner ID, name or comments"),
                                      ),
                          OptionsFilter("item_type_id",
                                        options = lambda: \
                                                  get_filter_options("security_seized_item_type",
                                                                     translate = True,
                                                                     ),
                                        ),
                          OptionsFilter("status",
                                        options = status_opts,
                                        cols = 2,
                                        default = "DEP",
                                        ),
                          OptionsFilter("depository_id",
                                        options = lambda: \
                                                  get_filter_options("security_seized_item_depository"),
                                        ),
                          DateFilter("date",
                                     hidden = True,
                                      ),
                          DateFilter("person_id$dvr_case.closed_on",
                                     hidden = True,
                                     ),
                          ]

        s3db.configure("security_seized_item",
                       crud_form = crud_form,
                       filter_widgets = filter_widgets,
                       )

    # Custom list-fields on component tab
    if r.tablename == "pr_person":
        s3db.configure("security_seized_item",
                       list_fields = ("person_id",
                                      "date",
                                      "number",
                                      "item_type_id",
                                      "confiscated_by",
                                      "status",
                                      "depository_id",
                                      "returned_on",
                                      "comments",
                                      ),
                       )

# END =========================================================================
