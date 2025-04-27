"""
    Shelter Registry

    Copyright: 2009-2022 (c) Sahana Software Foundation

    Permission is hereby granted, free of charge, to any person
    obtaining a copy of this software and associated documentation
    files (the "Software"), to deal in the Software without
    restriction, including without limitation the rights to use,
    copy, modify, merge, publish, distribute, sublicense, and/or sell
    copies of the Software, and to permit persons to whom the
    Software is furnished to do so, subject to the following
    conditions:

    The above copyright notice and this permission notice shall be
    included in all copies or substantial portions of the Software.

    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
    EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES
    OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
    NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
    HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,
    WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
    FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
    OTHER DEALINGS IN THE SOFTWARE.
"""

__all__ = ("CRShelterModel",
           "CRShelterPopulationModel",
           "CRShelterUnitModel",
           "CRShelterStatusModel",
           "CRShelterServiceModel",
           "CRShelterEnvironmentModel",
           "CRShelterInspectionModel",
           "CRShelterRegistrationModel",
           "CRShelterAllocationModel",
           "cr_rheader",
           "cr_resolve_shelter_flags",
           )

import json

from gluon import *
from gluon.storage import Storage
from ..core import *

from s3dal import Row

# =============================================================================
def shelter_status_opts():

    T = current.T
    return {1: T("Closed"),
            2: T("Open##status"),
            }

# =============================================================================
class CRShelterModel(DataModel):

    names = ("cr_shelter_type",
             "cr_shelter",
             "cr_shelter_id",
             )

    def model(self):

        T = current.T
        db = current.db

        s3 = current.response.s3
        crud_strings = s3.crud_strings

        settings = current.deployment_settings

        messages = current.messages
        NONE = messages["NONE"]

        configure = self.configure
        define_table = self.define_table
        super_link = self.super_link
        set_method = self.set_method

        # ---------------------------------------------------------------------
        # Shelter types
        #
        tablename = "cr_shelter_type"
        define_table(tablename,
                     Field("name", notnull=True,
                           label = T("Name"),
                           requires = [IS_NOT_EMPTY(),
                                       IS_NOT_ONE_OF(db, "%s.name" % tablename,
                                                     skip_imports = True,
                                                     ),
                                       ],
                           ),
                     CommentsField(),
                     )

        # CRUD strings
        crud_strings[tablename] = Storage(
            label_create = T("Create Shelter Type"),
            title_display = T("Shelter Type Details"),
            title_list = T("Shelter Types"),
            title_update = T("Edit Shelter Type"),
            label_list_button = T("List Shelter Types"),
            msg_record_created = T("Shelter Type added"),
            msg_record_modified = T("Shelter Type updated"),
            msg_record_deleted = T("Shelter Type deleted"),
            msg_list_empty = T("No Shelter Types currently registered"),
            )

        configure(tablename,
                  deduplicate = S3Duplicate(),
                  )

        represent = S3Represent(lookup=tablename, translate=True)
        shelter_type_id = FieldTemplate("shelter_type_id", "reference %s" % tablename,
                                        label = T("Shelter Type"),
                                        ondelete = "RESTRICT",
                                        represent = represent,
                                        requires = IS_EMPTY_OR(
                                                        IS_ONE_OF(db, "cr_shelter_type.id",
                                                                  represent,
                                                                  )),
                                        )

        # -------------------------------------------------------------------------
        # Shelters
        #
        status_opts = shelter_status_opts()

        manage_units = settings.get_cr_shelter_units()
        manage_registrations = settings.get_cr_shelter_registration()
        use_blocked_capacity = settings.get_cr_shelter_blocked_capacity()
        population_by_type = settings.get_cr_shelter_population_by_type()
        population_by_age_group = settings.get_cr_shelter_population_by_age_group()

        if population_by_age_group:
            population_total = T("Current Population (Total)")
        else:
            population_total = T("Current Population##shelter")

        population = FieldTemplate("population", "integer",
                                   default = 0,
                                   label = population_total,
                                   represent = IS_INT_AMOUNT.represent,
                                   requires = IS_EMPTY_OR(IS_INT_IN_RANGE(0, None)),
                                   )

        population_writable = not manage_units and \
                              not manage_registrations and \
                              not population_by_type

        tablename = "cr_shelter"
        define_table(tablename,
                     super_link("doc_id", "doc_entity"),
                     super_link("pe_id", "pr_pentity"),
                     super_link("site_id", "org_site"),
                     # @ToDo: code_requires
                     #Field("code", length=10, # Mayon compatibility
                     #      label=T("Code")
                     #      ),
                     Field("name",
                           length = 64, # Mayon compatibility
                           label = T("Shelter Name"),
                           requires = [IS_NOT_EMPTY(),
                                       IS_LENGTH(64),
                                       ],
                           ),
                     self.org_organisation_id(
                        requires = self.org_organisation_requires(updateable=True),
                     ),
                     shelter_type_id(),
                     self.gis_location_id(),
                     self.pr_person_id(
                        label = T("Contact Person"),
                        ),
                     # Alternative for person_id: simple name field
                     Field("contact_name",
                           label = T("Contact Name"),
                           represent = lambda v, row=None: v if v else "-",
                           readable = False,
                           writable = False,
                           ),
                     Field("phone",
                           label = T("Phone"),
                           requires = IS_EMPTY_OR(IS_PHONE_NUMBER_MULTI()),
                           represent = lambda v, row=None: v if v else "-",
                           ),
                     Field("email",
                           label = T("Email"),
                           requires = IS_EMPTY_OR(IS_EMAIL()),
                           represent = lambda v, row=None: v if v else "-",
                           ),
                     Field("website",
                           label = T("Website"),
                           represent = s3_url_represent,
                           requires = IS_EMPTY_OR(
                                        IS_URL(allowed_schemes = ["http", "https", None],
                                               prepend_scheme = "http",
                                               )),
                           readable = False,
                           writable = False,
                           ),
                     population(writable = population_writable and \
                                           not population_by_age_group,
                                comment = DIV(_class="tooltip",
                                              _title="%s|%s" % (population_total,
                                                                T("Current shelter population as number of people"),
                                                                ),
                                              ),
                                ),
                     population("population_adults",
                                label = T("Current Population (Adults)"),
                                readable = population_by_age_group,
                                writable = population_writable and \
                                           population_by_age_group,
                                ),
                     population("population_children",
                                label = T("Current Population (Children)"),
                                readable = population_by_age_group,
                                writable = population_writable and \
                                           population_by_age_group,
                                ),
                     population("capacity",
                                label = T("Capacity"),
                                comment = DIV(_class="tooltip",
                                              _title="%s|%s" % (T("Capacity"),
                                                                T("Capacity of the shelter as a number of people"),
                                                                ),
                                              ),
                                writable = not manage_units,
                                ),
                     population("blocked_capacity",
                                label = T("Non-allocable places"),
                                comment = DIV(_class="tooltip",
                                              _title="%s|%s" % (T("Non-allocable places"),
                                                                T("Number of places that are not currently allocable, e.g. due to technical issues, maintenance or closed groups"),
                                                                ),
                                              ),
                                readable = use_blocked_capacity,
                                writable = use_blocked_capacity and not manage_units,
                                ),
                     population("available_capacity",
                                label = T("Available Capacity"),
                                writable = False,
                                ),
                     Field("status", "integer",
                           label = T("Status"),
                           default = 2, # Open
                           represent = represent_option(status_opts),
                           requires = IS_EMPTY_OR(IS_IN_SET(status_opts)),
                           ),
                     CommentsField(),
                     Field("obsolete", "boolean",
                           default = False,
                           label = T("Obsolete"),
                           represent = lambda opt: messages.OBSOLETE if opt else NONE,
                           readable = False,
                           writable = False,
                           ),
                     )

        # Components
        self.add_components(tablename,
                            cr_shelter_unit = "shelter_id",
                            cr_shelter_population = {"name": "population",
                                                     "joinby": "shelter_id",
                                                     },
                            cr_shelter_status = {"name": "status",
                                                 "joinby": "shelter_id",
                                                 },
                            cr_shelter_allocation = "shelter_id",
                            cr_shelter_registration = "shelter_id",
                            cr_shelter_service = {"link": "cr_shelter_service_shelter",
                                                  "joinby": "shelter_id",
                                                  "key": "service_id",
                                                  },
                            cr_environment = {"link": "cr_shelter_environment",
                                              "joinby": "shelter_id",
                                              "key": "environment_id",
                                              },
                            event_event_shelter = "shelter_id",
                            )

        # TODO CRUD form
        # - alternative with inline-populations / inline-services

        # Fields for pivot table reports
        report_fields = ["name",
                         "shelter_type_id",
                         #"organisation_id",
                         "status",
                         "population",
                         ]

        # Text filter fields
        text_fields = ["name",
                       #"code",
                       "comments",
                       "organisation_id$name",
                       "organisation_id$acronym",
                       "location_id$name",
                       ]

        # List fields
        list_fields = ["name",
                       "status",
                       "shelter_type_id",
                       #"shelter_service_shelter.service_id",
                       ]
        if manage_registrations:
            list_fields.append("capacity")
            list_fields.append("population")
        else:
            # Manual
            list_fields.append("population")
        list_fields.append("location_id$addr_street")
        #list_fields.append("person_id")

        # Which levels of Hierarchy are we using?
        levels = current.gis.get_relevant_hierarchy_levels()
        for level in levels:
            lfield = "location_id$%s" % level
            report_fields.append(lfield)
            text_fields.append(lfield)
            list_fields.append(lfield)

        # Filter widgets
        cr_shelter_status_filter_opts = dict(status_opts)
        cr_shelter_status_filter_opts[None] = T("Unspecified")

        if settings.get_org_branches():
            org_filter = HierarchyFilter("organisation_id",
                                         leafonly = False,
                                         )
        else:
            org_filter = OptionsFilter("organisation_id",
                                       search = True,
                                       header = "",
                                       #hidden = True,
                                       )
        filter_widgets = [
                TextFilter(text_fields,
                           label = T("Search"),
                           #_class = "filter-search",
                           ),
                OptionsFilter("shelter_type_id",
                              label = T("Type"),
                              # Doesn't translate
                              #represent = "%(name)s",
                              ),
                org_filter,
                LocationFilter("location_id",
                               label = T("Location"),
                               levels = levels,
                               ),
                OptionsFilter("status",
                              label = T("Status"),
                              options = cr_shelter_status_filter_opts,
                              none = True,
                              ),
                ]

        if manage_registrations:
            filter_widgets.append(RangeFilter("available_capacity",
                                              label = T("Available Capacity"),
                                              ))
        filter_widgets.append(RangeFilter("capacity",
                                          label = T("Total Capacity"),
                                          ))
        # Table configuration
        configure(tablename,
                  deduplicate = S3Duplicate(),
                  filter_widgets = filter_widgets,
                  list_fields = list_fields,
                  onvalidation = self.shelter_onvalidation,
                  onaccept = self.shelter_onaccept,
                  orderby = "%s.name" % tablename,
                  report_options = Storage(
                        rows = report_fields,
                        cols = report_fields,
                        fact = report_fields,
                        defaults = Storage(rows = lfield, # Lowest-level of hierarchy
                                           cols = "status",
                                           fact = "count(name)",
                                           totals = True,
                                           )
                        ),
                  super_entity = ("org_site", "doc_entity", "pr_pentity"),
                  update_realm = True,
                  )

        # Custom method to assign HRs
        set_method("cr_shelter",
                   method = "assign",
                   action = self.hrm_AssignMethod(component="human_resource_site"),
                   )

        # Check-in method
        # TODO deprecate
        set_method("cr_shelter",
                   method="check-in",
                   action = self.org_SiteCheckInMethod,
                   )

        # Presence Registration
        set_method("cr_shelter",
                   method = "presence",
                   action = PresenceRegistration,
                   )

        # Shelter Inspection method
        set_method("cr_shelter",
                   method = "inspection",
                   action = CRShelterInspection,
                   )

        # CRUD strings
        ADD_SHELTER = T("Create Shelter")
        SHELTER_LABEL = T("Shelter")
        SHELTER_HELP = T("The Shelter this Request is from")
        crud_strings[tablename] = Storage(
            label_create = ADD_SHELTER,
            title_display = T("Shelter Details"),
            title_list = T("Shelters"),
            title_update = T("Edit Shelter"),
            label_list_button = T("List Shelters"),
            msg_record_created = T("Shelter added"),
            msg_record_modified = T("Shelter updated"),
            msg_record_deleted = T("Shelter deleted"),
            msg_list_empty = T("No Shelters currently registered"),
            )

        # Foreign Key Template
        represent = S3Represent(lookup=tablename)
        shelter_id = FieldTemplate("shelter_id", "reference %s" % tablename,
                                   label = SHELTER_LABEL,
                                   ondelete = "RESTRICT",
                                   represent = represent,
                                   requires = IS_EMPTY_OR(
                                                    IS_ONE_OF(db, "cr_shelter.id",
                                                              represent,
                                                              sort = True,
                                                              )),
                                   comment = PopupLink(c = "cr",
                                                       f = "shelter",
                                                       label = ADD_SHELTER,
                                                       title = SHELTER_LABEL,
                                                       tooltip = "%s (%s)." % (SHELTER_HELP,
                                                                               T("optional"),
                                                                               ),
                                                       ),
                                   widget = S3AutocompleteWidget("cr", "shelter")
                                   )

        # ---------------------------------------------------------------------
        # Pass variables back to global scope (response.s3.*)
        return {"ADD_SHELTER" : ADD_SHELTER,
                "SHELTER_LABEL" : SHELTER_LABEL,
                "cr_shelter_id" : shelter_id,
                }

    # -------------------------------------------------------------------------
    def defaults(self):
        """
            Returns safe defaults in case the model has been deactivated.
        """

        return {"cr_shelter_id": FieldTemplate.dummy("shelter_id"),
                }

    # -------------------------------------------------------------------------
    @staticmethod
    def shelter_onvalidation(form):
        """
            Shelter form validation
                - prevent status=closed while there are still people registered
                  as checked-in (if managing registrations)
        """

        T = current.T

        db = current.db
        s3db = current.s3db

        if current.deployment_settings.get_cr_shelter_registration():

            record = form.record if hasattr(form, "record") else None
            record_id = get_form_record_id(form)

            form_vars = form.vars

            status = form_vars.get("status")
            if record_id and str(status) == "1": # closed

                # Determine previous status
                if not record or "status" not in record:
                    table = s3db.cr_shelter
                    record = db(table.id == record_id).select(table.status,
                                                              limitby = (0, 1),
                                                              ).first()
                old_status = record.status if record else None

                # If changing to "closed", verify that there are no more people checked-in
                if record and status != old_status:
                    rtable = s3db.cr_shelter_registration
                    query = (rtable.shelter_id == record_id) & \
                            (rtable.registration_status == 2) & \
                            (rtable.deleted == False)
                    row = db(query).select(rtable.id, limitby=(0, 1)).first()
                    if row:
                        form.errors.status = T("Shelter is currently occupied and cannot be closed")

    # -------------------------------------------------------------------------
    @staticmethod
    def shelter_onaccept(form):
        """
            Onaccept of shelter
                - update PE hierarchy
                - update available capacity and create status entry
                - record org_site_event
        """

        s3db = current.s3db

        shelter_id = get_form_record_id(form)

        # Update PE hierarchy
        s3db.org_update_affiliations("cr_shelter", form.vars)

        # Update population, available capacity and create status entry
        Shelter(shelter_id).update_population()

        if not current.response.s3.bulk:

            # Track site events
            stable = s3db.cr_shelter
            shelter = current.db(stable.id == shelter_id).select(stable.site_id,
                                                                 stable.status,
                                                                 stable.obsolete,
                                                                 limitby = (0, 1)
                                                                 ).first()
            record = form.record
            if record:
                # Update form
                obsolete = shelter.obsolete
                if obsolete != record.obsolete:
                    s3db.org_site_event.insert(site_id = shelter.site_id,
                                               event = 4, # Obsolete Change
                                               comment = obsolete,
                                               )
                status = shelter.status
                if status != record.status:
                    s3db.org_site_event.insert(site_id = shelter.site_id,
                                               event = 1, # Status Change
                                               status = status,
                                               )
            else:
                # Create form
                s3db.org_site_event.insert(site_id = shelter.site_id,
                                           event = 1, # Status Change
                                           status = shelter.status,
                                           )

