# =============================================================================
#   1st RUN:
#       - Run update_check if needed.
#       - Import the S3 Framework Extensions
#       - If needed, copy deployment templates to the live installation.
# =============================================================================

# Shortcut
appname = request.application

# -----------------------------------------------------------------------------
# Perform update checks - will happen in 1st_run or on those upgrades when new
# dependencies have been added.
#
from updatechk import UpdateCheck
update_check_needed = False
try:
    if REQUIREMENTS_VERSION != UpdateCheck.REQUIREMENTS:
        update_check_needed = True
except NameError:
    update_check_needed = True

if update_check_needed:
    # Run update checks
    errors, warnings = UpdateCheck.check_all()

    # Catch-all check for dependency errors.
    # NB This does not satisfy the goal of calling out all the setup errors
    #    at once - it will die on the first fatal error encountered.
    try:
        import core as s3base
    except Exception as e:
        errors.append(e.message)

    import sys

    if warnings:
        # Report (non-fatal) warnings.
        prefix = "\n%s: " % T("WARNING")
        sys.stderr.write("%s%s\n" % (prefix, prefix.join(warnings)))
    if errors:
        # Report errors and stop.
        actionrequired = T("ACTION REQUIRED")
        prefix = "\n%s: " % actionrequired
        sys.stderr.write("%s%s\n" % (prefix, prefix.join(errors)))
        htmlprefix = "\n<br /><b>%s</b>: " % actionrequired
        html = "<errors>" + htmlprefix + htmlprefix.join(errors) + "\n</errors>"
        raise HTTP(500, body=html)

    # Create or update the canary file.
    from s3dal import portalocker
    canary = portalocker.LockedFile("applications/%s/models/0000_update_check.py" % appname, "w")
    statement = "REQUIREMENTS_VERSION = %s" % UpdateCheck.REQUIREMENTS
    canary.write(statement)
    canary.close()

# -----------------------------------------------------------------------------
import os
from collections import OrderedDict
from functools import reduce
from gluon import current
from gluon.storage import Storage

# Keep all S3 framework-level elements stored in response.s3, so as to avoid
# polluting global namespace & to make it clear which part of the framework is
# being interacted with.
# Avoid using this where a method parameter could be used:
# http://en.wikipedia.org/wiki/Anti_pattern#Programming_anti-patterns
response.s3 = Storage()
s3 = response.s3
s3.gis = Storage() # Defined early for use by S3Config.

current.cache = cache
# Limit for filenames on filesystem:
# https://en.wikipedia.org/wiki/Comparison_of_file_systems#Limits
# NB This takes effect during the file renaming algorithm - the length of uploaded filenames is unaffected
current.MAX_FILENAME_LENGTH = 255 # Defined early for use by S3Config.

# Import S3Config
import s3cfg
current.deployment_settings = deployment_settings = settings = s3cfg.S3Config()

if current.session.invalid:
    raise HTTP(423, "Invalid Session")

# END =========================================================================
