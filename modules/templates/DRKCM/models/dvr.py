"""
    DRKCM DVR Extensions

    Copyright: 2025 (c) AHSS

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

__all__ = ("DVRDiagnosisModel",
           )

from gluon import current, IS_EMPTY_OR, IS_LENGTH, IS_NOT_EMPTY
from gluon.storage import Storage

from s3dal import Field

from core import CommentsField, DataModel, FieldTemplate, IS_ONE_OF, \
                 S3Duplicate, S3Represent

# =============================================================================
class DVRDiagnosisModel(DataModel):
    """ Diagnoses, e.g. in Psychosocial Support """

    names = ("dvr_diagnosis",
             "dvr_diagnosis_suspected",
             "dvr_diagnosis_confirmed",
             )

    def model(self):

        T = current.T

        db = current.db
        s3 = current.response.s3

        define_table = self.define_table
        crud_strings = s3.crud_strings

        # ---------------------------------------------------------------------
        # Diagnoses
        #
        tablename = "dvr_diagnosis"
        define_table(tablename,
                     Field("name",
                           label = T("Diagnosis"),
                           requires = [IS_NOT_EMPTY(), IS_LENGTH(512, minsize=1)],
                           ),
                     CommentsField(),
                     )

        # Table configuration
        self.configure(tablename,
                       deduplicate = S3Duplicate(),
                       )

        # CRUD Strings
        crud_strings[tablename] = Storage(
            label_create = T("Create Diagnosis"),
            title_display = T("Diagnosis Details"),
            title_list = T("Diagnoses"),
            title_update = T("Edit Diagnosis"),
            label_list_button = T("List Diagnoses"),
            label_delete_button = T("Delete Diagnosis"),
            msg_record_created = T("Diagnosis created"),
            msg_record_modified = T("Diagnosis updated"),
            msg_record_deleted = T("Diagnosis deleted"),
            msg_list_empty = T("No Diagnoses currently defined"),
        )

        # Foreign Key Template
        represent = S3Represent(lookup=tablename, translate=True)
        diagnosis_id = FieldTemplate("diagnosis_id",
                                     "reference %s" % tablename,
                                     label = T("Diagnosis"),
                                     represent = represent,
                                     requires = IS_EMPTY_OR(
                                                 IS_ONE_OF(db, "%s.id" % tablename,
                                                           represent,
                                                           )),
                                     sortby = "name",
                                     )

        # ---------------------------------------------------------------------
        # Link tables for diagnosis <=> case activity (suspected and confirmed)
        #
        tablename = "dvr_diagnosis_suspected"
        define_table(tablename,
                     self.dvr_case_activity_id(
                         empty = False,
                         ondelete = "CASCADE",
                         ),
                     diagnosis_id(
                         empty = False,
                         ondelete = "RESTRICT",
                         ),
                     )

        tablename = "dvr_diagnosis_confirmed"
        define_table(tablename,
                     self.dvr_case_activity_id(
                         empty = False,
                         ondelete = "CASCADE",
                         ),
                     diagnosis_id(
                         empty = False,
                         ondelete = "RESTRICT",
                         ),
                     )

        # ---------------------------------------------------------------------
        # Pass names back to global scope (s3.*)
        #
        return None

# END =========================================================================