# =============================================================================
class CRShelterPopulationModel(DataModel):
    """ Shelter population subgroups """

    names = ("cr_population_type",
             "cr_shelter_population",
             )

    def model(self):

        T = current.T
        db = current.db
        settings = current.deployment_settings

        s3 = current.response.s3
        crud_strings = s3.crud_strings

        define_table = self.define_table

        # -------------------------------------------------------------------------
        # Resident types
        #
        tablename = "cr_population_type"
        define_table(tablename,
                     Field("code", length=16, notnull=True, unique=True,
                           label = T("Code"),
                           requires = [IS_NOT_EMPTY(),
                                       IS_LENGTH(16, minsize=1),
                                       IS_NOT_ONE_OF(db, "%s.code" % tablename),
                                       ],
                           comment = DIV(_class = "tooltip",
                                         _title = "%s|%s" % (T("Code"),
                                                             T("A unique code for this type"),
                                                             ),
                                         ),
                           ),
                     Field("name",
                           label = T("Name"),
                           requires = IS_NOT_EMPTY(),
                     ),
                     Field("obsolete", "boolean",
                           default = False,
                           label = T("Obsolete"),
                           represent = s3_yes_no_represent,
                           ),
                     CommentsField(),
                     )

        # CRUD strings
        crud_strings[tablename] = Storage(
            label_create = T("Add Population Type"),
            title_display = T("Population Type Details"),
            title_list = T("Population Types"),
            title_update = T("Edit Population Type"),
            label_list_button = T("List Population Types"),
            label_delete_button = T("Delete Population Type"),
            msg_record_created = T("Population Type added"),
            msg_record_modified = T("Population Type updated"),
            msg_record_deleted = T("Population Type deleted"),
            msg_list_empty = T("No Population Types currently defined"),
            )

        represent = S3Represent(lookup=tablename)
        type_id = FieldTemplate("type_id", "reference %s" % tablename,
                                label = T("Population Type"),
                                represent = represent,
                                requires = IS_EMPTY_OR(
                                                IS_ONE_OF(db, "%s.id" % tablename,
                                                          represent,
                                                          filterby = "obsolete",
                                                          filter_opts = (False,),
                                                          )),
                                ondelete = "RESTRICT",
                                )

        # -------------------------------------------------------------------------
        # Shelter population per type
        #
        population_by_age_group = settings.get_cr_shelter_population_by_age_group()

        population = FieldTemplate("population", "integer",
                                   label = T("Population##shelter"),
                                   represent = IS_INT_AMOUNT.represent,
                                   requires = IS_EMPTY_OR(IS_INT_IN_RANGE(0, None)),
                                   readable = True,
                                   writable = False,
                                   )

        tablename = "cr_shelter_population"
        define_table(tablename,
                     self.cr_shelter_id(empty = False,
                                        ondelete = "CASCADE",
                                        ),
                     type_id(empty=False),
                     population(writable = not population_by_age_group,
                                ),
                     population("population_adults",
                                label = T("Population (Adults)"),
                                writable = population_by_age_group,
                                ),
                     population("population_children",
                                label = T("Population (Children)"),
                                writable = population_by_age_group,
                                ),
                     )

        # Table configuration
        self.configure(tablename,
                       onaccept = self.shelter_population_onaccept,
                       ondelete = self.shelter_population_ondelete,
                       )

        # ---------------------------------------------------------------------
        # Pass variables back to global scope (response.s3.*)
        #
        return None

    # -------------------------------------------------------------------------
    @staticmethod
    def shelter_population_onaccept(form):
        """
            Onaccept of shelter population:
                - updates the total population (if separate per age group)
                - updates shelter population totals
        """

        record_id = get_form_record_id(form)
        if not record_id:
            return

        by_age_group = current.deployment_settings.get_cr_shelter_population_by_age_group()

        table = current.s3db.cr_shelter_population
        query = (table.id == record_id) & \
                (table.deleted == False)
        fields = [table.id, table.shelter_id]
        if by_age_group:
            fields += [table.population_adults, table.population_children]
        row = current.db(query).select(*fields, limitby = (0, 1)).first()
        if not row:
            return

        if by_age_group:
            a = row.population_adults
            c = row.population_children
            population = (a if a else 0) + (c if c else 0)
            row.update_record(population = population)

        shelter_id = row.shelter_id
        if shelter_id:
            Shelter(shelter_id).update_population()

    # -------------------------------------------------------------------------
    @staticmethod
    def shelter_population_ondelete(row):
        """
            Ondelete of shelter population:
                - updates shelter population totals
        """

        shelter_id = row.shelter_id
        if shelter_id:
            Shelter(shelter_id).update_population()

