"""
    Observation Tables

    - to display observed/measured values along a date/time axis

    Copyright: 2026 (c) Sahana Software Foundation

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

__all__ = ("ObsTable",
           "ObsTableWidget",
           )

from gluon import current

from .base import CRUDMethod

# =============================================================================
class ObsTable(CRUDMethod):

    # -------------------------------------------------------------------------
    def apply_method(self, r, **attr):
        """
            Page-render entry point for CRUD Controller.

            Args:
                r: the CRUDRequest instance
                attr: controller attributes
        """

        # TODO implement

        output = {}
        if r.http == "GET":
            pass
        else:
            r.error(405, current.ERROR.BAD_METHOD)

        return output

# =============================================================================
class ObsTableWidget:
    """ Helper to configure and render the observation table UI """

    def __init__(self):
        # TODO docstring

        # TODO implement
        pass

    # -------------------------------------------------------------------------
    def html(self, widget_id):
        # TODO docstring

        # TODO implement
        pass

    # -------------------------------------------------------------------------
    @staticmethod
    def inject_script(widget_id, options):
        # TODO docstring

        # TODO implement
        pass

# END =========================================================================
