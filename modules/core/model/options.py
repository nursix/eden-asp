"""
    Option sets and configuration tools

    Copyright: 2022-2023 (c) Sahana Software Foundation

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
__all__ = ("WorkflowOptions",
           )

from gluon import current, DIV, I

from ..tools import S3PriorityRepresent

# =============================================================================
class WorkflowOptions:
    """
        Option sets for workflow statuses or status reasons
    """

    icons = {"red": "fa fa-exclamation-triangle",
             "amber": "fa fa-hourglass",
             "green": "fa fa-check",
             "grey": "fa fa-minus-circle",
             "blue": "fa fa-circle-o",
             }

    css_classes = {"red": "workflow-red",
                   "amber": "workflow-amber",
                   "green": "workflow-green",
                   "grey": "workflow-grey",
                   "blue": "workflow-blue",
                   }

    # -------------------------------------------------------------------------
    def __init__(self, *theset, selectable=None, represent="workflow", none=None):
        """
            Args:
                theset: tuple|list of tuples specifying all options,
                        (value, label) or (value, label, color)
                selectable: tuple|list of manually selectable values
                represent: how to represent values, either:
                            - "workflow" for icon + red|amber|green
                            - "status"   to use S3PriorityRepresent
                none: treat None-value like this value
        """

        self.theset = theset
        self._represent = represent
        self.none = none

        self._colors = None

        self._keys = [o[0] for o in theset]
        if selectable:
            self._selectable = [k for k in self._keys if k in selectable]
        else:
            self._selectable = self._keys

    # -------------------------------------------------------------------------
    def selectable(self, values=False, current_value=None):
        """
            Produces a list of selectable options for use with IS_IN_SET

            Args:
                values: which values to use
                        - True for the manually selectable options as configured
                        - tuple of values to override the manually selectable options
                        - False for all possible options
                current_value: the current value of the field, to be included
                               in the selectable options
        """

        if values is False:
            selectable = self._keys
        elif values is True:
            selectable = self._selectable
        elif isinstance(values, (tuple, list, set)):
            selectable = list(values)
        else:
            selectable = []

        if current_value and current_value not in selectable:
            selectable = [current_value] + selectable

        return [o for o in self.labels() if o[0] in selectable]

    # -------------------------------------------------------------------------
    @property
    def colors(self):
        """
            The option "colors", for representation

            Returns:
                a dict {value: color}
        """

        colors = self._colors
        if not colors:
            colors = self._colors = {}
            for opt in self.theset:
                if len(opt) > 2:
                    colors[opt[0]] = opt[2]
                else:
                    colors[opt[0]] = None
        return colors

    # -------------------------------------------------------------------------
    def labels(self):
        """
            The (localized) option labels, for representation

            Returns:
                a list of tuples [(value, T(label)), ...]
        """

        T = current.T

        return [(o[0], T(o[1])) for o in self.theset]

    # -------------------------------------------------------------------------
    @property
    def represent(self):
        """
            The representation method for this option set

            Returns:
                the representation function
        """

        represent = self._represent
        if not callable(represent):
            if represent == "workflow":
                represent = self.represent_workflow()
            elif represent == "status":
                represent = self.represent_status()
            else:
                represent = None
            self._represent = represent
        return represent

    # -------------------------------------------------------------------------
    def represent_workflow(self):
        """
            Representation as workflow element (icon + red|amber|green)

            Returns:
                the representation function
        """

        none = self.none

        colors = self.colors
        icons = self.icons
        css_classes = self.css_classes

        def represent(value, row=None):

            if value is None and none:
                value = none

            label = DIV(_class="workflow-options")

            color = colors.get(value)
            if color:
                icon = icons.get(color)
                if icon:
                    label.append(I(_class=icon))
                css_class = css_classes.get(color)
                if css_class:
                    label.add_class(css_class)

            label.append(dict(self.labels()).get(value, "-"))

            return label

        return represent

    # -------------------------------------------------------------------------
    def represent_status(self):
        """
            Representation using S3PriorityRepresent

            Returns:
                a S3PriorityRepresent instance
        """

        inst = S3PriorityRepresent({},
                                   classes = self.colors,
                                   none = self.none,
                                   )

        def represent(value, row=None):
            inst.options = dict(self.labels())
            return inst(value, row=row)

        return represent

# END =========================================================================