# =============================================================================
class CRShelterUnitModel(DataModel):

    names = ("cr_shelter_unit",
             "cr_shelter_unit_id",
             )

    def model(self):

        T = current.T
        db = current.db
        settings = current.deployment_settings
        crud_strings = current.response.s3.crud_strings

        define_table = self.define_table

        population = FieldTemplate("population", "integer",
                                   default = 0,
                                   label = T("Current Population"),
                                   represent = IS_INT_AMOUNT.represent,
                                   requires = IS_EMPTY_OR(IS_INT_IN_RANGE(0, None)),
                                   )
        manage_registrations = settings.get_cr_shelter_registration()
        use_blocked_capacity = settings.get_cr_shelter_blocked_capacity()
        population_by_age_group = settings.get_cr_shelter_population_by_age_group()

        # -------------------------------------------------------------------------
        # Housing units
        #
        cr_housing_unit_opts = {1: T("Available"),
                                2: T("Not allocable"),
                                3: T("Closed"),
                                }
        status_represent = S3PriorityRepresent(cr_housing_unit_opts,
                                               {1: "lightblue",
                                                2: "grey",
                                                3: "black",
                                                }).represent

        tablename = "cr_shelter_unit"
        define_table(tablename,
                     Field("name", notnull=True, length = 64,
                           label = T("Housing Unit Name"),
                           requires = [IS_NOT_EMPTY(),
                                       IS_LENGTH(64),
                                       ],
                           ),
                     self.cr_shelter_id(ondelete = "CASCADE"),
                     self.gis_location_id(
                         widget = LocationSelector(#catalog_layers=True,
                                                   show_postcode = False,
                                                   points = False,
                                                   polygons = True,
                                                   ),
                         ),
                     Field("status", "integer",
                           default = 1,
                           label = T("Status"),
                           represent = status_represent,
                           requires = IS_EMPTY_OR(IS_IN_SET(cr_housing_unit_opts))
                           ),
                     Field("transitory", "boolean",
                           default = False,
                           label = T("Transitory Accommodation"),
                           represent = s3_yes_no_represent,
                           comment = DIV(_class="tooltip",
                                         _title="%s|%s" % (T("Transitory Accommodation"),
                                                           T("This unit is for transitory accommodation upon arrival, or buffer in case of capacity excess"),
                                                           ),
                                         ),
                           # Enable in template as required:
                           readable = False,
                           writable = False,
                           ),
                     population(writable = not manage_registrations and \
                                           not population_by_age_group,
                                ),
                     population("population_adults",
                                label = T("Current Population (Adults)"),
                                readable = population_by_age_group,
                                writable = not manage_registrations and \
                                           population_by_age_group,
                                ),
                     population("population_children",
                                label = T("Current Population (Children)"),
                                readable = population_by_age_group,
                                writable = not manage_registrations and \
                                           population_by_age_group,
                                ),
                     population("capacity",
                                label = T("Capacity"),
                                ),
                     population("blocked_capacity",
                                label = T("Non-allocable places"),
                                comment = DIV(_class="tooltip",
                                              _title="%s|%s" % (T("Non-allocable places"),
                                                                T("Number of places that are not currently allocable, e.g. due to technical issues, maintenance or closed groups"),
                                                                ),
                                              ),
                                readable = use_blocked_capacity,
                                writable = use_blocked_capacity,
                                ),
                     population("available_capacity",
                                label = T("Available Capacity"),
                                writable = False,
                                ),
                     Field.Method("cstatus", self.shelter_unit_status),
                     CommentsField(),
                     )

        # Components
        self.add_components(tablename,
                            cr_shelter_inspection = "shelter_unit_id",
                            )

        # List fields
        list_fields = ["id",
                       "name",
                       "available_capacity",
                       "capacity",
                       "population",
                       ]

        self.configure(tablename,
                       deduplicate = S3Duplicate(primary = ("name",),
                                                 secondary = ("shelter_id",),
                                                 ),
                       list_fields = list_fields,
                       # Extra fields for shelter_unit_status:
                       extra_fields = ["status",
                                       "capacity",
                                       "available_capacity",
                                       ],
                       onaccept = self.shelter_unit_onaccept,
                       ondelete = self.shelter_unit_ondelete,
                       orderby = "%s.name" % tablename,
                       )

        # CRUD strings
        crud_strings[tablename] = Storage(
            label_create = T("Create Housing Unit"),
            title_display = T("Housing Unit Details"),
            title_list = T("Housing Units"),
            title_update = T("Edit Housing Unit"),
            label_list_button = T("List Housing Units"),
            msg_record_created = T("Housing Unit added"),
            msg_record_modified = T("Housing Unit updated"),
            msg_record_deleted = T("Housing Unit deleted"),
            msg_list_empty = T("No Housing Units currently registered"),
            )

        # Foreign Key Template
        represent = S3Represent(lookup="cr_shelter_unit")
        shelter_unit_id = FieldTemplate("shelter_unit_id", "reference cr_shelter_unit",
                                        label = T("Housing Unit"),
                                        ondelete = "RESTRICT",
                                        represent = represent,
                                        requires = IS_EMPTY_OR(
                                                        IS_ONE_OF(db, "cr_shelter_unit.id",
                                                                  represent,
                                                                  orderby="shelter_id",
                                                                  #sort=True,
                                                                  )),
                                        #widget = S3AutocompleteWidget("cr", "shelter_unit")
                                        )

        # ---------------------------------------------------------------------
        # Pass variables back to global scope (response.s3.*)
        #
        return {"cr_shelter_unit_id" : shelter_unit_id,
                }

    # -------------------------------------------------------------------------
    def defaults(self):
        """
            Returns safe defaults in case the model has been deactivated.
        """

        dummy = FieldTemplate.dummy

        return {"cr_shelter_unit_id": dummy("shelter_unit_id"),
                }

    # -------------------------------------------------------------------------
    @staticmethod
    def shelter_unit_onaccept(form):
        """
            Onaccept of shelter unit:
                - updates population and available capacity of unit
                - updates shelter population
                - updates shelter capacity
        """

        db = current.db
        s3db = current.s3db

        manage_registrations = current.deployment_settings.get_cr_shelter_registration()

        record_id = get_form_record_id(form)
        if not record_id:
            return

        table = s3db.cr_shelter_unit
        query = (table.id == record_id) & \
                (table.deleted == False)
        unit = db(query).select(table.id,
                                table.status,
                                table.shelter_id,
                                table.capacity,
                                table.blocked_capacity,
                                limitby = (0, 1),
                                ).first()

        # Remove all checked-in registrations when unit is closed
        if unit.status == 3 and manage_registrations:
            rtable = s3db.cr_shelter_registration
            query = (rtable.shelter_unit_id == unit.id) & \
                    (rtable.registration_status != 3) & \
                    (rtable.deleted == False)
            db(query).update(shelter_unit_id=None)

        # Fix capacity<=>blocked_capacity
        capacity = unit.capacity
        blocked_capacity = unit.blocked_capacity
        if capacity is None:
            if blocked_capacity is not None and blocked_capacity > 0:
                unit.update_record(capacity=blocked_capacity)
        else:
            if blocked_capacity is not None and blocked_capacity > capacity:
                unit.update_record(blocked_capacity=capacity)

        HousingUnit(record_id).update_population()

        shelter_id = unit.shelter_id if unit else None
        if shelter_id:
            shelter = Shelter(shelter_id)
            if not manage_registrations:
                shelter.update_population(update_status=False)
            shelter.update_capacity()

    # -------------------------------------------------------------------------
    @staticmethod
    def shelter_unit_ondelete(row):
        """
            Ondelete of shelter unit:
                - updates shelter population
                - updates shelter capacity
        """

        shelter_id = row.shelter_id
        if shelter_id:
            shelter = Shelter(shelter_id)
            if not current.deployment_settings.get_cr_shelter_registration():
                shelter.update_population(update_status=False)
            shelter.update_capacity()

    # -------------------------------------------------------------------------
    @classmethod
    def shelter_unit_status(cls, row):
        """
            Field method to indicate available capacity as status
                - used to colour features on the map
                - values:
                    0: Full
                    1: Partial
                    2: Empty
                    3: Not Available, or status unknown
        """

        if hasattr(row, "cr_shelter_unit"):
            row = row.cr_shelter_unit

        try:
            status = row.status
            if status == 2:
                return 3 # Not Available

            total = row.capacity
            if not total:
                return 0 # No capacity ever, so Full

            actual = row.available_capacity
            if actual:
                if actual == total:
                    code = 2 # Empty
                else:
                    code = 1 if actual > 0 else 0 # Partial or Full
            else:
                code = 3 # Unknown
            return code

        except AttributeError:
            # Must reload the record :/
            try:
                record_id = row.id
            except AttributeError:
                return 3 # Unknown
            table = current.s3db.cr_shelter_unit
            query = (table.id == record_id)
            row = db(query).select(table.id,
                                   table.status,
                                   table.capacity,
                                   table.available_capacity,
                                   limitby = (0, 1),
                                   ).first()
            return cls.shelter_unit_status(row)

# =============================================================================
class CRShelterStatusModel(DataModel):
    """ Shelter Status Updates """

    names = ("cr_shelter_status",
             "cr_shelter_status_resident_type",
             )

    def model(self):

        T = current.T

        settings = current.deployment_settings

        s3 = current.response.s3

        crud_strings = s3.crud_strings
        define_table = self.define_table
        configure = self.configure

        status_opts = shelter_status_opts()

        population = FieldTemplate("population", "integer",
                                   label = T("Population##shelter"),
                                   represent = IS_INT_AMOUNT.represent,
                                   requires = IS_EMPTY_OR(IS_INT_IN_RANGE(0, None)),
                                   readable = True,
                                   writable = False,
                                   )
        population_by_age_group = settings.get_cr_shelter_population_by_age_group()
        use_blocked_capacity = settings.get_cr_shelter_blocked_capacity()

        # -------------------------------------------------------------------------
        # Shelter status updates
        # - a historical record of shelter status & populations
        #
        tablename = "cr_shelter_status"
        define_table(tablename,
                     self.cr_shelter_id(ondelete = "CASCADE",
                                        writable = False,
                                        ),
                     DateField(default = "now",
                               future = 0,
                               writable = False
                               ),
                     Field("status", "integer",
                           label = T("Status"),
                           default = 2, # Open
                           represent = represent_option(status_opts),
                           requires = IS_IN_SET(status_opts, zero=None),
                           writable = False,
                           ),
                     population(),
                     population("population_adults",
                                label = T("Population (Adults)"),
                                readable = population_by_age_group,
                                ),
                     population("population_children",
                                label = T("Population (Children)"),
                                readable = population_by_age_group,
                                ),
                     population("capacity",
                                label = T("Capacity"),
                                ),
                     population("blocked_capacity",
                                label = T("Non-allocable places"),
                                readable = use_blocked_capacity,
                                ),
                     CommentsField(),
                     )

        configure(tablename,
                  insertable = False,
                  deletable = False,
                  orderby = "cr_shelter_status.date desc",
                  )

        # CRUD strings
        crud_strings[tablename] = Storage(
            label_create = T("Create Shelter Status"),
            title_display = T("Shelter Status Details"),
            title_list = T("Shelter Statuses"),
            title_update = T("Edit Shelter Status"),
            label_list_button = T("List Shelter Statuses"),
            msg_record_created = T("Shelter Status added"),
            msg_record_modified = T("Shelter Status updated"),
            msg_record_deleted = T("Shelter Status deleted"),
            msg_list_empty = T("No Shelter Statuses currently registered"),
            )

        # ---------------------------------------------------------------------
        # Pass variables back to global scope (response.s3.*)
        #
        return None

