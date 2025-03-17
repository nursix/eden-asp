"""
    PR module customisations for BETRA

    License: MIT
"""

from gluon import current

# -------------------------------------------------------------------------
def pr_person_controller(**attr):

    # Custom rheader tabs
    from ..rheaders import dvr_rheader, hrm_rheader, default_rheader
    if current.request.controller == "dvr":
        attr["rheader"] = dvr_rheader
    elif current.request.controller == "hrm":
        attr["rheader"] = hrm_rheader
    elif current.request.controller == "default":
        attr["rheader"] = default_rheader

    return attr

# END =========================================================================
