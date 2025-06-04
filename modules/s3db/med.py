"""
    Emergency Medical Journal

    Copyright: 2024 (c) Sahana Software Foundation

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

__all__ = ("MedUnitModel",
           "MedPatientModel",
           "MedVitalsModel",
           "MedTreatmentModel",
           "MedStatusModel",
           "MedAnamnesisModel",
           "MedEpicrisisModel",
           "MedMedicationModel",
           "MedVaccinationModel",
           "med_UnitRepresent",
           "med_rheader",
           )

from gluon import *
from gluon.storage import Storage

from ..core import *

# =============================================================================
class MedUnitModel(DataModel):
    """ Medical Unit & Treatment Areas Model """

    names = ("med_unit",
             "med_unit_id",
             "med_area",
             "med_area_id",
             )

    def model(self):

        T = current.T
        db = current.db
        settings = current.deployment_settings

        s3 = current.response.s3
        crud_strings = s3.crud_strings

        define_table = self.define_table
        configure = self.configure
        super_link = self.super_link

        # ---------------------------------------------------------------------
        tablename = "med_unit"
        define_table(tablename,
                     super_link("pe_id", "pr_pentity"),
                     self.org_organisation_id(),
                     self.org_site_id(),
                     Field("name", length=64,
                           requires = IS_NOT_EMPTY(),
                           represent = lambda v, row=None: v if v else "-",
                           ),
                     )

        # Components
        self.add_components(tablename,
                            med_area = "unit_id",
                            )

        # Table configuration
        configure(tablename,
                  onvalidation = self.unit_onvalidation,
                  onaccept = self.unit_onaccept,
                  super_entity = ("pr_pentity",),
                  )

        # CRUD strings
        crud_strings[tablename] = Storage(
            label_create = T("Add Medical Unit"),
            title_display = T("Medical Unit"),
            title_list = T("Medical Units"),
            title_update = T("Edit Medical Unit"),
            label_list_button = T("List Medical Units"),
            label_delete_button = T("Delete Medical Unit"),
            msg_record_created = T("Medical Unit added"),
            msg_record_modified = T("Medical Unit updated"),
            msg_record_deleted = T("Medical Unit deleted"),
            msg_list_empty = T("No Medical Units currently registered"),
            )

        # Foreign key template
        represent = med_UnitRepresent()
        unit_id = FieldTemplate("unit_id", "reference %s" % tablename,
                                label = T("Unit"),
                                ondelete = "CASCADE",
                                represent = represent,
                                requires = IS_EMPTY_OR(
                                                IS_ONE_OF(db, "%s.id" % tablename,
                                                          represent,
                                                          )),
                                )

        # ---------------------------------------------------------------------
        # Area functions
        #
        area_functions = (("A", T("Arrival / Staging")),
                          ("T", T("Examination / Treatment")),
                          ("O", T("Observation")),
                          ("X", T("Transfer")),
                          )

        # ---------------------------------------------------------------------
        # Area status
        #
        area_status = (("O", T("Operational")),
                       ("Q", T("Quarantine")),
                       ("M", T("Maintenance")),
                       ("X", T("Closed")),
                       )

        area_status_represent = S3PriorityRepresent(area_status,
                                                    {"O": "green",
                                                     "Q": "amber",
                                                     "M": "red",
                                                     "X": "black",
                                                     }).represent

        # ---------------------------------------------------------------------
        # Areas (rooms)
        #
        tablename = "med_area"
        define_table(tablename,
                     unit_id(),
                     Field("name", length=64,
                           requires = IS_NOT_EMPTY(),
                           represent = lambda v, row=None: v if v else "-",
                           ),
                     Field("area_type",
                           default = "T",
                           requires = IS_IN_SET(area_functions,
                                                zero = None,
                                                sort = False,
                                                ),
                           represent = represent_option(dict(area_functions)),
                           ),
                     Field("capacity", "integer",
                           default = 1,
                           requires = IS_INT_IN_RANGE(minimum=1),
                           ),
                     Field("status",
                           default = "O",
                           requires = IS_IN_SET(area_status,
                                                zero = None,
                                                sort = False,
                                                ),
                           represent = area_status_represent,
                           ),
                     CommentsField(),
                     )

        # Table configuration
        configure(tablename,
                  onvalidation = self.area_onvalidation,
                  )

        # CRUD strings
        area_label = settings.get_med_area_label()
        if area_label == "area":
            crud_strings[tablename] = Storage(
                label_create = T("Add Treatment Area"),
                title_display = T("Treatment Area"),
                title_list = T("Treatment Areas"),
                title_update = T("Edit Treatment Area"),
                label_list_button = T("List Treatment Areas"),
                label_delete_button = T("Delete Treatment Area"),
                msg_record_created = T("Treatment Area added"),
                msg_record_modified = T("Treatment Area updated"),
                msg_record_deleted = T("Treatment Area deleted"),
                msg_list_empty = T("No Treatment Areas currently registered"),
                )
        else:
            crud_strings[tablename] = Storage(
                label_create = T("Add Room"),
                title_display = T("Room"),
                title_list = T("Rooms"),
                title_update = T("Edit Room"),
                label_list_button = T("List Rooms"),
                label_delete_button = T("Delete Room"),
                msg_record_created = T("Room added"),
                msg_record_modified = T("Room updated"),
                msg_record_deleted = T("Room deleted"),
                msg_list_empty = T("No Rooms currently registered"),
                )

        # Foreign key template
        represent = S3Represent(lookup=tablename)
        area_id = FieldTemplate("area_id", "reference %s" % tablename,
                                label = T("Area") if area_label == "area" else T("Room"),
                                ondelete = "RESTRICT",
                                represent = represent,
                                requires = IS_EMPTY_OR(
                                                IS_ONE_OF(db, "%s.id" % tablename,
                                                          represent,
                                                          )),
                                )

        # ---------------------------------------------------------------------
        # Pass names back to global scope (s3.*)
        #
        return {"med_unit_id": unit_id,
                "med_area_id": area_id,
                }

    # -------------------------------------------------------------------------
    def defaults(self):
        """ Safe defaults for names in case the module is disabled """

        dummy = FieldTemplate.dummy

        return {"med_unit_id": dummy("unit_id"),
                "med_area_id": dummy("area_id"),
                }

    # -------------------------------------------------------------------------
    @staticmethod
    def unit_onvalidation(form):
        """
            Form validation for medical units
            - name must be unique within the organisation
        """

        # Get form record id
        record_id = get_form_record_id(form)

        # Get form record data
        table = current.s3db.med_unit
        data = get_form_record_data(form, table, ["organisation_id", "name"])

        name = data.get("name")
        if name:
            # Name must be unique within the organisation
            query = (table.name == name)
            if record_id:
                query &= (table.id != record_id)
            query &= (table.organisation_id == data.get("organisation_id")) & \
                     (table.deleted == False)
            duplicate = current.db(query).select(table.id, limitby=(0, 1)).first()
            if duplicate:
                form.errors.name = current.T("A unit with that name already exists")

    # -------------------------------------------------------------------------
    @staticmethod
    def unit_onaccept(form):
        """
            Update Affiliation, record ownership and component ownership
        """

        current.s3db.org_update_affiliations("med_unit", form.vars)

    # -------------------------------------------------------------------------
    @staticmethod
    def area_onvalidation(form):
        """
            Form validation for treatment areas
            - name must be unique within the unit
        """

        # Get form record id
        record_id = get_form_record_id(form)

        # Get form record data
        table = current.s3db.med_area
        data = get_form_record_data(form, table, ["unit_id", "name"])

        name = data.get("name")
        if name:
            # Name must be unique within the unit
            query = (table.name == name)
            if record_id:
                query &= (table.id != record_id)
            query &= (table.unit_id == data.get("unit_id")) & \
                     (table.deleted == False)
            duplicate = current.db(query).select(table.id, limitby=(0, 1)).first()
            if duplicate:
                form.errors.name = current.T("An area with that name already exists")

# =============================================================================
class MedPatientModel(DataModel):
    """ Patient (Care Occasion) Data Model """

    names = ("med_patient",
             "med_patient_id",
             )

    def model(self):

        T = current.T
        db = current.db
        settings = current.deployment_settings

        s3 = current.response.s3
        crud_strings = s3.crud_strings

        define_table = self.define_table
        # configure = self.configure

        # ---------------------------------------------------------------------
        # Triage Priorities
        #
        triage_priorities = (("A", T("Immediate")),
                             ("B", T("Delayed")),
                             ("C", T("Minor")),
                             ("D", T("Deceased/Expectant")),
                             )

        triage_represent = S3PriorityRepresent(triage_priorities,
                                               {"A": "red",
                                                "B": "amber",
                                                "C": "green",
                                                "D": "black",
                                                }).represent

        # ---------------------------------------------------------------------
        # Contamination Hazards
        #
        hazards = (("B", T("Infection")),
                   ("R", T("Radiation")),
                   ("C", T("Toxic")),
                   )

        # ---------------------------------------------------------------------
        # Patient
        # - occasion when a person receives medical care (=is a patient)
        # - there can be multiple (successive) patient records for a person,
        #   but only one (active) at a time
        # TODO method to export entire patient record as PDF
        #
        tablename = "med_patient"
        define_table(tablename,
                     self.med_unit_id(
                         empty = False,
                         ondelete = "RESTRICT",
                         ),
                     Field("refno",
                           label = T("No."),
                           writable = False,
                           ),
                     # The patient
                     Field("unidentified", "boolean",
                           label = T("Unidentified Person"),
                           default = False,
                           ),
                     self.pr_person_id(
                         label = T("Identity"),
                         represent = self.pr_PersonRepresent(show_link=True),
                         comment = None,
                         ),

                     # TODO filterOptions
                     self.med_area_id(),

                     # Start and end date of the care occasion
                     DateTimeField(
                        default = "now",
                        writable = False,
                        ),
                     DateTimeField("end_date",
                        label = T("End Date"),
                        # TODO to be set automatically when the patient is concluded
                        readable = False,
                        writable = False,
                        ),

                     # Reason for the patient to seek care
                     Field("reason",
                           label = T("Reason for visit"),
                           requires = IS_NOT_EMPTY(),
                           ),
                     # TODO room/place
                     # TODO speciality?

                     # Contamination hazards
                     Field("hazards", "list:string",
                           label = T("Contamination Hazards"),
                           requires = IS_IN_SET(hazards, multiple=True, sort=False, zero=None),
                           represent = self.hazards_represent(hazards),
                           widget = S3GroupedOptionsWidget(multiple = True,
                                                           size = None,
                                                           cols = 1,
                                                           sort = False,
                                                           ),
                           ),
                     # TODO Display advice in rheader
                     Field("hazards_advice",
                           label = T("Hazard Advice"),
                           represent = lambda v, row=None: v if v else "-",
                           ),

                     Field("priority",
                           label = T("Priority"),
                           default = "C",
                           requires = IS_IN_SET(triage_priorities, zero=None, sort=False),
                           represent = triage_represent,
                           ),
                     # TODO deceased (maybe in person record instead?)
                     # TODO deceased_on (maybe in person record instead?)
                     # TODO inbound route (where did the patient come from?)
                     # TODO outbound route (destination)
                     # TODO replace by status:
                     # Flag to indicate that the care patient is concluded
                     # - TODO once set, the patient cannot be re-opened
                     # - TODO there can only be once patient open at any one time
                     Field("closed", "boolean",
                           label = T("Closed##status"),
                           default = False,
                           ),
                     # Flag to indicate that this is an invalid record
                     # - TODO filter out invalid records from all operative contexts
                     # - TODO have an archive-link (separate controller?) to access invalid records
                     Field("invalid", "boolean",
                           label = T("Invalid"),
                           default = False,
                           ),
                     CommentsField(),
                     )

        # Components
        self.add_components(tablename,
                            med_status = "patient_id",
                            med_treatment = "patient_id",
                            med_vitals = "patient_id",
                            med_epicrisis = {"joinby": "patient_id",
                                             "multiple": False,
                                             },
                            )

        # List fields
        # TODO make using areas a deployment setting
        # TODO show unit if user can see multiple
        area_label = T("Area") if settings.get_med_area_label() == "area" else T("Room")
        list_fields = [(area_label, "area_id$name"),
                       "priority",
                       "refno",
                       "person_id",
                       "reason",
                       "date",
                       #end_date,       # Only when viewing previous patients
                       (T("Hazards"), "hazards"),
                       "comments",
                       ]

        # Table configuration
        self.configure(tablename,
                       list_fields = list_fields,
                       onvalidation = self.patient_onvalidation,
                       onaccept = self.patient_onaccept,
                       # TODO if not using areas, order by priority
                       orderby = "med_area.name",
                       )

        # Foreign key template
        # TODO Representation as date+reason
        represent = S3Represent(lookup=tablename, fields=["date", "reason"])
        patient_id = FieldTemplate("patient_id", "reference %s" % tablename,
                                   label = T("Patient"),
                                   ondelete = "RESTRICT",
                                   represent = represent,
                                   requires = IS_EMPTY_OR(
                                                IS_ONE_OF(db, "%s.id" % tablename,
                                                          represent,
                                                          )),
                                   )

        # CRUD Strings
        crud_strings[tablename] = Storage(
            label_create = T("Add Patient"),
            title_display = T("Patient"),
            title_list = T("Patients"),
            title_update = T("Edit Patient"),
            label_list_button = T("List Patients"),
            label_delete_button = T("Delete Patient"),
            msg_record_created = T("Patient added"),
            msg_record_modified = T("Patient updated"),
            msg_record_deleted = T("Patient deleted"),
            msg_list_empty = T("No Patients currently registered"),
            )

        # ---------------------------------------------------------------------
        # Pass names back to global scope (s3.*)
        #
        return {"med_patient_id": patient_id,
                }

    # -------------------------------------------------------------------------
    def defaults(self):
        """ Safe defaults for names in case the module is disabled """

        return {"med_patient_id": FieldTemplate.dummy("patient_id"),
                }

    # -------------------------------------------------------------------------
    @staticmethod
    def patient_onvalidation(form):
        """
            Patient form validation:
            - there must be only one open patient record per person
        """

        # Get form record id
        record_id = get_form_record_id(form)

        # Get form record data
        table = current.s3db.med_patient
        data = get_form_record_data(form, table, ["person_id", "closed"])

        # Verify that there are no (other) open patient records for the same person
        closed = data.get("closed")
        if not closed:
            person_id = data.get("person_id")
            query = (table.person_id == person_id) & \
                    (table.closed == False)
            if record_id:
                query &= (table.id != record_id)
            query &= (table.deleted == False)
            row = current.db(query).select(table.id, limitby=(0, 1)).first()
            if row:
                error = current.T("Person already has an ongoing patient registration")
                form.errors.person_id = error

    # -------------------------------------------------------------------------
    @staticmethod
    def patient_onaccept(form):
        """
            Onaccept routine for patient records:
            - update person_id in component records
        """

        db = current.db
        s3db = current.s3db

        record_id = get_form_record_id(form)
        if not record_id:
            return

        table = s3db.med_patient
        query = (table.id == record_id) & \
                (table.deleted == False)
        record = db(query).select(table.id,
                                  table.refno,
                                  table.person_id,
                                  limitby = (0, 1),
                                  ).first()
        if not record:
            return

        # Set reference number
        if not record.refno:
            record.update_record(refno=str(record.id))

        # Update person_id in component records
        for tn in ("med_status",
                   "med_vitals",
                   "med_treatment",
                   "med_epicrisis",
                   ):
            ctable = s3db.table(tn)
            query = (ctable.patient_id == record_id) & \
                    (ctable.person_id != record.person_id) & \
                    (ctable.deleted == False)
            db(query).update(person_id = record.person_id,
                             modified_by = ctable.modified_by,
                             modified_on = ctable.modified_on,
                             )

    # -------------------------------------------------------------------------
    @staticmethod
    def hazards_represent(options):
        """
            Returns a function that represents a hazard list as group of icons

            Args:
                options: the hazard options

            Returns:
                representation function
        """

        hazards = dict(options)

        css = {"B": "hazard-bio",
               "R": "hazard-rad",
               "C": "hazard-tox",
               }

        def represent(value, row=None):

            if value is None:
                value = []

            representation = DIV(_class="med-hazards")
            for k, v in hazards.items():
                item = SPAN(_class=css.get(k, "hazard-any"))
                if k in value:
                    item["_title"] = v
                    item.add_class("hazard-pos")
                else:
                    item.add_class("hazard-neg")
                representation.append(item)

            return representation

        return represent

    # -------------------------------------------------------------------------
    @staticmethod
    def set_patient(record):
        # TODO docstring

        db = current.db
        s3db = current.s3db

        table = s3db.med_patient

        if record.patient_id:
            query = (table.id == record.patient_id) & \
                    (table.deleted == False)
            patient = db(query).select(table.person_id, limitby=(0, 1)).first()
            if patient:
                record.update_record(person_id=patient.person_id)

        elif record.person_id:
            query = (table.person_id == record.person_id) & \
                    (table.concluded == False) & \
                    (table.invalid == False) & \
                    (table.deleted == False)
            patient = db(query).select(table.id,
                                        orderby = ~table.date,
                                        limitby = (0, 1),
                                        ).first()
            if patient:
                record.update_record(patient_id=patient.id)

# =============================================================================
class MedStatusModel(DataModel):
    """ Data Model for medical status """

    names = ("med_status",
             )

    def model(self):

        T = current.T
        # db = current.db

        s3 = current.response.s3
        crud_strings = s3.crud_strings

        define_table = self.define_table
        # configure = self.configure

        # ---------------------------------------------------------------------
        # Medical Status Report
        # TODO make person component and add to tabs in med/person
        # TODO make r/o except for the original author
        #
        tablename = "med_status"
        define_table(tablename,
                     self.pr_person_id(
                         label = T("Patient"),
                         empty = False,
                         comment = None,
                         readable = False,
                         writable = False, # TODO set onaccept
                         ),
                     self.med_patient_id(
                         readable = False, # TODO make readable in person perspective
                         writable = False, # TODO set onaacept
                         ),
                     DateTimeField(
                        default = "now",
                        future = 0,
                        past = 24, # hours
                        ),
                     # TODO role (physician, nurse, paramedic, assistant, consultant, other)
                     CommentsField("situation",
                                   label = T("Situation"),
                                   represent = s3_text_represent,
                                   comment = None,
                                   ),
                     CommentsField("background",
                                   label = T("Background"),
                                   represent = s3_text_represent,
                                   comment = None,
                                   ),
                     CommentsField("assessment",
                                   label = T("Assessment"),
                                   represent = s3_text_represent,
                                   comment = None,
                                   ),
                     CommentsField("recommendation",
                                   label = T("Recommendation"),
                                   represent = s3_text_represent,
                                   comment = None
                                   ),
                     # TODO show this field for the original author
                     Field("complete", "boolean",
                           default = False,
                           label = T("Complete"),
                           readable = False,
                           writable = False,
                           ),
                     # TODO show this field for the original author
                     Field("invalid", "boolean",
                           default = False,
                           label = T("Invalid"),
                           readable = False,
                           writable = False,
                           ),
                     )

        # Table configuration
        # TODO list_fields (include author+date+role)
        self.configure(tablename,
                       onaccept = self.status_onaccept,
                       # TODO orderby: newest first
                       )

        # CRUD Strings
        crud_strings[tablename] = Storage(
            label_create = T("Add Status Report"),
            title_display = T("Status Report"),
            title_list = T("Status Reports"),
            title_update = T("Edit Status Report"),
            label_list_button = T("List Status Reports"),
            label_delete_button = T("Delete Status Report"),
            msg_record_created = T("Status Report added"),
            msg_record_modified = T("Status Report updated"),
            msg_record_deleted = T("Status Report deleted"),
            msg_list_empty = T("No Status Reports currently registered"),
            )

        # ---------------------------------------------------------------------
        # Pass names back to global scope (s3.*)
        #
        return {}

    # -------------------------------------------------------------------------
    def defaults(self):
        """ Safe defaults for names in case the module is disabled """

        return {}

    # -------------------------------------------------------------------------
    @staticmethod
    def status_onaccept(form):
        # TODO docstring

        db = current.db
        s3db = current.s3db

        record_id = get_form_record_id(form)

        table = s3db.med_status
        query = (table.id == record_id) & (table.deleted == False)
        record = db(query).select(table.id,
                                  table.person_id,
                                  table.patient_id,
                                  limitby = (0, 1),
                                  ).first()

        if record:
            MedPatientModel.set_patient(record)

# =============================================================================
class MedVitalsModel(DataModel):
    """ Data Model for vital signs """

    names = ("med_vitals",
             )

    def model(self):

        T = current.T
        # db = current.db

        s3 = current.response.s3
        crud_strings = s3.crud_strings

        define_table = self.define_table
        # configure = self.configure

        # ---------------------------------------------------------------------
        # Vital Signs
        # TODO make person component and add to tabs in med/person
        # TODO make r/o except for the original author
        #
        avcpu = (("A", T("Alert##consciousness")),
                 ("V", T("Verbal##consciousness")),
                 ("C", T("Confused##consciousness")),
                 ("P", T("Pain##consciousness")),
                 ("U", T("Unresponsive##consciousness")),
                 )

        tablename = "med_vitals"
        define_table(tablename,
                     self.pr_person_id(
                         label = T("Patient"),
                         empty = False,
                         comment = None,
                         readable = False,
                         writable = False, # TODO set onaccept
                         ),
                     self.med_patient_id(
                         readable = False, # TODO make readable in person perspective
                         writable = False, # TODO set onaacept
                         ),
                     DateTimeField(
                        default = "now",
                        future = 0,
                        past = 6, # hours
                        ),
                     # TODO Calculate onaccept
                     Field("warning_score", "integer",
                           label = T("Score"),
                           requires = IS_INT_IN_RANGE(minimum=0, maximum=24),
                           ),
                     Field("rf", "integer",
                           label = T("RF"),
                           requires = IS_INT_IN_RANGE(minimum=0, maximum=80),
                           ),
                     Field("o2sat", "integer",
                           label = T("O2 Sat%"),
                           requires = IS_INT_IN_RANGE(minimum=0, maximum=100),
                           ),
                     Field("o2sub", "integer",
                           label = T("O2 L/min"),
                           requires = IS_INT_IN_RANGE(minimum=0, maximum=20),
                           ),
                     Field("hypox", "boolean",
                           default = False,
                           label = T("Chronic Hypoxemia"),
                           ),
                     #Field("bp",
                     #      ),
                     Field("bp_sys", "integer",
                           label = T("BP sys"),
                           requires = IS_INT_IN_RANGE(minimum=20, maximum=300),
                           ),
                     Field("bp_dia", "integer",
                           label = T("BP dia"),
                           requires = IS_INT_IN_RANGE(minimum=20, maximum=300),
                           ),
                     Field("hf", "integer",
                           label = T("HF"),
                           requires = IS_INT_IN_RANGE(minimum=0, maximum=300),
                           ),
                     Field("temp", "double",
                           label = T("Temp"),
                           requires = IS_FLOAT_IN_RANGE(minimum=25.0, maximum=44.0),
                           ),
                     Field("consc",
                           default = "A",
                           label = T("Consciousness"),
                           requires = IS_IN_SET(avcpu, zero=None, sort=False),
                           represent = represent_option(dict(avcpu)),
                           ),
                     # TODO show this field for the original author
                     Field("complete", "boolean",
                           default = False,
                           label = T("Complete"),
                           readable = False,
                           writable = False,
                           ),
                     # TODO show this field for the original author
                     Field("invalid", "boolean",
                           default = False,
                           label = T("Invalid"),
                           readable = False,
                           writable = False,
                           ),
                     )

        # List fields
        list_fields = ["date",
                       "warning_score",
                       "rf",
                       "o2sat",
                       "o2sub",
                       "bp_sys",
                       "bp_dia",
                       "hf",
                       "temp",
                       "consc",
                       ]

        # Table configuration
        # TODO list_fields (include author+date+role)
        self.configure(tablename,
                       list_fields = list_fields,
                       onaccept = self.vitals_onaccept,
                       # TODO orderby: newest first
                       )

        # CRUD Strings
        crud_strings[tablename] = Storage(
            label_create = T("Add Vital Signs"),
            title_display = T("Vital Signs"),
            title_list = T("Vital Signs"),
            title_update = T("Edit Vital Signs"),
            label_list_button = T("List Vital Signs"),
            label_delete_button = T("Delete Vital Signs"),
            msg_record_created = T("Vital Signs added"),
            msg_record_modified = T("Vital Signs updated"),
            msg_record_deleted = T("Vital Signs deleted"),
            msg_list_empty = T("No Vital Signs currently registered"),
            )

        # ---------------------------------------------------------------------
        # Pass names back to global scope (s3.*)
        #
        return {}

    # -------------------------------------------------------------------------
    def defaults(self):
        """ Safe defaults for names in case the module is disabled """

        return {}

    # -------------------------------------------------------------------------
    @staticmethod
    def vitals_onaccept(form):
        # TODO docstring

        db = current.db
        s3db = current.s3db

        record_id = get_form_record_id(form)

        table = s3db.med_vitals
        query = (table.id == record_id) & (table.deleted == False)
        record = db(query).select(table.id,
                                  table.person_id,
                                  table.patient_id,
                                  limitby = (0, 1),
                                  ).first()

        if record:
            MedPatientModel.set_patient(record)

# =============================================================================
class MedTreatmentModel(DataModel):
    """ Data Model for treatment documentation """

    names = ("med_treatment",
             )

    def model(self):

        T = current.T
        # db = current.db

        s3 = current.response.s3
        crud_strings = s3.crud_strings

        define_table = self.define_table
        # configure = self.configure

        # ---------------------------------------------------------------------
        # Treatment
        # TODO make person component and add to tabs in med/person
        # TODO make r/o except for the original author
        #
        treatment_status = (("P", T("Pending")),
                            ("S", T("Started / Ongoing")),
                            ("C", T("Completed")),
                            ("R", T("Canceled")),
                            ("O", T("Obsolete")),
                            )

        tablename = "med_treatment"
        define_table(tablename,
                     self.pr_person_id(
                         label = T("Patient"),
                         empty = False,
                         comment = None,
                         readable = False,
                         writable = False, # TODO set onaccept
                         ),
                     self.med_patient_id(
                         readable = False, # TODO make readable in person perspective
                         writable = False, # TODO set onaacept
                         ),
                     DateTimeField(
                        default = "now",
                        future = 0,
                        past = 6, # hours
                        ),
                     # TODO physician / person responsible for order
                     Field("details", "text",
                           label = T("Order Details##med"),
                           requires = IS_NOT_EMPTY(),
                           ),
                     # TODO hash to detect changes in order
                     # TODO order can only be changed by original author
                     # TODO staff responsible for status change
                     Field("status",
                           default = "P",
                           label = T("Status"),
                           requires = IS_IN_SET(treatment_status, zero=None, sort=False),
                           represent = represent_option(dict(treatment_status)),
                           ),
                     # TODO previous status
                     # TODO status date
                     CommentsField(),
                     )

        # TODO List fields
        # list_fields = []

        # Table configuration
        self.configure(tablename,
                       # list_fields = list_fields,
                       onaccept = self.treatment_onaccept,
                       # TODO orderby: newest first
                       )

        # CRUD Strings
        crud_strings[tablename] = Storage(
            label_create = T("Add Order##med"),
            title_display = T("Order Details##med"),
            title_list = T("Treatment"),
            title_update = T("Edit Order##med"),
            label_list_button = T("List Orders##med"),
            label_delete_button = T("Delete Order##med"),
            msg_record_created = T("Order added##med"),
            msg_record_modified = T("Order updated##med"),
            msg_record_deleted = T("Order deleted##med"),
            msg_list_empty = T("No Treatments currently registered"),
            )

        # ---------------------------------------------------------------------
        # Pass names back to global scope (s3.*)
        #
        return {}

    # -------------------------------------------------------------------------
    def defaults(self):
        """ Safe defaults for names in case the module is disabled """

        return {}

    # -------------------------------------------------------------------------
    @staticmethod
    def treatment_onaccept(form):
        # TODO docstring

        db = current.db
        s3db = current.s3db

        record_id = get_form_record_id(form)

        table = s3db.med_treatment
        query = (table.id == record_id) & (table.deleted == False)
        record = db(query).select(table.id,
                                  table.person_id,
                                  table.patient_id,
                                  limitby = (0, 1),
                                  ).first()

        if record:
            MedPatientModel.set_patient(record)

# =============================================================================
class MedEpicrisisModel(DataModel):
    """ Epicrisis Report Model """

    names = ("med_epicrisis",
             )

    def model(self):

        T = current.T
        # db = current.db

        s3 = current.response.s3
        crud_strings = s3.crud_strings

        define_table = self.define_table
        # configure = self.configure

        # ---------------------------------------------------------------------
        # Epicrisis
        #
        tablename = "med_epicrisis"
        define_table(tablename,
                     self.pr_person_id(
                         label = T("Patient"),
                         empty = False,
                         comment = None,
                         readable = False,
                         writable = False,
                         ),
                     self.med_patient_id(
                         readable = False, # TODO make readable in person perspective
                         writable = False,
                         ),
                     CommentsField("situation",
                                   label = T("Initial Situation Details"),
                                   comment = None,
                                   ),
                     CommentsField("diagnoses",
                                   label = T("Diagnoses"),
                                   comment = None,
                                   ),
                     CommentsField("progress",
                                   label = T("Treatment / Progress"),
                                   comment = None,
                                   ),
                     CommentsField("outcome",
                                   label = T("Outcome"),
                                   comment = None,
                                   ),
                     CommentsField("recommendation",
                                   label = T("Recommendation"),
                                   comment = None,
                                   ),
                     Field("closed", "boolean",
                           label = T("Closed##status"),
                           default = False,
                           ),
                     )

        # Table configuration
        self.configure(tablename,
                       onaccept = self.epicrisis_onaccept,
                       )

        # CRUD Strings
        crud_strings[tablename] = Storage(
            label_create = T("Add Epicrisis##med"),
            title_display = T("Epicrisis Details##med"),
            title_list = T("Epicrisis"),
            title_update = T("Edit Epicrisis##med"),
            label_list_button = T("List Epicrisiss##med"),
            label_delete_button = T("Delete Epicrisis##med"),
            msg_record_created = T("Epicrisis added##med"),
            msg_record_modified = T("Epicrisis updated##med"),
            msg_record_deleted = T("Epicrisis deleted##med"),
            msg_list_empty = T("No Epicrisis currently registered"),
            )

        # ---------------------------------------------------------------------
        # Pass names back to global scope (s3.*)
        #
        return {}

    # -------------------------------------------------------------------------
    def defaults(self):
        """ Safe defaults for names in case the module is disabled """

        return {}

    # -------------------------------------------------------------------------
    @staticmethod
    def epicrisis_onaccept(form):
        # TODO docstring

        db = current.db
        s3db = current.s3db

        record_id = get_form_record_id(form)

        table = s3db.med_epicrisis
        query = (table.id == record_id) & (table.deleted == False)
        record = db(query).select(table.id,
                                  table.person_id,
                                  table.patient_id,
                                  limitby = (0, 1),
                                  ).first()

        if record:
            MedPatientModel.set_patient(record)

# =============================================================================
class MedAnamnesisModel(DataModel):
    """ Data Model for case anamnesis / background """

    names = ("med_anamnesis",
             )

    def model(self):

        T = current.T
        # db = current.db

        s3 = current.response.s3
        crud_strings = s3.crud_strings

        define_table = self.define_table
        configure = self.configure

        UNKNOWN = current.messages.UNKNOWN_OPT

        # ---------------------------------------------------------------------
        # Blood types
        #
        blood_types = {"A+": "A RhD pos",
                       "A-": "A RhD neg",
                       "B+": "B RhD pos",
                       "B-": "B RhD neg",
                       "AB+": "AB RhD pos",
                       "AB-": "AB RhD neg",
                       "O+": "O RhD pos",
                       "O-": "O RhD neg",
                       }

        # ---------------------------------------------------------------------
        # Anamnesis
        #
        tablename = "med_anamnesis"
        define_table(tablename,
                     self.pr_person_id(
                         comment = None,
                         ),
                     CommentsField("allergies",
                                   label = T("Allergies"),
                                   comment = None,
                                   ),
                     CommentsField("chronic",
                                   label = T("Chronic Conditions"),
                                   comment = None,
                                   ),
                     CommentsField("disabilities",
                                   label = T("Disabilities"),
                                   comment = None,
                                   ),
                     CommentsField("history",
                                   label = T("Medical History"),
                                   comment = None,
                                   ),
                     Field("height", "integer",
                           label = T("Height (cm)##body"),
                           requires = IS_EMPTY_OR(IS_INT_IN_RANGE(30, 280)),
                           represent = lambda v, row=None: str(v) if v else "-",
                           ),
                     Field("weight", "integer",
                           label = T("Weight (kg)##body"),
                           requires = IS_EMPTY_OR(IS_INT_IN_RANGE(2, 300)),
                           represent = lambda v, row=None: str(v) if v else "-",
                           ),
                     Field("blood_type",
                           label = T("Blood Type"),
                           requires = IS_EMPTY_OR(IS_IN_SET(blood_types, zero=UNKNOWN)),
                           represent = represent_option(blood_types, default=UNKNOWN),
                           ),
                     CommentsField(),
                     )

        # Table configuration
        configure(tablename,
                  deletable = False,
                  )

        # CRUD strings
        crud_strings[tablename] = Storage(
            label_create = T("Add Medical Background"),
            title_display = T("Medical Background"),
            title_update = T("Edit Medical Background"),
            label_delete_button = T("Delete Medical Background"),
            msg_record_created = T("Medical Background added"),
            msg_record_modified = T("Medical Background updated"),
            msg_record_deleted = T("Medical Background deleted"),
            )

        # ---------------------------------------------------------------------
        # Pass names back to global scope (s3.*)
        #
        return {}

    # -------------------------------------------------------------------------
    def defaults(self):
        """ Safe defaults for names in case the module is disabled """

        return {}

# =============================================================================
class MedMedicationModel(DataModel):
    """ Data Model to record chronic medication """

    names = ("med_substance",
             "med_medication",
             )

    def model(self):

        T = current.T
        db = current.db

        # s3 = current.response.s3
        # crud_strings = s3.crud_strings

        define_table = self.define_table
        # configure = self.configure

        # ---------------------------------------------------------------------
        # Medicine (generic substance)
        # TODO import XSLT
        #
        tablename = "med_substance"
        define_table(tablename,
                     Field("name",
                           label = T("Substance"),
                           requires = IS_NOT_EMPTY(),
                           represent = lambda v, row=None: v if v else "-",
                           ),
                     CommentsField(),
                     )

        # TODO onvalidation to exclude duplicates

        # Field template
        represent = S3Represent(lookup = tablename)
        substance_id = FieldTemplate("substance_id", "reference %s" % tablename,
                                     label = T("Substance"),
                                     ondelete = "RESTRICT",
                                     represent = represent,
                                     requires = IS_EMPTY_OR(
                                                    IS_ONE_OF(db, "%s.id" % tablename,
                                                              represent,
                                                              )),
                                                    )

        # TODO CRUD Strings

        # ---------------------------------------------------------------------
        # Priorities
        #
        priorities = (("A", T("Critical")),
                      ("B", T("Regular")),
                      ("C", T("Optional")),
                      )
        priority_represent = S3PriorityRepresent(priorities,
                                                 {"A": "red",
                                                  "B": "green",
                                                  "C": "lightblue",
                                                  }).represent

        # ---------------------------------------------------------------------
        # Pharmaceutical forms
        #
        pforms = {"TBL": T("Tbl##pharma"),  # tablet
                  "CPS": T("Cps##pharma"),  # capsule
                  "INH": T("Inh##pharma"),  # inhalation
                  "INJ": T("Inj##pharma"),  # injection
                  "INF": T("Inf##pharma"),  # infusion
                  "GTTS": T("Gtts##pharma"), # guttae/drops
                  "OINT": T("Oint##pharma"), # ointment/salve
                  "PULV": T("Pulv##pharma"), # pulver/powder
                  "SUPP": T("Supp##pharma"), # suppository
                  "OTH": T("Other"),
                  }

        # ---------------------------------------------------------------------
        # Application forms
        #
        aforms = (("PO", T("p.o.##medical")), # oral
                  ("SC", T("s.c.##medical")), # subcutaneous
                  ("IV", T("i.v.##medical")), # intravenous
                  ("IM", T("i.m.##medical")), # intramuscular
                  ("PR", T("p.r.##medical")), # per rectal
                  ("PA", T("p.a.##medical")), # partibus affectis
                  ("OTH", T("Other")),
                  )

        # ---------------------------------------------------------------------
        # Dosage units
        #
        dunits = (("MG", T("mg")),
                  ("G", T("g")),
                  ("ML", T("ml")),
                  ("L", T("l")),
                  ("DOS", T("Dose##pharma")),
                  ("IU", T("IU##pharma")),
                  ("UNIT", T("Unit##pharma")),
                  )
        # ---------------------------------------------------------------------
        # Medication (prescription)
        #
        tablename = "med_medication"
        define_table(tablename,
                     self.pr_person_id(
                         comment = None,
                         ),
                     Field("priority",
                           label = T("Priority"),
                           default = "B",
                           requires = IS_IN_SET(priorities, zero=None, sort=False),
                           represent = priority_represent,
                           ),
                     Field("pform",
                           label = T("Form##pharma"),
                           default = "TBL",
                           requires = IS_IN_SET(pforms, zero=None),
                           represent = represent_option(pforms),
                           ),
                     Field("product", length=255,
                           label = T("Preparation / Trade Name"),
                           requires = IS_EMPTY_OR(IS_LENGTH(255, minsize=1)),
                           represent = lambda v, row=None: v if v else "-",
                           ),
                     substance_id(),
                     Field("aform",
                           label = T("Application##pharma"),
                           default = "PO",
                           requires = IS_IN_SET(aforms, zero=None, sort=False),
                           represent = represent_option(dict(aforms)),
                           ),
                     Field("dosage", "double",
                           label = T("Dosage"),
                           requires = IS_FLOAT_IN_RANGE(minimum=0.01),
                           represent = lambda v, row=None: IS_FLOAT_AMOUNT.represent(v,
                                                                                     precision = 4,
                                                                                     fixed = False,
                                                                                     ),
                           ),
                     Field("dosage_unit",
                           label = T("Unit"),
                           requires = IS_IN_SET(dunits, zero="", sort=False),
                           represent = represent_option(dict(dunits)),
                           ),
                     Field("scheme",
                           label = T("Scheme"),
                           requires = IS_NOT_EMPTY(),
                           ),
                     Field("is_current", "boolean",
                           label = T("Current"),
                           default = True,
                           represent = BooleanRepresent(labels = False,
                                                        icons = True,
                                                        colors = True,
                                                        ),
                           ),
                     CommentsField(),
                     )

        list_fields = ["priority",
                       "is_current",
                       "pform",
                       "product",
                       "substance_id",
                       "dosage",
                       "dosage_unit",
                       "aform",
                       "scheme",
                       "comments",
                       # TODO use separate DateField and set onaccept
                       (T("Updated"), "modified_on"),
                       ]

        self.configure(tablename,
                       list_fields = list_fields,
                       )

        # TODO CRUD Strings

        # ---------------------------------------------------------------------
        # Pass names back to global scope (s3.*)
        #
        return {}

    # -------------------------------------------------------------------------
    def defaults(self):
        """ Safe defaults for names in case the module is disabled """

        return {}

# =============================================================================
class MedVaccinationModel(DataModel):
    """ Data Model to document vaccinations """

    names = ("med_vaccination_type",
             "med_vaccination",
             )

    def model(self):

        T = current.T
        db = current.db

        # s3 = current.response.s3
        # crud_strings = s3.crud_strings

        define_table = self.define_table
        # configure = self.configure

        # ---------------------------------------------------------------------
        # Vaccination Type
        # TODO import XSLT
        #
        tablename = "med_vaccination_type"
        define_table(tablename,
                     Field("name",
                           label = T("Name"),
                           requires = IS_NOT_EMPTY(),
                           represent = lambda v, row=None: v if v else "-",
                           ),
                     Field("vaccine_type",
                           label = T("Vaccine type"),
                           represent = lambda v, row=None: v if v else "-",
                           ),
                     CommentsField(),
                     )

        # TODO onvalidation to exclude duplicates

        # Field template
        represent = S3Represent(lookup = tablename,
                                fields = ["name", "vaccine_type"],
                                labels = "%(name)s (%(vaccine_type)s)",
                                )
        vaccination_type_id = FieldTemplate("type_id", "reference %s" % tablename,
                                            label = T("Vaccination Type"),
                                            ondelete = "RESTRICT",
                                            represent = represent,
                                            requires = IS_EMPTY_OR(
                                                        IS_ONE_OF(db, "%s.id" % tablename,
                                                                  represent,
                                                                  )),
                                            )

        # TODO CRUD Strings

        # ---------------------------------------------------------------------
        # TODO m2m link vaccination_type <=> disease
        #
        # ---------------------------------------------------------------------
        # Vaccination
        #
        tablename = "med_vaccination"
        define_table(tablename,
                     self.pr_person_id(
                         comment = None,
                         ),
                     vaccination_type_id(),
                     Field("product", length=255,
                           label = T("Preparation / Trade Name"),
                           represent = lambda v, row=None: v if v else "-",
                           requires = IS_EMPTY_OR(IS_LENGTH(255, minsize=1)),
                           ),
                     Field("lot_no", length=255,
                           label = T("LOT No."),
                           represent = lambda v, row=None: v if v else "-",
                           requires = IS_EMPTY_OR(IS_LENGTH(255, minsize=1)),
                           ),
                     DateField(),
                     CommentsField(),
                     )

        # TODO CRUD Strings

        # ---------------------------------------------------------------------
        # Pass names back to global scope (s3.*)
        #
        return {}

    # -------------------------------------------------------------------------
    def defaults(self):
        """ Safe defaults for names in case the module is disabled """

        return {}

# =============================================================================
class med_UnitRepresent(S3Represent):
    """ Representation of medical units """

    def __init__(self, *, show_org=None, show_link=False):
        """
            Args:
                show_org: include the organisation name (True|False)
                show_link: represent as link to the unit
        """

        super().__init__(lookup = "med_unit",
                         show_link = show_link,
                         )

        self._show_org = show_org

    # -------------------------------------------------------------------------
    @property
    def show_org(self):
        """
            Determines whether to include the organisation name in
            the representation; defaults to True when the user can
            read med_units from more than one organisation; can be
            overridden by explicit True|False constructor parameter
            "show_org"

            Returns:
                boolean
        """

        show_org = self._show_org
        if show_org is None:

            permissions = current.auth.permission
            permitted_realms = permissions.permitted_realms("med_unit", "read")

            if permitted_realms is None:
                show_org = True
            elif permitted_realms:
                orgs = current.s3db.pr_get_entities(permitted_realms,
                                                    types = ["org_organisation"],
                                                    represent = False,
                                                    )
                show_org = len(orgs) != 1
            else:
                show_org = True

            self._show_org = show_org

        return show_org

    # -------------------------------------------------------------------------
    def lookup_rows(self, key, values, fields=None):
        """
            Custom rows lookup

            Args:
                key: the key Field
                values: the values
                fields: list of fields to look up (unused)
        """

        count = len(values)
        if count == 1:
            query = (key == values[0])
        else:
            query = key.belongs(values)

        table = self.table
        fields = [table.id, table.name]

        if self.show_org:
            # Left join org?
            otable = current.s3db.org_organisation
            left = otable.on(otable.id == table.organisation_id)
            fields.append(otable.name)
        else:
            left = None

        rows = current.db(query).select(*fields, left=left, limitby=(0, count))
        self.queries += 1

        return rows

    # -------------------------------------------------------------------------
    def represent_row(self, row):
        """
            Generates a string representation from a Row

            Args:
                row: the Row
        """

        if self.show_org and hasattr(row, "org_organisation"):
            org_name = row.org_organisation.name
            row = row.med_unit
        else:
            org_name = None

        reprstr = "%s" % row.name
        if org_name:
            reprstr = "%s (%s)" % (reprstr, org_name)

        return reprstr

# =============================================================================
def med_rheader(r, tabs=None):
    """ MED resource headers """

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
        settings = current.deployment_settings

        if tablename == "pr_person":
            if not tabs:
                tabs = [(T("Basic Details"), None),
                        # TODO contacts tab
                        (T("Background"), "anamnesis"),
                        (T("Vaccinations"), "vaccination"),
                        (T("Medication"), "medication"),
                        (T("Care Occasions"), "patient"),
                        # TODO lab results
                        # TODO examinations / interventions
                        ]
            rheader_fields = [["date_of_birth"],
                              ]
            rheader_title = s3_fullname

        elif tablename == "med_patient":
            if not tabs:
                tabs = [(T("Overview"), None),
                        # Person details [viewing]
                        # TODO contacts tab     [viewing, if we have a person_id]
                        # Background [viewing]
                        # Vaccinations [viewing]
                        # Medication [viewing]
                        (T("Vital Signs"), "vitals"),
                        (T("Status Reports"), "status"),
                        (T("Treatment"), "treatment"),
                        # TODO lab results
                        # TODO examinations / interventions
                        (T("Epicrisis"), "epicrisis"),
                        ]
                if record.person_id:
                    tabs[1:1] = [(T("Person Details"), "person/"),
                                 (T("Background"), "anamnesis/"),
                                 (T("Medication"), "medication/"),
                                 (T("Vaccinations"), "vaccination/"),
                                 ]

            rheader_fields = [["priority", "hazards"],
                              ["date", "hazards_advice"],
                              ["reason"],
                              ]
            rheader_title = "person_id"

        elif tablename == "med_unit":
            if not tabs:
                if settings.get_med_area_label() == "area":
                    areas_label = T("Treatment Areas")
                else:
                    areas_label = T("Rooms")
                tabs = [(T("Basic Details"), None),
                        (areas_label, "area"),
                        ]

            rheader_fields = ["organisation_id",
                              "site_id",
                              ]
            rheader_title = "name"

        else:
            return None

        rheader = S3ResourceHeader(rheader_fields, tabs, title=rheader_title)
        rheader = rheader(r, table=resource.table, record=record)

    return rheader

# END =========================================================================