# =============================================================================
class CRShelterServiceModel(DataModel):
    """ Model for Shelter Services """

    names = ("cr_shelter_service",
             "cr_shelter_service_shelter",
             )

    def model(self):

        T = current.T

        define_table = self.define_table

        # -------------------------------------------------------------------------
        # Shelter services
        # e.g. medical, housing, food, ...
        tablename = "cr_shelter_service"
        define_table(tablename,
                     Field("name", notnull=True,
                           label = T("Name"),
                           requires = IS_NOT_EMPTY(),
                           ),
                     CommentsField(),
                     )

        # CRUD strings
        ADD_SHELTER_SERVICE = T("Create Shelter Service")
        SHELTER_SERVICE_LABEL = T("Shelter Service")
        current.response.s3.crud_strings[tablename] = Storage(
            label_create = ADD_SHELTER_SERVICE,
            title_display = T("Shelter Service Details"),
            title_list = T("Shelter Services"),
            title_update = T("Edit Shelter Service"),
            label_list_button = T("List Shelter Services"),
            msg_record_created = T("Shelter Service added"),
            msg_record_modified = T("Shelter Service updated"),
            msg_record_deleted = T("Shelter Service deleted"),
            msg_list_empty = T("No Shelter Services currently registered"),
            )

        service_represent = S3Represent(lookup=tablename, translate=True)

        service_id = FieldTemplate("service_id", "reference %s" % tablename,
                                   label = SHELTER_SERVICE_LABEL,
                                   ondelete = "RESTRICT",
                                   represent = service_represent,
                                   requires = IS_EMPTY_OR(
                                                    IS_ONE_OF(current.db,
                                                              "cr_shelter_service.id",
                                                              service_represent,
                                                              )),
                                   sortby = "name",
                                   comment = PopupLink(c = "cr",
                                                       f = "shelter_service",
                                                       label = ADD_SHELTER_SERVICE,
                                                       ),
                                   )
        self.configure(tablename,
                       deduplicate = S3Duplicate(),
                       )

        # ---------------------------------------------------------------------
        # Shelter Service <> Shelter link table
        #
        tablename = "cr_shelter_service_shelter"
        define_table(tablename,
                     self.cr_shelter_id(empty = False,
                                        ondelete = "CASCADE",
                                        ),
                     service_id(empty = False,
                                ondelete = "CASCADE",
                                ),
                     )

        # ---------------------------------------------------------------------
        # Pass names back to global scope (s3.*)
        #
        return None

# =============================================================================
class CRShelterEnvironmentModel(DataModel):
    """ Environmental conditions of a shelter """

    names = ("cr_environment",
             "cr_shelter_environment",
             )

    def model(self):

        T = current.T
        db = current.db

        define_table = self.define_table

        # -------------------------------------------------------------------------
        # Environmental conditions (e.g. Lake, Mountain, ground type)
        #
        tablename = "cr_environment"
        define_table(tablename,
                     Field("name", notnull=True,
                           label = T("Name"),
                           requires = IS_NOT_EMPTY(),
                           ),
                     CommentsField(),
                     )

        environment_represent = S3Represent(lookup=tablename, translate=True)

        # -------------------------------------------------------------------------
        # Link shelter <=> environment
        #
        tablename = "cr_shelter_environment"
        define_table(tablename,
                     self.cr_shelter_id(
                        empty = False,
                        ondelete = "CASCADE",
                        ),
                     Field("environment_id", "reference cr_environment",
                           represent = environment_represent,
                           requires = IS_ONE_OF(db, "cr_environment.id",
                                                environment_represent,
                                                ),
                           ),
                     )

        # -------------------------------------------------------------------------
        return None

# =============================================================================
class CRShelterInspectionModel(DataModel):
    """ Model for Shelter / Housing Unit Flags """

    names = ("cr_shelter_flag",
             "cr_shelter_flag_id",
             "cr_shelter_inspection",
             "cr_shelter_inspection_flag",
             "cr_shelter_inspection_task",
             )

    def model(self):

        T = current.T

        db = current.db
        s3 = current.response.s3
        settings = current.deployment_settings

        crud_strings = s3.crud_strings

        define_table = self.define_table
        configure = self.configure

        shelter_inspection_tasks = settings.get_cr_shelter_inspection_tasks()
        task_priority_opts = settings.get_project_task_priority_opts()

        assignee_represent = self.pr_PersonEntityRepresent(show_label = False,
                                                           #show_type = False,
                                                           )

        # ---------------------------------------------------------------------
        # Flags - flags that can be set for a shelter / housing unit
        #
        tablename = "cr_shelter_flag"
        define_table(tablename,
                     Field("name",
                           requires = IS_NOT_EMPTY(),
                           ),
                     Field("create_task", "boolean",
                           label = T("Create Task"),
                           default = False,
                           represent = s3_yes_no_represent,
                           readable = shelter_inspection_tasks,
                           writable = shelter_inspection_tasks,
                           ),
                     Field("task_description", length=100,
                           label = T("Task Description"),
                           requires = IS_EMPTY_OR(IS_LENGTH(100)),
                           represent = lambda v: v if v else "",
                           readable = shelter_inspection_tasks,
                           writable = shelter_inspection_tasks,
                           ),
                     Field("task_priority", "integer",
                           default = 3,
                           label = T("Priority"),
                           represent = represent_option(task_priority_opts),
                           requires = IS_IN_SET(task_priority_opts,
                                                zero = None,
                                                ),
                           ),
                     # Task Assignee
                     Field("task_assign_to", "reference pr_pentity",
                           label = T("Assign to"),
                           represent = assignee_represent,
                           requires = IS_EMPTY_OR(
                                           IS_ONE_OF(db, "pr_pentity.pe_id",
                                                     assignee_represent,
                                                     filterby = "instance_type",
                                                     filter_opts = ("pr_person",
                                                                    "pr_group",
                                                                    #"org_organisation",
                                                                    ),
                                                     ),
                                           ),
                           ),
                     CommentsField(),
                     )

        # Table settings
        configure(tablename,
                  deduplicate = S3Duplicate(),
                  onvalidation = self.shelter_flag_onvalidation,
                  )

        # CRUD Strings
        crud_strings[tablename] = Storage(
            label_create = T("Create Shelter Flag"),
            title_display = T("Shelter Flag Details"),
            title_list = T("Shelter Flags"),
            title_update = T("Edit Shelter Flag"),
            label_list_button = T("List Shelter Flags"),
            label_delete_button = T("Delete Shelter Flag"),
            msg_record_created = T("Shelter Flag created"),
            msg_record_modified = T("Shelter Flag updated"),
            msg_record_deleted = T("Shelter Flag deleted"),
            msg_list_empty = T("No Shelter Flags currently defined"),
        )

        # Foreign Key Template
        represent = S3Represent(lookup=tablename, translate=True)
        flag_id = FieldTemplate("flag_id", "reference %s" % tablename,
                                label = T("Shelter Flag"),
                                represent = represent,
                                requires = IS_ONE_OF(db, "%s.id" % tablename,
                                                     represent,
                                                     ),
                                sortby = "name",
                                )

        # ---------------------------------------------------------------------
        # Shelter Inspection
        #
        tablename = "cr_shelter_inspection"
        define_table(tablename,
                     #self.cr_shelter_id(ondelete = "CASCADE",
                     #                   readable = False,
                     #                   writable = False,
                     #                   ),
                     self.cr_shelter_unit_id(ondelete = "CASCADE"),
                     DateField(default = "now",
                               ),
                     CommentsField(),
                     )

        # CRUD Form
        crud_form = CustomForm("shelter_unit_id",
                               "date",
                               InlineLink("shelter_flag",
                                          field = "flag_id",
                                          multiple = True,
                                          cols = 3,
                                          ),
                               "comments",
                               )

        # List fields
        list_fields = ["shelter_unit_id",
                       "date",
                       (T("Flags"), "shelter_flag__link.flag_id"),
                       (T("Registered by"), "modified_by"),
                       "comments",
                       ]

        # Table configuration
        configure(tablename,
                  crud_form = crud_form,
                  list_fields = list_fields,
                  orderby = "%s.date desc" % tablename,
                  )

        # CRUD Strings
        crud_strings[tablename] = Storage(
            label_create = T("Create Shelter Inspection"),
            title_display = T("Shelter Inspection Details"),
            title_list = T("Shelter Inspections"),
            title_update = T("Edit Shelter Inspection"),
            label_list_button = T("List Shelter Inspections"),
            label_delete_button = T("Delete Shelter Inspection"),
            msg_record_created = T("Shelter Inspection created"),
            msg_record_modified = T("Shelter Inspection updated"),
            msg_record_deleted = T("Shelter Inspection deleted"),
            msg_list_empty = T("No Shelter Inspections currently registered"),
        )

        # Components
        self.add_components(tablename,
                            cr_shelter_flag = {"link": "cr_shelter_inspection_flag",
                                               "joinby": "inspection_id",
                                               "key": "flag_id",
                                               },
                            )

        # ---------------------------------------------------------------------
        # Shelter Inspection <=> Flag link table
        #
        represent = ShelterInspectionRepresent(show_link=True)
        tablename = "cr_shelter_inspection_flag"
        define_table(tablename,
                     Field("inspection_id", "reference cr_shelter_inspection",
                           label = T("Shelter Inspection"),
                           ondelete = "CASCADE",
                           represent = represent,
                           requires = IS_ONE_OF(db, "cr_shelter_inspection.id",
                                                represent,
                                                ),
                           ),
                     flag_id(label = T("Defect found")),
                     Field("resolved", "boolean",
                           label = T("Resolved"),
                           default = False,
                           represent = s3_yes_no_represent,
                           ),
                     )

        # List fields
        list_fields = ["id",
                       "inspection_id$shelter_unit_id$name",
                       "inspection_id$date",
                       (T("Registered by"), "inspection_id$modified_by"),
                       (T("Defect"), "flag_id"),
                       "resolved",
                       ]

        # Filter widgets
        filter_widgets = [OptionsFilter("inspection_id$shelter_unit_id",
                                        search = 10,
                                        header = True,
                                        ),
                          OptionsFilter("flag_id",
                                        label = T("Defect"),
                                        options = get_filter_options("cr_shelter_flag"),
                                        ),
                          OptionsFilter("resolved",
                                        label = T("Resolved"),
                                        options = {False: T("No"),
                                                   True: T("Yes"),
                                                   },
                                        default = False,
                                        cols = 2,
                                        ),
                          ]

        # Table Configuration
        configure(tablename,
                  filter_widgets = filter_widgets,
                  list_fields = list_fields,
                  # Can not be directly inserted nor edited
                  insertable = False,
                  editable = False,
                  create_onaccept = self.shelter_inspection_flag_onaccept,
                  )

        # CRUD Strings
        crud_strings[tablename] = Storage(
            label_create = T("Register Defect"),
            title_display = T("Defect Details"),
            title_list = T("Defects"),
            title_update = T("Edit Defect"),
            label_list_button = T("List Defects"),
            label_delete_button = T("Delete Defect"),
            msg_record_created = T("Defect created"),
            msg_record_modified = T("Defect updated"),
            msg_record_deleted = T("Defect deleted"),
            msg_list_empty = T("No Defects currently registered"),
        )

        # ---------------------------------------------------------------------
        # Inspection Flag <=> Project Task link table
        #
        tablename = "cr_shelter_inspection_task"
        define_table(tablename,
                     Field("inspection_flag_id", "reference cr_shelter_inspection_flag",
                           label = T("Defects"),
                           ondelete = "CASCADE",
                           represent = ShelterInspectionFlagRepresent(show_link=True),
                           requires = IS_ONE_OF(db, "cr_shelter_inspection_flag.id"),
                           ),
                     self.project_task_id(ondelete = "RESTRICT",
                                          ),
                     )

        # Table Configuration
        configure(tablename,
                  list_fields = ["id",
                                 "task_id",
                                 "inspection_flag_id",
                                 "inspection_flag_id$resolved",
                                 ],
                  ondelete_cascade = self.shelter_inspection_task_ondelete_cascade,
                  )

        # ---------------------------------------------------------------------
        # Pass names back to global scope (s3.*)
        #
        return {"cr_shelter_flag_id": flag_id,
                }

    # -------------------------------------------------------------------------
    def defaults(self):
        """ Safe defaults for names in case the module is disabled """

        return {"cr_shelter_flag_id":  FieldTemplate.dummy("flag_id"),
                }

    # -------------------------------------------------------------------------
    @staticmethod
    def shelter_flag_onvalidation(form):
        """
            Shelter Flag form validation:
                - if create_task=True, then task_description is required
        """

        T = current.T
        formvars = form.vars

        create_task = formvars.get("create_task")
        task_description = formvars.get("task_description")

        if create_task and not task_description:
            form.errors["task_description"] = T("Task Description required")

    # -------------------------------------------------------------------------
    @staticmethod
    def shelter_inspection_flag_onaccept(form):
        """
            Shelter inspection flag onaccept:
                - auto-creates task if/as configured
        """

        settings = current.deployment_settings

        if not settings.get_cr_shelter_inspection_tasks():
            # Automatic task creation disabled
            return

        try:
            record_id = form.vars.id
        except AttributeError:
            # Nothing we can do
            return

        db = current.db
        s3db = current.s3db

        # Tables
        table = s3db.cr_shelter_inspection_flag
        ftable = s3db.cr_shelter_flag
        itable = s3db.cr_shelter_inspection
        utable = s3db.cr_shelter_unit
        ltable = s3db.cr_shelter_inspection_task
        ttable = s3db.project_task

        # Get the record
        join = (itable.on(itable.id == table.inspection_id),
                utable.on(utable.id == itable.shelter_unit_id),
                ftable.on(ftable.id == table.flag_id),
                )
        left = ltable.on(ltable.inspection_flag_id == table.id)
        query = (table.id == record_id)
        row = db(query).select(table.id,
                               table.flag_id,
                               ftable.create_task,
                               ftable.task_description,
                               ftable.task_priority,
                               ftable.task_assign_to,
                               ltable.task_id,
                               itable.shelter_unit_id,
                               utable.name,
                               join = join,
                               left = left,
                               limitby = (0, 1),
                               ).first()
        if not row:
            return

        create_task = False
        create_link = None

        flag = row.cr_shelter_flag
        task_description = flag.task_description
        task_priority = flag.task_priority
        task_assign_to = flag.task_assign_to

        shelter_unit = row.cr_shelter_unit.name

        if flag.create_task:

            inspection_task = row.cr_shelter_inspection_task
            if inspection_task.task_id is None:

                shelter_unit_id = row.cr_shelter_inspection.shelter_unit_id
                flag_id = row.cr_shelter_inspection_flag.flag_id

                # Do we have any active task for the same problem
                # in the same shelter unit?
                active_statuses = settings.get_cr_shelter_inspection_task_active_statuses()
                left = (itable.on(itable.id == table.inspection_id),
                        ltable.on(ltable.inspection_flag_id == table.id),
                        ttable.on(ttable.id == ltable.task_id),
                        )
                query = (table.flag_id == flag_id) & \
                        (table.deleted == False) & \
                        (ttable.name == task_description) & \
                        (ttable.status.belongs(active_statuses)) & \
                        (ttable.deleted == False) & \
                        (itable.shelter_unit_id == shelter_unit_id) & \
                        (itable.deleted == False)
                row = db(query).select(ttable.id,
                                       left = left,
                                       limitby = (0, 1),
                                       ).first()
                if row:
                    # Yes => link to this task
                    create_link = row.id
                else:
                    # No => create a new task
                    create_task = True

        if create_task:

            # Create a new task
            task = {"name": "%s: %s" % (shelter_unit, task_description),
                    "priority": task_priority,
                    "pe_id": task_assign_to,
                    }
            task_id = ttable.insert(**task)
            if task_id:
                task["id"] = task_id

                # Post-process create
                s3db.update_super(ttable, task)
                auth = current.auth
                auth.s3_set_record_owner(ttable, task_id)
                auth.s3_make_session_owner(ttable, task_id)
                s3db.onaccept(ttable, task, method="create")

                create_link = task_id

        if create_link:

            # Create the cr_shelter_inspection_task link
            ltable.insert(inspection_flag_id = record_id,
                          task_id = create_link,
                          )

    # -------------------------------------------------------------------------
    @staticmethod
    def shelter_inspection_task_ondelete_cascade(row, tablename=None):
        """
            Ondelete-cascade method for inspection task links:
                - closes the linked task if there are no other
                  unresolved flags linked to it
        """

        db = current.db
        s3db = current.s3db

        # Get the task_id
        ltable = s3db.cr_shelter_inspection_task
        query = (ltable.id == row.id)
        link = db(query).select(ltable.id,
                                ltable.task_id,
                                limitby = (0, 1),
                                ).first()
        task_id = link.task_id

        # Are there any other unresolved flags linked to the same task?
        ftable = s3db.cr_shelter_inspection_flag
        ttable = s3db.project_task
        query = (ltable.task_id == task_id) & \
                (ltable.id != link.id) & \
                (ltable.deleted != True) & \
                (ftable.id == ltable.inspection_flag_id) & \
                ((ftable.resolved == False) | (ftable.resolved == None))
        other = db(query).select(ltable.id,
                                 limitby = (0, 1)
                                 ).first()
        if not other:
            # Set task to completed status
            closed = current.deployment_settings \
                            .get_cr_shelter_inspection_task_completed_status()
            db(ttable.id == task_id).update(status = closed)

            # Remove task_id (to allow deletion of the link)
            link.update_record(task_id = None)

