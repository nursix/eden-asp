"""
    DOC module customisations for GIMS

    License: MIT
"""

from gluon import current

# -------------------------------------------------------------------------
def doc_image_resource(r, tablename):

    s3db = current.s3db

    if r.tablename == "cr_shelter":

        from core import CustomForm

        table = s3db.doc_image

        # Default date today
        field = table.date
        field.default = r.utcnow.date()

        crud_form = CustomForm("file",
                               "date",
                               "name",
                               "comments",
                               )
        list_fields = ["date", "name", "file", "comments"]

        s3db.configure("doc_image",
                       list_fields = list_fields,
                       crud_form = crud_form,
                       )
# END =========================================================================
