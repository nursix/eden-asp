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

from gluon import current, \
                  TABLE, THEAD, TBODY, TFOOT, TR, TH, TD, DIV

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
            output = self.render_table(r, **attr)
        else:
            r.error(405, current.ERROR.BAD_METHOD)

        return output

    # -------------------------------------------------------------------------
    def render_table(self, r, **attr):
        """
            Render the observation table (HTML method)

            Args:
                r: the CRUDRequest instance
                attr: controller attributes

            Returns:
                dict of values for the view
        """

        output = {}

        widget_id = "obstable"

        # Instantiate Widget
        widget = ObsTableWidget()
        output["obstable"] = widget.html(widget_id = widget_id,
                                         )

        # View
        current.response.view = self._view(r, "obstable.html")

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
        obstable = TABLE(_class = "obstable-table",
                         _id = widget_id,
                         )

        # TODO render header    (Repeat as footer)
        # <thead>
        #   <tr>
        #     <th scope="col" class="fixed">Parameter</th>      # Left fixed column
        #     <th scope="col">19.08.2025 10:12</th>             # Date/Time Slots
        #     <th scope="col">18.08.2025 16:23</th>
        #     <th scope="col">16.08.2025 08:33</th>
        #     <th scope="col">13.08.2025 12:44</th>
        #     <th scope="col">11.08.2025 09:55</th>
        #     <th scope="col">08.08.2025 14:06</th>
        #     <th scope="col">04.08.2025 13:17</th>
        #     <th scope="col">04.08.2025 13:17</th>
        #     <th scope="col">04.08.2025 13:17</th>
        #     <th scope="col">04.08.2025 13:17</th>
        #     <th scope="col">04.08.2025 13:17</th>
        #     <th scope="col">04.08.2025 13:17</th>
        #     <th scope="col">04.08.2025 13:17</th>
        #   </tr>
        # </thead>
        header_row = TR(TH("Parameter", _scope="col", _class="fixed"))
        for x in range(12):
            header_row.append(TH(x, _scope="col"))
        header = THEAD(header_row)
        obstable.append(header)

        # TODO render body
        # <tbody>
        #   <tr>
        #     <th class="fixed">
        #         <div class="obs-cat">Serum-Na+</div>          # Parameter
        #         <div class="obs-rrg">137-145 mmol/l</div>     # Normal Range + Unit
        #     </th>
        #     <td>132</td>                                      # Slot value
        #     <td></td>
        #     <td></td>
        #     <td>141</td>
        #     <td></td>
        #     <td></td>
        #     <td></td>
        #     <td></td>
        #     <td></td>
        #     <td></td>
        #     <td></td>
        #     <td></td>
        #     <td></td>
        #   </tr>
        # </tbody>
        body = TBODY()
        for i in range(24):
            value_row = TR(TH(DIV("Serum-Na+", _class="obstable-param"),
                            DIV("137-145 mmol/l", _class="obstable-range"),
                            _class="fixed",
                            ))
            for x in range(12):
                value_row.append(TD("%s-%s" % (i, x)))
            body.append(value_row)
        obstable.append(body)

        # TODO render footer (Repeat from Header)
        # <tfoot>
        #   <tr>
        #     <th class="fixed">Footer 1</th>
        #     <td>Footer 2</td>
        #     <td>Footer 3</td>
        #     <td>Footer 4</td>
        #     <td>Footer 5</td>
        #     <td>Footer 6</td>
        #     <td>Footer 7</td>
        #     <td>Footer 8</td>
        #     <td>Footer 7</td>
        #     <td>Footer 8</td>
        #     <td>Footer 7</td>
        #     <td>Footer 8</td>
        #     <td>Footer 7</td>
        #     <td>Footer 8</td>
        #   </tr>
        # </tfoot>
        footer_row = TR(TH("Parameter", _scope="col", _class="fixed"))
        for x in range(12):
            footer_row.append(TH(x, _scope="col"))
        footer = TFOOT(footer_row)
        obstable.append(footer)


        container = DIV(obstable,
                        _class = "obstable-scroll",
                        _id = "%s-scroll" % widget_id,
                        )
        return container

    # -------------------------------------------------------------------------
    @staticmethod
    def inject_script(widget_id, options):
        # TODO docstring

        # TODO implement
        pass

# END =========================================================================