# =============================================================================
class CRShelterRegistrationModel(DataModel):

    names = ("cr_shelter_registration",
             "cr_shelter_registration_history",
             "cr_shelter_registration_status_opts",
             )

    def model(self):

        T = current.T

        settings = current.deployment_settings
        crud_strings = current.response.s3.crud_strings

        configure = self.configure
        define_table = self.define_table

        person_id = self.pr_person_id
        shelter_id = self.cr_shelter_id
        shelter_unit_id = self.cr_shelter_unit_id

        # ---------------------------------------------------------------------
        # Shelter Registration: table to register a person to a shelter
        #
        # Registration status
        reg_status_opts = {1: T("Planned"),
                           2: T("Checked-in"),
                           3: T("Checked-out"),
                           }

        reg_status = FieldTemplate("registration_status", "integer",
                                   label = T("Status"),
                                   represent = S3Represent(options=reg_status_opts),
                                   requires = IS_IN_SET(reg_status_opts,
                                                        zero=None
                                                        ),
                                   )

        housing_unit = settings.get_cr_shelter_units()

        tablename = "cr_shelter_registration"
        define_table(tablename,
                     # The comment explains how to register a new person
                     # it should not be done in a popup
                     person_id(
                         comment = DIV(_class="tooltip",
                                       _title="%s|%s" % (T("Person"),
                                                         #  @ToDo: Generalise (this is EVASS-specific)
                                                         T("Type the name of a registered person \
                                                           or to add an unregistered person to this \
                                                           shelter click on Evacuees")
                                                         )
                                       ),
                         ),
                     shelter_id(empty = False,
                                ondelete = "CASCADE",
                                ),
                     shelter_unit_id(readable = housing_unit,
                                     writable = housing_unit,
                                     ),
                     shelter_id("last_shelter_id",
                                readable = False,
                                writable = False,
                                ),
                     shelter_unit_id("last_shelter_unit_id",
                                     readable = False,
                                     writable = False,
                                     ),
                     reg_status(default=1),
                     DateTimeField("check_in_date",
                                   label = T("Check-in date"),
                                   default = "now",
                                   #empty = False,
                                   future = 0,
                                   ),
                     DateTimeField("check_out_date",
                                   label = T("Check-out date"),
                                   ),
                     CommentsField(),
                     )

        configure(tablename,
                  deduplicate = S3Duplicate(primary = ("person_id",)),
                  onaccept = self.shelter_registration_onaccept,
                  ondelete = self.shelter_registration_ondelete,
                  )

        if housing_unit:
            configure(tablename,
                      onvalidation = self.shelter_registration_onvalidation,
                      )

        # Custom Methods
        self.set_method("cr_shelter_registration",
                        method = "assign",
                        action = cr_AssignUnit())

        # ---------------------------------------------------------------------
        # Shelter Registration History: history of status changes
        #
        tablename = "cr_shelter_registration_history"
        define_table(tablename,
                     person_id(),
                     self.cr_shelter_id(),
                     DateTimeField(default = "now",
                                   ),
                     reg_status("previous_status",
                                label = T("Old Status"),
                                ),
                     reg_status("status",
                                label = T("New Status"),
                                ),
                     )

        configure(tablename,
                  list_fields = ["shelter_id",
                                 "date",
                                 (T("Status"), "status"),
                                 (T("Modified by"), "modified_by"),
                                 ],
                  insertable = False,
                  editable = False,
                  deletable = False,
                  orderby = "%s.date desc" % tablename,
                  )

        # CRUD strings
        crud_strings[tablename] = Storage(
            title_list = T("Shelter Registration History"),
            )

        # ---------------------------------------------------------------------
        # Pass variables back to global scope (response.s3.*)
        return {"cr_shelter_registration_status_opts": reg_status_opts,
                }

    # -------------------------------------------------------------------------
    @staticmethod
    def shelter_registration_onvalidation(form):
        """
            Checks if the housing unit belongs to the requested shelter
        """

        T = current.T

        db = current.db
        s3db = current.s3db

        record_id = get_form_record_id(form)

        if hasattr(form, "record") and form.record:
            record = form.record
        else:
            record = None

        table = s3db.cr_shelter_registration
        form_vars = form.vars
        lookup = []

        def get_field_value(fn):
            if fn in form_vars:
                # Modified by form => use form.vars
                value = form_vars[fn]
            elif record_id:
                # Existing record => use form.record or lookup
                if record and fn in record:
                    value = record[fn]
                else:
                    lookup.append(table[fn])
                    value = None
            else:
                # New record => use table default
                value = table[fn].default
            return value

        registration_status = get_field_value("registration_status")
        shelter_id = get_field_value("shelter_id")
        shelter_unit_id = get_field_value("shelter_unit_id")

        if record_id and lookup:
            # Lookup from record
            row = db(table.id == record_id).select(*lookup, limitby=(0, 1)).first()
            if row:
                if "registration_status" in row:
                    registration_status = row.registration_status
                if "shelter_id" in row:
                    shelter_id = row.shelter_id
                if "shelter_unit_id" in row:
                    shelter_unit_id = row.shelter_unit_id

        stable = s3db.cr_shelter
        utable = s3db.cr_shelter_unit

        if shelter_id and shelter_unit_id:
            # Verify that they match
            query = (utable.id == shelter_unit_id) & \
                    (utable.shelter_id == shelter_id)
            row = db(query).select(utable.id, limitby=(0, 1)).first()
            if not row:
                msg = T("You have to select a housing unit belonging to the shelter")
                form.errors.shelter_unit_id = msg

        elif not shelter_id and not shelter_unit_id:
            # Missing data
            msg = T("Shelter or housing unit required")
            form.errors.shelter_id = \
            form.errors.shelter_unit_id = msg

        if str(registration_status) != "3":
            # Verify that the shelter is open when attempting to check-in people
            if shelter_id:
                query = (stable.id == shelter_id)
            elif shelter_unit_id:
                query = (stable.id == utable.shelter_id) & \
                        (utable.id == shelter_unit_id)
            else:
                query = None
            if query:
                row = db(query).select(stable.status, limitby=(0, 1)).first()
            else:
                row = None

            if row and row.status == 1:
                msg = T("Shelter is closed")
                if "registration_status" in form_vars:
                    form.errors.registration_status = msg
                else:
                    form.errors.shelter_id = \
                    form.errors.shelter_unit_id = msg

    # -------------------------------------------------------------------------
    @classmethod
    def shelter_registration_onaccept(cls, form):
        """
            Onaccept of shelter registration:
                - updates registration history
                - updates shelter / housing unit census
        """

        record_id = get_form_record_id(form)

        # Get the registration
        db = current.db
        s3db = current.s3db

        # Get the current status
        table = s3db.cr_shelter_registration
        query = (table.id == record_id) & \
                (table.deleted != True)
        registration = db(query).select(table.id,
                                        table.shelter_id,
                                        table.shelter_unit_id,
                                        table.last_shelter_id,
                                        table.last_shelter_unit_id,
                                        table.registration_status,
                                        table.check_in_date,
                                        table.check_out_date,
                                        table.modified_on,
                                        table.person_id,
                                        limitby = (0, 1),
                                        ).first()
        if not registration:
            return

        person_id = registration.person_id
        shelter_id = registration.shelter_id
        unit_id = registration.shelter_unit_id
        last_unit_id = registration.last_shelter_unit_id
        last_shelter_id = registration.last_shelter_id

        update = {}

        # Add shelter ID if missing
        if unit_id and not shelter_id:
            utable = s3db.cr_shelter_unit
            unit = db(utable.id == unit_id).select(utable.shelter_id,
                                                   limitby = (0, 1),
                                                   ).first()
            if unit:
                shelter_id = update["shelter_id"] = unit.shelter_id

        # Get the last registration history entry
        htable = s3db.cr_shelter_registration_history
        query = (htable.person_id == person_id) & \
                (htable.deleted != True)
        row = db(query).select(htable.status,
                               htable.date,
                               orderby = (~htable.date, ~htable.id),
                               limitby = (0, 1)
                               ).first()

        if row:
            previous_status = row.status
            previous_date = row.date
        else:
            previous_status = None
            previous_date = None

        # Get the effective date field
        current_status = registration.registration_status
        if current_status == 2:
            effective_date_field = "check_in_date"
        elif current_status == 3:
            effective_date_field = "check_out_date"
        else:
            effective_date_field = None

        # Get effective date
        if effective_date_field:
            effective_date = registration[effective_date_field]
            if not effective_date or shelter_id != last_shelter_id or \
               previous_date and effective_date < previous_date:
                effective_date = update[effective_date_field] = registration.modified_on
        else:
            effective_date = registration.modified_on

        # Status or shelter changed?
        if current_status != previous_status or shelter_id != last_shelter_id:

            # Insert new history entry
            entry = {"previous_status": previous_status,
                     "status": current_status,
                     "date": effective_date,
                     "person_id": person_id,
                     "shelter_id": shelter_id,
                     }
            entry_id = entry["id"] = htable.insert(**entry)
            s3db.update_super(htable, entry)
            current.auth.s3_set_record_owner(htable, entry_id)
            s3db.onaccept(htable, entry, method="create")

            if current_status == 3: # checked-out
                # Register a CHECKOUT-event at the current shelter
                shelter = Shelter(shelter_id)
                if shelter and shelter.site_id:
                    SitePresence.register(person_id, shelter.site_id, "CHECKOUT")

        # Update registration
        if current_status != 3:
            # Remove check-out-date if not checked-out
            update["check_out_date"] = None
        if current_status not in (2, 3):
            # Remove check-in date if neither checked-in nor checked-out
            update["check_in_date"] = None
        update["last_shelter_id"] = shelter_id
        update["last_shelter_unit_id"] = unit_id
        registration.update_record(**update)

        # Update housing unit census
        if last_unit_id and last_unit_id != unit_id:
            HousingUnit(last_unit_id).update_population()
        if unit_id:
            HousingUnit(unit_id).update_population()

        # Update shelter census
        if last_shelter_id and last_shelter_id != shelter_id:
            last_shelter = Shelter(last_shelter_id)
            last_shelter.update_population()
            # ...also register a check-out event at the last shelter
            SitePresence.register(person_id, last_shelter.site_id, "CHECKOUT")
        if shelter_id:
            Shelter(shelter_id).update_population()

        # Warn user if shelter / housing unit is full
        cr_warn_if_full(shelter_id, unit_id)

    # -------------------------------------------------------------------------
    @staticmethod
    def shelter_registration_ondelete(row):
        """
            Ondelete of shelter registration:
                - updates census of housing unit and shelter
        """

        unit_id = row.shelter_unit_id
        if unit_id:
            HousingUnit(unit_id).update_population()

        Shelter(row.shelter_id).update_population()

