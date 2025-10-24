"""
    TimePlot Report

    Copyright: 2013-2022 (c) Sahana Software Foundation

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

__all__ = ("TimePlot",
           )

import json
import sys

from gluon import current
from gluon.storage import Storage
from gluon.html import DIV, FORM, INPUT, LABEL, SPAN, TAG, XML
from gluon.validators import IS_IN_SET
from gluon.sqlhtml import OptionsWidget, SQLFORM

from ..tools import JSONSEPARATORS, TimeSeries, TimeSeriesFact, get_crud_string

from .base import CRUDMethod
from .report import S3Report, S3ReportForm

# =============================================================================
class TimePlot(CRUDMethod):
    """ RESTful method for time plot reports """

    # -------------------------------------------------------------------------
    def apply_method(self, r, **attr):
        """
            Page-render entry point for REST interface.

            Args:
                r: the CRUDRequest instance
                attr: controller attributes for the request
        """

        output = None

        if r.http == "GET":
            output = self.timeplot(r, **attr)
        else:
            r.error(405, current.ERROR.BAD_METHOD)

        return output

    # -------------------------------------------------------------------------
    def widget(self, r, method=None, widget_id=None, visible=True, **attr):
        """
            Widget-render entry point for S3Summary.

            Args:
                r: the CRUDRequest
                method: the widget method
                widget_id: the widget ID
                visible: whether the widget is initially visible
                attr: controller attributes
        """

        # Get the target resource
        resource = self.get_target(r)

        # Read the relevant GET vars
        report_vars, get_vars = self.get_options(r, resource)

        # Parse event timestamp option
        timestamp = get_vars.get("timestamp")
        event_start, event_end = self.parse_timestamp(timestamp)

        # Parse fact option
        fact = get_vars.get("fact")
        try:
            facts = TimeSeriesFact.parse(fact)
        except SyntaxError:
            r.error(400, sys.exc_info()[1])
        baseline = get_vars.get("baseline")

        # Parse grouping axes
        rows = get_vars.get("rows")
        cols = get_vars.get("cols")

        # Parse event frame parameters
        start = get_vars.get("start")
        end = get_vars.get("end")
        slots = get_vars.get("slots")

        if visible:
            # Create time series
            ts = TimeSeries(resource,
                            start = start,
                            end = end,
                            slots = slots,
                            event_start = event_start,
                            event_end = event_end,
                            rows = rows,
                            cols = cols,
                            facts = facts,
                            baseline = baseline,
                            # @todo: add title
                            #title = title,
                            )

            # Extract aggregated results as JSON-serializable dict
            data = ts.as_dict()
        else:
            data = None

        # Render output
        if r.representation in ("html", "iframe"):

            ajax_vars = Storage(r.get_vars)
            ajax_vars.update(get_vars)
            filter_url = r.url(method = "",
                               representation = "",
                               vars = ajax_vars.fromkeys((k for k in ajax_vars
                                                          if k not in report_vars)))
            ajaxurl = attr.get("ajaxurl", r.url(method = "timeplot",
                                                representation = "json",
                                                vars = ajax_vars,
                                                ))
            output = TimePlotForm(resource).html(data,
                                                 get_vars = get_vars,
                                                 filter_widgets = None,
                                                 ajaxurl = ajaxurl,
                                                 filter_url = filter_url,
                                                 widget_id = widget_id,
                                                 )

            # Detect and store theme-specific inner layout
            view = self._view(r, "timeplot.html")

            # Render inner layout (outer page layout is set by S3Summary)
            output["title"] = None
            output = XML(current.response.render(view, output))

        else:
            r.error(415, current.ERROR.BAD_FORMAT)

        return output

    # -------------------------------------------------------------------------
    def timeplot(self, r, **attr):
        """
            Time plot report page

            Args:
                r: the CRUDRequest instance
                attr: controller attributes for the request
        """

        output = {}

        # Get the target resource
        resource = self.get_target(r)
        tablename = resource.tablename
        get_config = resource.get_config

        # Apply filter defaults (before rendering the data!)
        show_filter_form = False
        if r.representation in ("html", "iframe"):
            filter_widgets = get_config("filter_widgets", None)
            if filter_widgets and not self.hide_filter:
                from ..filters import FilterForm
                show_filter_form = True
                FilterForm.apply_filter_defaults(r, resource)

        # Read the relevant GET vars
        report_vars, get_vars = self.get_options(r, resource)

        # Parse event timestamp option
        timestamp = get_vars.get("timestamp")
        event_start, event_end = self.parse_timestamp(timestamp)

        # Parse fact option
        fact = get_vars.get("fact")
        try:
            facts = TimeSeriesFact.parse(fact)
        except SyntaxError:
            r.error(400, sys.exc_info()[1])
        baseline = get_vars.get("baseline")

        # Parse grouping axes
        rows = get_vars.get("rows")
        cols = get_vars.get("cols")

        # Parse event frame parameters
        start, end, slots = TimePlotForm.get_timeframe(get_vars)

        # Create time series
        ts = TimeSeries(resource,
                        start = start,
                        end = end,
                        slots = slots,
                        event_start = event_start,
                        event_end = event_end,
                        rows = rows,
                        cols = cols,
                        facts = facts,
                        baseline = baseline,
                        # @todo: add title
                        #title = title,
                        )

        # Extract aggregated results as JSON-serializable dict
        data = ts.as_dict()

        # Widget ID
        widget_id = "timeplot"

        # Render output
        if r.representation in ("html", "iframe"):
            # Page load

            output["title"] = get_crud_string(tablename, "title_report")

            # Filter widgets
            if show_filter_form:
                advanced = False
                for widget in filter_widgets:
                    if "hidden" in widget.opts and widget.opts.hidden:
                        advanced = get_config("report_advanced", True)
                        break
                filter_formstyle = get_config("filter_formstyle", None)
                filter_form = FilterForm(filter_widgets,
                                           formstyle = filter_formstyle,
                                           advanced = advanced,
                                           submit = False,
                                           _class = "filter-form",
                                           _id = "%s-filter-form" % widget_id,
                                           )
                fresource = current.s3db.resource(tablename)
                alias = resource.alias if resource.parent else None
                filter_widgets = filter_form.fields(fresource,
                                                    r.get_vars,
                                                    alias = alias,
                                                    )
            else:
                # Render as empty string to avoid the exception in the view
                filter_widgets = None

            ajax_vars = Storage(r.get_vars)
            ajax_vars.update(get_vars)
            ajax_vars.pop("time", None)
            filter_url = r.url(method="",
                               representation="",
                               vars=ajax_vars.fromkeys((k for k in ajax_vars
                                                        if k not in report_vars)))
            ajaxurl = attr.get("ajaxurl", r.url(method = "timeplot",
                                                representation = "json",
                                                vars = ajax_vars,
                                                ))

            output = TimePlotForm(resource).html(data,
                                                 get_vars = get_vars,
                                                 filter_widgets = filter_widgets,
                                                 ajaxurl = ajaxurl,
                                                 filter_url = filter_url,
                                                 widget_id = widget_id,
                                                 )

            output["title"] = get_crud_string(tablename, "title_report")
            output["report_type"] = "timeplot"

            # Detect and store theme-specific inner layout
            self._view(r, "timeplot.html")

            # View
            response = current.response
            response.view = self._view(r, "report.html")

        elif r.representation == "json":
            # Ajax load
            output = json.dumps(data, separators=JSONSEPARATORS)

        else:
            r.error(415, current.ERROR.BAD_FORMAT)

        return output

    # -------------------------------------------------------------------------
    def get_target(self, r):
        """
            Identify the target resource

            Args:
                r: the CRUDRequest
        """

        # Fallback
        resource = self.resource

        # Read URL parameter
        alias = r.get_vars.get("component")

        # Identify target component
        if alias and alias not in (resource.alias, "~"):
            component = resource.components.get(alias)
            if component:
                resource = component

        return resource

    # -------------------------------------------------------------------------
    @staticmethod
    def get_options(r, resource):
        """
            Read the relevant GET vars for the timeplot

            Args:
                r: the CRUDRequest
                resource: the target CRUDResource
        """

        # Extract the relevant GET vars
        report_vars = ("timestamp",
                       "start",
                       "end",
                       "slots",
                       "fact",
                       "baseline",
                       "rows",
                       "cols",
                       )
        get_vars = {k: v for k, v in r.get_vars.items() if k in report_vars}

        # Fall back to report options defaults
        report_options = resource.get_config("timeplot_options", {})
        defaults = report_options.get("defaults", {})
        if not any(k in get_vars for k in report_vars):
            get_vars = defaults
        else:
            # Optional URL args always fall back to config:
            optional = ("timestamp",
                        "fact",
                        "baseline",
                        "rows",
                        "cols",
                        )
            for opt in optional:
                if opt not in get_vars and opt in defaults:
                    get_vars[opt] = defaults[opt]

        return report_vars, get_vars

    # -------------------------------------------------------------------------
    @staticmethod
    def parse_timestamp(timestamp):
        """
            Parse timestamp expression

            Args:
                timestamp: the timestamp expression
        """

        if timestamp:
            fields = timestamp.split(",")
            if len(fields) > 1:
                start = fields[0].strip()
                end = fields[1].strip()
            else:
                start = fields[0].strip()
                end = None
        else:
            start = None
            end = None

        return start, end

# =============================================================================
class TimePlotForm(S3ReportForm):
    """ Helper class to render a report form """

    # -------------------------------------------------------------------------
    def html(self, data, *,
             filter_widgets = None,
             get_vars = None,
             ajaxurl = None,
             filter_url = None,
             filter_form = None,
             filter_tab = None,
             widget_id = None,
             ):
        """
            Render the form for the report

            Args:
                get_vars: the GET vars if the request (as dict)
                widget_id: the HTML element base ID for the widgets
        """

        T = current.T

        # Filter options
        if filter_widgets is not None:
            filter_options = self._fieldset(T("Filter Options"),
                                            filter_widgets,
                                            _id="%s-filters" % widget_id,
                                            _class="filter-form")
        else:
            filter_options = ""

        # Report options
        report_options = self.report_options(get_vars = get_vars,
                                             widget_id = widget_id)

        hidden = {"tp-data": json.dumps(data, separators=JSONSEPARATORS)}

        # @todo: chart title
        empty = T("No data available")

        # Report form submit element
        resource = self.resource
        submit = resource.get_config("report_submit", True)
        if submit:
            _class = "tp-submit"
            if submit is True:
                label = T("Update Report")
            elif isinstance(submit, (list, tuple)):
                label = submit[0]
                _class = "%s %s" % (submit[1], _class)
            else:
                label = submit
            submit = TAG[""](
                        INPUT(_type="button",
                              _value=label,
                              _class=_class))
        else:
            submit = ""

        # @todo: use view template (see S3ReportForm)
        form = FORM(filter_options,
                    report_options,
                    submit,
                    hidden = hidden,
                    _class = "tp-form",
                    _id = "%s-tp-form" % widget_id,
                    )

        # View variables
        output = {"form": form,
                  "empty": empty,
                  "widget_id": widget_id,
                  }

        # D3/Timeplot scripts (injected so that they are available for summary)
        S3Report.inject_d3()
        s3 = current.response.s3
        scripts = s3.scripts
        appname = current.request.application
        if s3.debug:
            script = "/%s/static/scripts/S3/s3.ui.timeplot.js" % appname
            if script not in scripts:
                scripts.append(script)
        else:
            script = "/%s/static/scripts/S3/s3.ui.timeplot.min.js" % appname
            if script not in scripts:
                scripts.append(script)

        # Script to attach the timeplot widget
        settings = current.deployment_settings
        options = {
            "ajaxURL": ajaxurl,
            "autoSubmit": settings.get_ui_report_auto_submit(),
            "emptyMessage": str(empty),
            "labelGrouped": str(T("Grouped##barchart")),
            "labelStacked": str(T("Stacked##barchart")),
            }
        script = """$("#%(widget_id)s").timeplot(%(options)s)""" % \
                    {"widget_id": widget_id,
                     "options": json.dumps(options),
                    }
        s3.jquery_ready.append(script)

        return output

    # -------------------------------------------------------------------------
    def report_options(self, get_vars=None, widget_id="timeplot"):
        """
            Render the widgets for the report options form

            Args:
                get_vars: the GET vars if the request (as dict)
                widget_id: the HTML element base ID for the widgets
        """

        T = current.T

        timeplot_options = self.resource.get_config("timeplot_options")

        label = lambda l, **attr: LABEL("%s:" % l, **attr)
        selectors = []

        # Fact options
        selector = self.fact_options(options = timeplot_options,
                                     get_vars = get_vars,
                                     widget_id = widget_id,
                                     )
        selectors.append(("%s-fact__row" % widget_id,
                          label(T("Report of"), _for=selector["_id"]),
                          selector,
                          None,
                          ))

        # Timestamp options
        selector = self.timestamp_options(options = timeplot_options,
                                          get_vars = get_vars,
                                          widget_id = widget_id,
                                          )
        selectors.append(("%s-timestamp__row" % widget_id,
                          label(T("Mode"), _for=selector["_id"]),
                          selector,
                          None,
                          ))

        # Time frame and slots options
        tf_selector = self.time_options(options = timeplot_options,
                                        get_vars = get_vars,
                                        widget_id = widget_id,
                                        )
        ts_selector = self.slot_options(options = timeplot_options,
                                        get_vars = get_vars,
                                        widget_id = widget_id,
                                        )
        if ts_selector:
            selector = DIV(tf_selector,
                           label(T("Intervals"), _for=ts_selector["_id"]),
                           ts_selector,
                           _class = "tp-time-options",
                           )
        else:
            selector = tf_selector
        selectors.append(("%s-time__row" % widget_id,
                          label(T("Time Frame"), _for=tf_selector["_id"]),
                          selector,
                          None,
                          ))

        # Build field set
        formstyle = current.deployment_settings.get_ui_filter_formstyle()
        if not callable(formstyle):
            formstyle = SQLFORM.formstyles[formstyle]

        selectors = formstyle(FORM(), selectors)

        return self._fieldset(T("Report Options"),
                              selectors,
                              _id = "%s-options" % widget_id,
                              _class = "report-options",
                              )

    # -------------------------------------------------------------------------
    def fact_options(self, options=None, get_vars=None, widget_id=None):
        """
            Generate a selector for fact options (multiple allowed)

            Args:
                options: the timeplot options for the target table
                get_vars: the current GET vars with selected options
                          or defaults, respectively
                widget_id: the main widget DOM ID

            Returns:
                a multi-select widget
        """

        T = current.T
        table = self.resource.table

        default = "count(%s)" % (table._id.name)

        # Options
        if options and "facts" in options:
            opts = options["facts"]
        else:
            from ..model import META_FIELD_NAMES
            opts = [(T("Number of Records"), default)]
            for fn in table.fields:
                if fn in META_FIELD_NAMES:
                    continue
                field = table[fn]
                if not field.readable:
                    continue
                requires = field.requires
                if field.type == "integer" and not hasattr(requires, "options") or \
                    field.type == "double":
                    label = T("%(field)s (total)") % {"field": field.label}
                    opts.append((label, "sum(%s)" % fn))

        # Currently selected option(s)
        value = []
        if get_vars:
            selected = get_vars.get("fact")
            if not isinstance(selected, list):
                selected = [selected]
            for item in selected:
                if isinstance(item, (tuple, list)):
                    value.append(item[-1])
                elif isinstance(item, str):
                    value.extend(item.split(","))
        if not value:
            value = default

        # Dummy field
        widget_opts = [(opt, label) for (label, opt) in opts]
        dummy_field = Storage(name = "timeplot-fact",
                              requires = IS_IN_SET(widget_opts, zero=None),
                              )

        # Widget
        from ..ui import S3MultiSelectWidget
        return S3MultiSelectWidget()(dummy_field,
                                     value,
                                     _id = "%s-fact" % widget_id,
                                     _name = "fact",
                                     _class = "tp-fact",
                                     )

    # -------------------------------------------------------------------------
    def timestamp_options(self, options=None, get_vars=None, widget_id=None):
        """
            Generate a selector for timestamp options

            Args:
                options: the timeplot options for the target table
                get_vars: the current GET vars with selected options
                          or defaults, respectively
                widget_id: the main widget DOM ID

            Returns:
                an options widget
        """

        T = current.T
        table = self.resource.table

        # Options
        if options and "timestamp" in options:
            opts = options["timestamp"]
        else:
            start, end = TimeSeries.default_timestamp(table)
            if not start:
                return None
            separate = (start, end) if end else (start, start)
            opts = [(T("per interval"), ",".join(separate)),
                    (T("cumulative"), start),
                    ]

        if not opts:
            return SPAN(T("no options available"),
                        _class = "no-options-available",
                        )

        # Currently selected option
        value = get_vars.get("timestamp") if get_vars else None
        if not value:
            start, end = TimeSeries.default_timestamp(table)
            if start and end:
                value = "%s,%s" % (start, end)
            elif start:
                value = start

        # Dummy field
        widget_opts = [(opt, label) for (label, opt) in opts]
        dummy_field = Storage(name = "timestamp",
                              requires = IS_IN_SET(widget_opts, zero=None),
                              )

        # Widget
        return OptionsWidget.widget(dummy_field,
                                    value,
                                    _id = "%s-timestamp" % widget_id,
                                    _name = "timestamp",
                                    _class = "tp-timestamp",
                                    )

    # -------------------------------------------------------------------------
    @classmethod
    def time_options(cls, options=None, get_vars=None, widget_id=None):
        """
            Generate a selector for the report time frame

            Args:
                options: the timeplot options for the target table
                get_vars: the current GET vars with selected options
                          or defaults, respectively
                widget_id: the main widget DOM ID

            Returns:
                an options widget
        """

        T = current.T

        # Time options:
        if options and "time" in options:
            opts = options["time"]
        else:
            # (label, start, end, slots)
            # - if start is specified, end is relative to start
            # - otherwise, end is relative to now
            # - start "" means the date of the earliest recorded event
            # - end "" means now
            opts = ((T("All up to now"), "", "", ""),
                    (T("Last Year"), "<-1 year", "+1 year", "months"),
                    (T("This Year"), "<-0 years", "", "months"),
                    (T("Last Month"), "<-1 month", "+1 month", "days"),
                    (T("This Month"), "<-0 months", "", "days"),
                    (T("Last Week"), "<-1 week", "+1 week", "days"),
                    (T("This Week"), "<-0 weeks", "", "days"),
                    #(T("Past 12 Months"), "-12months", "", "months"),
                    #(T("Past 6 Months"), "-6months", "", "weeks"),
                    #(T("Past 3 Months"), "-3months", "", "weeks"),
                    #(T("Past Month"), "-1month", "", "days"),
                    #(T("Past Week"), "-1week", "", "days"),
                    #("All/+1 Month", "", "+1month", ""),
                    #("All/+2 Month", "", "+2month", ""),
                    #("-6/+3 Months", "-6months", "+9months", "months"),
                    #("-3/+1 Months", "-3months", "+4months", "weeks"),
                    #("-4/+2 Weeks", "-4weeks", "+6weeks", "weeks"),
                    #("-2/+1 Weeks", "-2weeks", "+3weeks", "days"),
                    )

        widget_opts = []
        for opt in opts:
            label, start, end, slots = opt
            widget_opts.append(("|".join((start, end, slots)), T(label)))

        # Currently selected value
        if get_vars:
            start, end, slots = cls.get_timeframe(get_vars)
        else:
            start = end = slots = ""
        value = "|".join((start, end, slots))

        # Dummy field
        dummy_field = Storage(name = "time",
                              requires = IS_IN_SET(widget_opts, zero=None),
                              )

        # Widget
        return OptionsWidget.widget(dummy_field,
                                    value,
                                    _id = "%s-time" % widget_id,
                                    _name = "time",
                                    _class = "tp-time",
                                    )

    # -------------------------------------------------------------------------
    @staticmethod
    def slot_options(options=None, get_vars=None, widget_id=None):
        """
            Generates a selector for the time slots

            Args:
                options: the timeplot options for the target table
                get_vars: the current GET vars with selected options
                          or defaults, respectively
                widget_id: the main widget DOM ID

            Returns:
                an options widget, or None if there is only
                the "auto" option available
        """

        T = current.T

        automatic = (T("Automatic"), "auto")

        if options and "slots" in options:
            opts = options["slots"]
        else:
            # Do not render by default
            return None
            #opts = (automatic,
                    #(T("Days"), "days"),
                    #(T("Weeks"), "weeks"),
                    #(T("2 Weeks"), "2 weeks"),
                    #(T("Months"), "months"),
                    #(T("3 Months"), "3 months"),
                    #)

        if not any(opt[1] == "auto" for opt in opts):
            explicit = opts
            opts = [automatic]
            opts.extend(explicit)
        if len(opts) == 1:
            return None

        # Currently selected value
        value = get_vars.get("slots") if get_vars else None
        if not value:
            value = "auto"

        # Dummy field
        widget_opts = [(opt, label) for (label, opt) in opts]
        dummy_field = Storage(name = "slots",
                              requires = IS_IN_SET(widget_opts, zero=None),
                              )
        # Widget
        return OptionsWidget.widget(dummy_field,
                                    value,
                                    _id = "%s-slots" % widget_id,
                                    _name = "slots",
                                    _class = "tp-slots",
                                    )

    # -------------------------------------------------------------------------
    @staticmethod
    def get_timeframe(get_vars):
        """
            Get the report time frame from GET vars; can be encoded either
            as a query parameter "time" with start|end|slots (i.e. |-separated),
            or as separate start, end and slots parameters.

            Args:
                get_vars: the GET vars

            Returns:
                tuple (start, end, slots)
        """

        timeframe = get_vars.get("time")
        if timeframe:
            if isinstance(timeframe, str):
                timeframe = timeframe.split("|")
            start, end, slots = (list(timeframe[-3:]) + ["", "", ""])[:3]
        else:
            start = get_vars.get("start", "")
            end = get_vars.get("end", "")
            slots = get_vars.get("slots", "")

        return start, end, slots

# END =========================================================================
