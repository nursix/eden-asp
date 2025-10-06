"""
    MED module customisations for MRCMS

    License: MIT
"""

from gluon import current, A

from core import ICON

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

    from ..patient import PatientSummary
    s3db.set_method("med_patient",
                    method = "summarize",
                    action = PatientSummary,
                    )

# -----------------------------------------------------------------------------
def med_patient_controller(**attr):

    T = current.T

    s3 = current.response.s3

    # Custom postp
    standard_postp = s3.postp
    def postp(r, output):
        # Call standard postp
        if callable(standard_postp):
            output = standard_postp(r, output)

        if r.record and isinstance(output, dict):
            if r.component_name == "epicrisis":
                # Inject button to generate summary PDF
                from ..helpers import inject_button
                btn = A(ICON("file-pdf"), T("Summary"),
                        data = {"url": r.url(component = "",
                                             method = "summarize",
                                             representation = "pdf",
                                             ),
                                },
                        _class = "action-btn activity button s3-download-button",
                        )
                inject_button(output, btn, before="delete_btn", alt=None)
        return output
    s3.postp = postp

    return attr

# END =========================================================================