# =============================================================================
class CRShelterAllocationModel(DataModel):

    names = ("cr_shelter_allocation",
             )

    def model(self):

        T = current.T

        configure = self.configure
        define_table = self.define_table

        shelter_id = self.cr_shelter_id

        # ---------------------------------------------------------------------
        # Shelter Allocation: table to allocate shelter capacity to a group
        #
        allocation_status_opts = {1: T("requested"),
                                  2: T("available"),
                                  3: T("allocated"),
                                  4: T("occupied"),
                                  5: T("departed"),
                                  6: T("obsolete"),
                                  7: T("unavailable"),
                                  }

        tablename = "cr_shelter_allocation"
        define_table(tablename,
                     shelter_id(empty = False,
                                ondelete = "CASCADE",
                                ),
                     self.pr_group_id(comment = None),
                     Field("status", "integer",
                           default = 3,
                           label = T("Status"),
                           represent = represent_option(allocation_status_opts),
                           requires = IS_IN_SET(allocation_status_opts),
                           ),
                     Field("group_size_day", "integer",
                           default = 0,
                           label = T("Group Size"),
                           ),
                     Field("group_size_night", "integer",
                           default = 0,
                           label = T("Group Size (Night)"),
                           readable = False,
                           writable = False,
                           ),
                     )

        configure(tablename,
                  onaccept = self.shelter_allocation_onaccept,
                  ondelete = self.shelter_allocation_ondelete,
                  )

    # -------------------------------------------------------------------------
    @classmethod
    def shelter_allocation_onaccept(cls, form):
        """
            Onaccept if shelter allocation:
                - updates available shelter capacity
        """

        record_id = get_form_record_id(form)
        if not record_id:
            return

        table = current.s3db.cr_shelter_allocation
        query = (table.id == record_id) & \
                (table.deleted == False)
        row = current.db(query).select(table.shelter_id,
                                       limitby = (0, 1),
                                       ).first()
        shelter_id = row.shelter_id if row else None

        if shelter_id:
            Shelter(row.shelter_id).update_available_capacity()
            cr_warn_if_full(shelter_id, None)

    # -------------------------------------------------------------------------
    @staticmethod
    def shelter_allocation_ondelete(row):
        """
            Ondelete of shelter allocation:
                - updates available shelter capacity
        """

        shelter_id = row.shelter_id
        if shelter_id:
            Shelter(shelter_id).update_available_capacity()

# =============================================================================
class Shelter:
    """ Methods for shelters """

    def __init__(self, shelter_id):
        """
            Args:
                shelter_id: the cr_shelter record ID
        """

        self.shelter_id = shelter_id

        settings = current.deployment_settings

        self.manage_units = settings.get_cr_shelter_units()
        self.manage_registrations = settings.get_cr_shelter_registration()
        self.manage_allocations = settings.get_cr_shelter_allocation()

        self.population_by_type = settings.get_cr_shelter_population_by_type()
        self.population_by_age_group = settings.get_cr_shelter_population_by_age_group()

        self._site_id = None

    # -----------------------------------------------------------------------------
    @property
    def site_id(self):
        """
            The site ID of the shelter (lazy property)

            Returns:
                site ID
        """

        site_id = self._site_id
        if not site_id:
            table = current.s3db.cr_shelter
            row = current.db(table.id == self.shelter_id).select(table.site_id,
                                                                 limitby = (0, 1),
                                                                 ).first()
            site_id = self._site_id = row.site_id if row else None

        return site_id

    # -----------------------------------------------------------------------------
    def update_status(self, date=None):
        """
            Updates the status record of the shelter; creates one if
            none exists for the date yet

            Args:
                date: the date of the status record (default: today)
        """

        db = current.db
        s3db = current.s3db

        shelter_id = self.shelter_id

        track_fields = ("status",
                        "capacity",
                        "blocked_capacity",
                        "population",
                        "population_adults",
                        "population_children",
                        )

        stable = s3db.cr_shelter
        fields = [stable.id] + [stable[fn] for fn in track_fields]
        query = (stable.id == shelter_id) & \
                (stable.deleted == False)
        shelter = db(query).select(*fields, limitby = (0, 1)).first()
        if not shelter:
            return

        status = {fn: shelter[fn] for fn in track_fields}
        if not date:
            date = current.request.utcnow.date()
        status["shelter_id"] = shelter_id
        status["date"] = date

        rtable = s3db.cr_shelter_status
        query = (rtable.shelter_id == shelter_id) & \
                (rtable.date == date) & \
                (rtable.deleted == False)
        report = db(query).select(rtable.id, limitby = (0, 1)).first()
        if report:
            report.update_record(**status)
            status["id"] = report.id
            s3db.onaccept(rtable, status, method="update")
        else:
            status_id = status["id"] = rtable.insert(**status)
            s3db.update_super(rtable, status)
            current.auth.s3_set_record_owner(rtable, status_id)
            s3db.onaccept(rtable, status, method="create")

    # -----------------------------------------------------------------------------
    def update_capacity(self, update_status=True):
        """
            Updates the total capacity of the shelter

            Args:
                update_status: also update available capacity and status record
        """

        db = current.db
        s3db = current.s3db

        shelter_id = self.shelter_id

        if self.manage_units:
            utable = s3db.cr_shelter_unit
            query = (utable.shelter_id == shelter_id) & \
                    (utable.status == 1) & \
                    (utable.deleted != True)
            total_capacity = utable.capacity.sum()
            total_blocked_capacity = utable.blocked_capacity.sum()
            row = db(query).select(total_capacity,
                                   total_blocked_capacity,
                                   ).first()
            if row:
                capacity = row[total_capacity]
                blocked_capacity = row[total_blocked_capacity]
            else:
                capacity = blocked_capacity = 0

            stable = s3db.cr_shelter
            db(stable.id == shelter_id).update(capacity = capacity,
                                               blocked_capacity = blocked_capacity,
                                               modified_by = stable.modified_by,
                                               modified_on = stable.modified_on,
                                               )
            self.update_available_capacity()
            self.update_status()
        else:
            # Capacity directly editable
            pass

    # -----------------------------------------------------------------------------
    def update_population(self, update_status=True):
        """
            Updates the population totals for this shelter

            Args:
                update_status: also update available capacity and status record
        """

        db = current.db
        s3db = current.s3db

        table = s3db.cr_shelter
        shelter_id = self.shelter_id

        update = {}

        if self.manage_registrations:
            # Get current population from registration count
            rtable = s3db.cr_shelter_registration
            query = (rtable.shelter_id == shelter_id) & \
                    (rtable.registration_status != 3) & \
                    (rtable.deleted == False)
            cnt = rtable.person_id.count(distinct=True)
            row = db(query).select(cnt).first()
            update["population"] = row[cnt] if row else 0

        elif self.manage_units:
            # Update from subtotals per housing unit
            utable = s3db.cr_shelter_unit
            query = (utable.shelter_id == shelter_id) & \
                    (utable.deleted == False)
            if self.population_by_age_group:
                cnt_a = utable.population_adults.sum()
                cnt_c = utable.population_children.sum()
                row = db(query).select(cnt_a, cnt_c).first()
                if row:
                    a, c = row[cnt_a], row[cnt_c]
                else:
                    a = c = 0
                update = {"population": a + c,
                          "population_adults": a,
                          "population_children": c,
                          }
            else:
                cnt = utable.population.sum()
                row = db(query).select(cnt).first()
                update["population"] = row[cnt] if row else 0

        elif self.population_by_type:
            # Update from subtotals per population type
            rtable = s3db.cr_shelter_population
            query = (rtable.shelter_id == shelter_id) & \
                    (rtable.deleted == False)

            if self.population_by_age_group:
                cnt_a = rtable.population_adults.sum()
                cnt_c = rtable.population_children.sum()
                row = db(query).select(cnt_a, cnt_c).first()
                if row:
                    a, c = row[cnt_a], row[cnt_c]
                else:
                    a = c = 0
                update = {"population": (a if a else 0) + (c if c else 0),
                          "population_adults": a,
                          "population_children": c,
                          }
            else:
                cnt = rtable.population.sum()
                row = db(query).select(cnt).first()
                update["population"] = row[cnt] if row else 0

        elif self.population_by_age_group:
            # Update total from subtotal per age group
            shelter = db(table.id == shelter_id).select(table.population_adults,
                                                        table.population_children,
                                                        limitby = (0, 1),
                                                        ).first()
            a = shelter.population_adults
            c = shelter.population_children
            update["population"] = (a if a else 0) + (c if c else 0)

        else:
            # Total population directly editable
            pass

        if update:
            update["modified_by"] = table.modified_by
            update["modified_on"] = table.modified_on
            db(table.id == shelter_id).update(**update)

        if update_status:
            self.update_available_capacity()
            self.update_status()

    # -----------------------------------------------------------------------------
    def update_available_capacity(self):
        """
            Updates the available capacity of the shelter
        """

        shelter_id = self.shelter_id

        db = current.db
        s3db = current.s3db

        table = s3db.cr_shelter
        query = (table.id == shelter_id)
        shelter = db(query).select(table.id,
                                   table.capacity,
                                   table.population,
                                   table.blocked_capacity,
                                   table.available_capacity,
                                   limitby = (0, 1),
                                   ).first()

        if not shelter:
            return

        update = {}

        # Compute available capacity
        capacity = shelter.capacity
        if capacity is None:
            capacity = update["capacity"] = 0

        if current.deployment_settings.get_cr_shelter_blocked_capacity():
            blocked_capacity = shelter.blocked_capacity
            if blocked_capacity is None:
                blocked_capacity = update["blocked_capacity"] = 0
            capacity -= blocked_capacity

        population = shelter.population
        if population is None:
            population = update["population"] = 0

        available_capacity = max(capacity - population, 0)

        if self.manage_allocations:
            # Look up allocation total
            atable = s3db.cr_shelter_allocation
            query = (atable.shelter_id == shelter_id) & \
                    (atable.status.belongs((1, 2, 3, 4))) & \
                    (atable.deleted == False)
            cnt = atable.group_size_day.sum()
            row = db(query).select(cnt).first()
            allocated_capacity = row[cnt] if row else 0

            # Subtract allocation total from available capacity
            available_capacity = max(available_capacity - allocated_capacity, 0)

        if available_capacity != shelter.available_capacity:
            update["available_capacity"] = available_capacity

        if update:
            update["modified_by"] = table.modified_by
            update["modified_on"] = table.modified_on
            shelter.update_record(**update)

