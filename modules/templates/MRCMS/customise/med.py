"""
    MED module customisations for MRCMS

    License: MIT
"""

from gluon import current

# =============================================================================
def med_patient_resource(r, tablename):

    s3db = current.s3db

    s3db.configure("med_patient",
                   # Update realm when moving patient between units
                   update_realm = True,
                   realm_components = ("vitals",
                                       "status",
                                       "treatment",
                                       "epicrisis",
                                       ),
                   )

# END =========================================================================