# -----------------------------------------------------------------------------
class HousingUnit:
    """ Methods for housing units """

    def __init__(self, unit_id):
        """
            Args:
                unit_id: the cr_shelter_unit record ID
        """

        self.unit_id = unit_id

        settings = current.deployment_settings

        self.manage_registrations = settings.get_cr_shelter_registration()

        self.population_by_age_group = settings.get_cr_shelter_population_by_age_group()

    # -------------------------------------------------------------------------
    def update_population(self):
        """
            Updates total population and available capacity of this unit
        """

        unit_id = self.unit_id

        db = current.db
        s3db = current.s3db

        # Lookup shelter unit
        table = s3db.cr_shelter_unit
        query = (table.id == unit_id)
        unit = db(query).select(table.id,
                                table.capacity,
                                table.population,
                                table.population_adults,
                                table.population_children,
                                table.blocked_capacity,
                                table.available_capacity,
                                limitby = (0, 1),
                                ).first()
        if not unit:
            return

        if self.manage_registrations:
            # Get current population from registration count
            rtable = s3db.cr_shelter_registration
            query = (rtable.shelter_unit_id == unit_id) & \
                    (rtable.registration_status != 3) & \
                    (rtable.deleted == False)
            cnt = rtable.person_id.count(distinct=True)
            row = db(query).select(cnt).first()
            population = row[cnt] if row else 0
        else:
            if self.population_by_age_group:
                a = unit.population_adults
                c = unit.population_children
                population = (a if a else 0) + (c if c else 0)
            else:
                population = unit.population
                if population is None:
                    population = 0

        update = {}

        # Compute available capacity
        capacity = unit.capacity
        if capacity is None:
            capacity = update["capacity"] = 0

        if current.deployment_settings.get_cr_shelter_blocked_capacity():
            blocked_capacity = unit.blocked_capacity
            if blocked_capacity is None:
                blocked_capacity = update["blocked_capacity"] = 0
            capacity -= blocked_capacity

        available_capacity = max(capacity - population, 0)

        # Update unit if required
        if population != unit.population:
            update["population"] = population
        if available_capacity != unit.available_capacity:
            update["available_capacity"] = available_capacity
        if update:
            update["modified_by"] = table.modified_by
            update["modified_on"] = table.modified_on
            unit.update_record(**update)

# =============================================================================
def cr_rheader(r, tabs=None):
    """ CR Resource Headers """

    if r.representation != "html":
        # Resource headers only used in interactive views
        return None

    tablename, record = s3_rheader_resource(r)
    if tablename != r.tablename:
        resource = current.s3db.resource(tablename, id=record.id)
    else:
        resource = r.resource

    rheader = None
    rheader_fields = []

    if record:
        T = current.T

        if tablename == "cr_shelter":

            if not tabs:
                settings = current.deployment_settings

                tabs = [(T("Basic Details"), None),
                        #(T("Status Reports"), "status"),
                        ]
                if settings.get_L10n_translate_org_site():
                    tabs.append((T("Local Names"), "name"))
                if settings.get_cr_shelter_units():
                    tabs.append((T("Housing Units"), "shelter_unit"))
                if settings.get_cr_tags():
                    tabs.append((T("Tags"), "tag"))
                if settings.get_cr_shelter_allocation():
                    tabs.append((T("Client Reservation"), "shelter_allocation"))
                if settings.get_cr_shelter_registration():
                    tabs.append((T("Client Registration"), "shelter_registration"))

                if settings.has_module("hrm"):
                    STAFF = settings.get_hrm_staff_label()
                    tabs.append((STAFF, "human_resource"))
                    permitted = current.auth.s3_has_permission
                    if permitted("update", tablename, r.id) and \
                       permitted("create", "hrm_human_resource_site"):
                        tabs.append((T("Assign %(staff)s") % {"staff": STAFF}, "assign"))

                s3db = current.s3db
                try:
                    tabs = tabs + s3db.req_tabs(r, match=False)
                except AttributeError:
                    pass
                try:
                    tabs = tabs + s3db.inv_tabs(r)
                except AttributeError:
                    pass

                if settings.has_module("asset"):
                    tabs.append((T("Assets"), "asset"))

            rheader_fields = [["organisation_id"],
                              ["location_id"],
                              ["status"],
                              ]
            rheader_title = "name"

            rheader = S3ResourceHeader(rheader_fields, tabs, title=rheader_title)
            rheader = rheader(r, table = resource.table, record = record)

    return rheader

# =============================================================================
def cr_resolve_shelter_flags(task_id):
    """
        If a task is set to an inactive status, then marks all linked
        shelter inspection flags as resolved

        Args:
            task_id: the task record ID
    """

    db = current.db
    s3db = current.s3db

    active_statuses = current.deployment_settings \
                             .get_cr_shelter_inspection_task_active_statuses()

    # Get the task
    ttable = s3db.project_task
    query = (ttable.id == task_id)
    task = db(query).select(ttable.id,
                            ttable.status,
                            limitby = (0, 1),
                            ).first()

    if task and task.status not in active_statuses:

        # Mark all shelter inspection flags as resolved
        ltable = s3db.cr_shelter_inspection_task
        ftable = s3db.cr_shelter_inspection_flag
        query = (ltable.task_id == task.id) & \
                (ftable.id == ltable.inspection_flag_id) & \
                ((ftable.resolved == False) | (ftable.resolved == None))
        rows = db(query).select(ftable.id)
        ids = set(row.id for row in rows)
        db(ftable.id.belongs(ids)).update(resolved=True)

# =============================================================================
def cr_warn_if_full(shelter_id, unit_id):
    """
        Generates a response.warning if housing unit / shelter is at or over
        capacity

        Args:
            shelter_id: the shelter ID
            unit_id: the housing unit ID
    """

    if current.auth.permission.format != "html":
        return

    s3db = current.s3db
    if unit_id:
        table = s3db.cr_shelter_unit
        query = (table.id == unit_id)
    elif shelter_id:
        table = s3db.cr_shelter
        query = (table.id == shelter_id)
    else:
        return

    row = current.db(query).select(table.available_capacity,
                                   limitby = (0, 1),
                                   ).first()

    available_capacity = row.available_capacity if row else None
    full = available_capacity is None or available_capacity <= 0

    warning = None
    if full:
        T = current.T
        if unit_id:
            warning = T("Warning: this housing unit is full")
        else:
            warning = T("Warning: this shelter is full")

        response = current.response
        response_warning = response.warning
        if response_warning:
            response.warning = "%s - %s" % (response_warning, warning)
        else:
            response.warning = warning

# =============================================================================
class cr_AssignUnit(BasicCRUD):
    """
        Assign a Person to a Housing Unit (used in DRK-Village)
    """

    # -------------------------------------------------------------------------
    def apply_method(self, r, **attr):
        """
            Applies the method (controller entry point).

            Args:
                r: the CRUDRequest
                attr: controller arguments
        """

        try:
            person_id = int(r.get_vars["person_id"])
        except (AttributeError, ValueError, TypeError):
            r.error(400, current.messages.BAD_REQUEST)

        self.settings = current.response.s3.crud
        form = self.resource.get_config("crud_form")
        self.form = form if form else DefaultForm()
        self.data = None

        # Create or Update?
        table = current.s3db.cr_shelter_registration
        query = (table.deleted == False) & \
                (table.person_id == person_id)
        exists = current.db(query).select(table.id, limitby=(0, 1)).first()
        if exists:
            # Update form
            r.method = "update" # Ensure correct View template is used
            self.record_id = exists.id
            output = self.update(r, **attr)
        else:
            # Create form
            r.method = "create" # Ensure correct View template is used
            self.data = {"person_id": person_id}
            output = self.create(r, **attr)

        return output

# =============================================================================
class ShelterInspectionFlagRepresent(S3Represent):
    """ Representations of Shelter Inspection Flags """

    def __init__(self, show_link=False):
        """
            Args:
                show_link: represent as link to the shelter inspection
        """

        super().__init__(lookup = "cr_shelter_inspection_flag",
                         show_link = show_link,
                         )

    # ---------------------------------------------------------------------
    def link(self, k, v, row=None):
        """
            Links inspection flag representations to the inspection record

            Args:
                k: the inspection flag ID
                v: the representation
                row: the row from lookup_rows
        """

        if row:
            inspection_id = row.cr_shelter_inspection.id
            if inspection_id:
                return A(v, _href=URL(c="cr",
                                      f="shelter_inspection",
                                      args=[inspection_id],
                                      ),
                         )
        return v

    # ---------------------------------------------------------------------
    def represent_row(self, row):
        """
            Represents a Row

            Args:
                row: the Row
        """

        details = {"unit": row.cr_shelter_unit.name,
                   "date": row.cr_shelter_inspection.date,
                   "flag": row.cr_shelter_flag.name,
                   }

        return "%(unit)s (%(date)s): %(flag)s" % details

    # ---------------------------------------------------------------------
    def lookup_rows(self, key, values, fields=None):
        """
            Looks up all rows referenced by values.

            Args:
                key: the key Field
                values: the values
                fields: the fields to retrieve
        """

        s3db = current.s3db

        table = self.table
        ftable = s3db.cr_shelter_flag
        itable = s3db.cr_shelter_inspection
        utable = s3db.cr_shelter_unit

        left = (ftable.on(ftable.id == table.flag_id),
                itable.on(itable.id == table.inspection_id),
                utable.on(utable.id == itable.shelter_unit_id),
                )
        count = len(values)
        if count == 1:
            query = (table.id == values[0])
        else:
            query = (table.id.belongs(values))
        limitby = (0, count)

        rows = current.db(query).select(table.id,
                                        utable.name,
                                        itable.id,
                                        itable.date,
                                        ftable.name,
                                        left = left,
                                        limitby = limitby,
                                        )
        return rows

# =============================================================================
class ShelterInspectionRepresent(S3Represent):
    """ Representations of Shelter Inspections """

    def __init__(self, show_link=False):
        """
            Args:
                show_link: represent as link to the shelter inspection
        """

        super().__init__(lookup = "cr_shelter_inspection",
                         show_link = show_link,
                         )

    # ---------------------------------------------------------------------
    def link(self, k, v, row=None):
        """
            Links inspection flag representations to the inspection record

            Args:
                k: the inspection flag ID
                v: the representation
                row: the row from lookup_rows
        """

        if row:
            inspection_id = row.cr_shelter_inspection.id
            if inspection_id:
                return A(v, _href=URL(c="cr",
                                      f="shelter_inspection",
                                      args=[inspection_id],
                                      ),
                         )
        return v

    # ---------------------------------------------------------------------
    def represent_row(self, row):
        """
            Represents a Row

            Args:
                row: the Row
        """

        details = {"unit": row.cr_shelter_unit.name,
                   "date": row.cr_shelter_inspection.date,
                   }

        return "%(date)s: %(unit)s" % details

    # ---------------------------------------------------------------------
    def lookup_rows(self, key, values, fields=None):
        """
            Looks up all rows referenced by values.

            Args:
                key: the key Field
                values: the values
                fields: the fields to retrieve
        """

        s3db = current.s3db

        table = self.table

        utable = s3db.cr_shelter_unit
        left = utable.on(utable.id == table.shelter_unit_id)

        count = len(values)
        if count == 1:
            query = (table.id == values[0])
        else:
            query = (table.id.belongs(values))
        limitby = (0, count)

        rows = current.db(query).select(table.id,
                                        table.date,
                                        utable.name,
                                        left = left,
                                        limitby = limitby,
                                        )
        return rows

# =============================================================================
class CRShelterInspection(CRUDMethod):
    """
        Mobile-optimized UI for shelter inspection
    """

    # -------------------------------------------------------------------------
    def apply_method(self, r, **attr):
        """
            Main entry point for REST interface.

            Args:
                r: the CRUDRequest instance
                attr: controller parameters
        """

        if not self.permitted():
            current.auth.permission.fail()

        output = {}
        representation = r.representation

        if representation == "html":
            if r.http in ("GET", "POST"):
                output = self.inspection_form(r, **attr)
            else:
                r.error(405, current.ERROR.BAD_METHOD)

        elif representation == "json":
            if r.http == "POST":
                output = self.inspection_ajax(r, **attr)
            else:
                r.error(405, current.ERROR.BAD_METHOD)

        else:
            r.error(415, current.ERROR.BAD_FORMAT)

        return output

    # -------------------------------------------------------------------------
    @staticmethod
    def permitted():
        """
            Checks if the user is permitted to use this method
        """

        # @todo: implement
        return True

    # -------------------------------------------------------------------------
    def inspection_form(self, r, **attr):
        """
            Generates the form

            Args:
                r: the CRUDRequest instance
                attr: controller parameters
        """

        T = current.T
        db = current.db
        s3db = current.s3db

        settings = current.deployment_settings
        response = current.response

        output = {}

        # Limit selection of shelter units to current shelter
        record = r.record
        if record:
            utable = s3db.cr_shelter_unit
            dbset = db(utable.shelter_id == record.id)
        else:
            dbset = db

        # Representation methods for form widgets
        shelter_unit_represent = S3Represent(lookup="cr_shelter_unit")
        shelter_flag_represent = S3Represent(lookup="cr_shelter_flag",
                                             translate=True,
                                             )

        # Standard form fields and data
        formfields = [Field("shelter_unit_id",
                            label = T("Housing Unit"),
                            requires = IS_ONE_OF(dbset, "cr_shelter_unit.id",
                                                 shelter_unit_represent,
                                                 orderby = "shelter_id",
                                                 ),
                            widget = S3MultiSelectWidget(multiple = False,
                                                         search = True,
                                                         ),
                            ),
                      Field("shelter_flags",
                            label = T("Defects"),
                            requires = IS_ONE_OF(db, "cr_shelter_flag.id",
                                                 shelter_flag_represent,
                                                 multiple = True,
                                                 ),
                            widget = S3GroupedOptionsWidget(
                                        cols = 2,
                                        size = None,
                                        ),
                            ),
                      CommentsField(comment=None),
                      ]

        # Buttons
        submit_btn = INPUT(_class = "tiny primary button submit-btn",
                           _name = "submit",
                           _type = "button",
                           _value = T("Submit"),
                           )

        buttons = [submit_btn]

        # Add the cancel-action
        buttons.append(A(T("Cancel"), _class = "cancel-action action-lnk"))

        # Generate form
        widget_id = "shelter-inspection-form"
        formstyle = settings.get_ui_formstyle()
        form = SQLFORM.factory(record = None,
                               showid = False,
                               formstyle = formstyle,
                               table_name = "shelter_inspection",
                               buttons = buttons,
                               #hidden = hidden,
                               _id = widget_id,
                               *formfields)

        output["form"] = form

        # Custom view
        response.view = self._view(r, "cr/shelter_inspection.html")

        # Inject JS
        options = {"ajaxURL": r.url(None,
                                    method = "inspection",
                                    representation = "json",
                                    ),
                   }
        self.inject_js(widget_id, options)

        return output

    # -------------------------------------------------------------------------
    @staticmethod
    def inspection_ajax(r, **attr):
        """
            Ajax-registration of shelter inspection

            Args:
                r: the CRUDRequest instance
                attr: controller parameters
        """

        T = current.T

        db = current.db
        s3db = current.s3db

        # Load JSON data from request body
        s = r.body
        s.seek(0)
        try:
            data = json.load(s)
        except (ValueError, TypeError):
            r.error(400, current.ERROR.BAD_REQUEST)

        shelter_unit_id = data.get("u")
        if shelter_unit_id:
            # Register shelter inspection
            error = False

            # Read comments
            comments = data.get("c")

            # Find inspection record
            update = False
            itable = s3db.cr_shelter_inspection
            query = (itable.shelter_unit_id == shelter_unit_id) & \
                    (itable.date == current.request.utcnow.date()) & \
                    (itable.deleted != True)
            row = db(query).select(itable.id,
                                   limitby = (0, 1),
                                   ).first()
            if row:
                # Update this inspection
                update = True
                inspection_id = row.id
                row.update_record(comments = comments)
            else:
                # Create a new inspection
                inspection_id = itable.insert(shelter_unit_id = shelter_unit_id,
                                              comments = comments,
                                              )
            if inspection_id:
                # Currently selected flags
                flag_ids = data.get("f")

                if update:
                    # Remove all flags linked to the current inspection
                    # which are not in the current selection
                    query = (FS("inspection_id") == inspection_id)
                    if flag_ids:
                        query &= ~(FS("flag_id").belongs(flag_ids))
                    fresource = s3db.resource("cr_shelter_inspection_flag",
                                              filter = query,
                                              )
                    fresource.delete(cascade=True)

                if flag_ids:

                    # Determine which flags have been newly selected
                    ftable = s3db.cr_shelter_inspection_flag
                    if update:
                        query = (ftable.inspection_id == inspection_id) & \
                                (ftable.deleted == False)
                        rows = db(query).select(ftable.flag_id)
                        new = set(flag_ids) - set(row.flag_id for row in rows)
                    else:
                        new = set(flag_ids)

                    # Create links to newly selected flags
                    ftable = s3db.cr_shelter_inspection_flag
                    data = {"inspection_id": inspection_id,
                            }
                    for flag_id in new:
                        data["flag_id"] = flag_id
                        success = ftable.insert(**data)
                        if not success:
                            error = True
                            break
                        # Call onaccept to auto-create tasks
                        record = Storage(data)
                        record["id"] = success
                        s3db.onaccept(ftable, record)
            else:
                error = True

            if error:
                db.rollback()
                output = {"a": s3_str(T("Error registering shelter inspection")),
                          }
            else:
                output = {"m": s3_str(T("Registration successful")),
                          }
        else:
            # Error - no shelter unit selected
            output = {"a": s3_str(T("No shelter unit selected")),
                      }

        return json.dumps(output)

    # -------------------------------------------------------------------------
    @staticmethod
    def inject_js(widget_id, options):
        """
            Helper function to inject static JS and instantiate
            the shelterInspection widget

            Args:
                widget_id: the node ID where to instantiate the widget
                options: dict of widget options (JSON-serializable)
        """

        s3 = current.response.s3
        appname = current.request.application

        # Static JS
        scripts = s3.scripts
        if s3.debug:
            script = "/%s/static/scripts/S3/s3.shelter_inspection.js" % appname
        else:
            script = "/%s/static/scripts/S3/s3.shelter_inspection.min.js" % appname
        scripts.append(script)

        # Instantiate widget
        scripts = s3.jquery_ready
        script = '''$('#%(id)s').shelterInspection(%(options)s)''' % \
                 {"id": widget_id, "options": json.dumps(options)}
        if script not in scripts:
            scripts.append(script)

# END =========================================================================
