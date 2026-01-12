"""
    Select-or-add widgets for foreign key fields

    Copyright: 2009-2023 (c) Sahana Software Foundation

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

__all__ = ("LocationSelector",
           "PersonSelector",
           )

import json
import sys

from uuid import uuid4

from gluon import current, \
                  A, BUTTON, DIV, INPUT, LABEL, OPTION, SELECT, SPAN, TABLE, TAG, TD, TR, \
                  IS_EMPTY_OR, IS_EMAIL
from gluon.sqlhtml import FormWidget, StringWidget, OptionsWidget
from gluon.storage import Storage

from s3dal import filter_fields

from .icons import ICON
from ..tools import IS_LOCATION, IS_PHONE_NUMBER_MULTI, IS_PHONE_NUMBER_SINGLE, \
                    JSONERRORS, JSONSEPARATORS, StringTemplateParser, \
                    s3_required_label, s3_fullname, s3_str, s3_validate

# =============================================================================
class LocationSelector(FormWidget):
    """
        Form widget to select a location_id that can also
        create/update the location

        Differences to the original S3LocationSelectorWidget:
        * Allows selection of either an Lx or creation of a new Point
          within the lowest Lx level
        * Uses dropdowns not autocompletes
        * Selection of lower Lx levels only happens when higher-level
          have been done

        Implementation Notes:
        * Performance: Create JSON for the hierarchy, along with bboxes for
                       the map zoom - loaded progressively rather than all as
                       one big download
        h = {id : {'n' : name,
                   'l' : level,
                   'f' : parent
                   }}

        Limitations TODO:
        * Doesn't allow creation of new Lx Locations
        * Doesn't support manual entry of LatLons
        * Doesn't allow selection of existing specific Locations
        * Doesn't support variable Levels by Country
        * Doesn't handle renamed fields (like Merge form)
        * Use in an InlineComponent with multiple=False needs completing:
            - Validation errors cause issues
            - Needs more testing
        * Should support use in an InlineComponent with multiple=True
        * Option to allow having Lx mandatory *except* when a specific location
          is defined (e.g. Polygon spanning 2 countries)
    """

    keys = ("L0", "L1", "L2", "L3", "L4", "L5",
            "address", "postcode", "lat", "lon", "wkt", "specific", "id", "radius")

    def __init__(self,
                 levels = None,
                 required_levels = None,
                 hide_lx = True,
                 reverse_lx = False,
                 filter_lx = None,
                 show_address = False,
                 address_required = None,
                 show_postcode = None,
                 postcode_required = None,
                 postcode_to_address = None,
                 show_latlon = None,
                 latlon_mode = "decimal",
                 latlon_mode_toggle = True,
                 show_map = None,
                 open_map_on_load = False,
                 feature_required = False,
                 lines = False,
                 points = True,
                 polygons = False,
                 circles = False,
                 catalog_layers = False,
                 min_bbox = None,
                 labels = True,
                 placeholders = False,
                 error_message = None,
                 represent = None,
                 prevent_duplicate_addresses = False,
                 outside = None,
                 ):
        """
            Args:
                levels: list or tuple of hierarchy levels (names) to expose,
                        in order (e.g. ("L0", "L1", "L2"))
                        or False to disable completely
                required_levels: list or tuple of required hierarchy levels (if empty,
                                 only the highest selectable Lx will be required)
                hide_lx: hide Lx selectors until higher level has been selected
                reverse_lx: render Lx selectors in the order usually used by
                            street Addresses (lowest level first), and below the
                            address line
                filter_lx: filter the top-level selectable Lx by name (tuple of names),
                           i.e. restrict to regional
                show_address: show a field for street address. If the parameter is set
                              to a string then this is used as the label.
                address_required: address field is mandatory
                show_postcode: show a field for postcode
                postcode_required: postcode field is mandatory
                postcode_to_address: service to use to lookup a list of addresses from
                                     the postcode
                show_latlon: show fields for manual Lat/Lon input
                latlon_mode: (initial) lat/lon input mode ("decimal" or "dms")
                latlon_mode_toggle: allow user to toggle lat/lon input mode
                show_map: show a map to select specific points
                open_map_on_load: show map on load
                feature_required: map feature is required
                lines: use a line draw tool
                points: use a point draw tool
                polygons: use a polygon draw tool
                circles: use a circle draw tool
                catalog_layers: display catalogue layers or just the default base layer
                min_bbox: minimum BBOX in map selector, used to determine automatic
                          zoom level for single-point locations
                labels: show labels on inputs
                placeholders: show placeholder text in inputs
                error_message: default error message for server-side validation
                represent: an S3Represent instance that can represent non-DB rows
                prevent_duplicate_addresses: do a check for duplicate addresses & prevent
                                             creation of record if a dupe is found
        """

        settings = current.deployment_settings

        self._initlx = True
        self._levels = levels
        self._required_levels = required_levels
        self._filter_lx = filter_lx
        self._load_levels = None

        self.hide_lx = hide_lx
        self.reverse_lx = reverse_lx
        self.show_address = show_address
        self.address_required = address_required
        self.show_postcode = show_postcode
        self.postcode_required = postcode_required
        self.postcode_to_address = postcode_to_address or \
                                   settings.get_gis_postcode_to_address()
        self.prevent_duplicate_addresses = prevent_duplicate_addresses

        if show_latlon is None:
            show_latlon = settings.get_gis_latlon_selector()
        self.show_latlon = show_latlon
        self.latlon_mode = latlon_mode
        if show_latlon:
            # @todo: latlon_toggle_mode should default to a deployment setting
            self.latlon_mode_toggle = latlon_mode_toggle
        else:
            self.latlon_mode_toggle = False

        if feature_required:
            show_map = True
            if not any((points, lines, polygons, circles)):
                points = True
            if lines or polygons or circles:
                required = "wkt" if not points else "any"
            else:
                required = "latlon"
            self.feature_required = required
        else:
            self.feature_required = None
        if show_map is None:
            show_map = settings.get_gis_map_selector()
        self.show_map = show_map
        self.open_map_on_load = show_map and open_map_on_load

        self.lines = lines
        self.points = points
        self.polygons = polygons
        self.circles = circles

        self.catalog_layers = catalog_layers

        self.min_bbox = min_bbox or settings.get_gis_bbox_min_size()

        self.labels = labels
        self.placeholders = placeholders

        self.error_message = error_message
        self._represent = represent

        self.field = Storage() # validate in inline forms doesn't go through call() 1st

    # -------------------------------------------------------------------------
    @property
    def levels(self):
        """ Lx-levels to expose as dropdowns """

        levels = self._levels
        if self._initlx:
            lx = []
            if levels is False:
                levels = []
            elif not levels:
                # Which levels of Hierarchy are we using?
                levels = current.gis.get_relevant_hierarchy_levels()
                if levels is None:
                    levels = []
            if not isinstance(levels, (tuple, list)):
                levels = [levels]
            for level in levels:
                if level not in lx:
                    lx.append(level)
            for level in self.required_levels:
                if level not in lx:
                    lx.append(level)
            levels = self._levels = lx
            self._initlx = False
        return levels

    # -------------------------------------------------------------------------
    @property
    def required_levels(self):
        """ Lx-levels to treat as required """

        levels = self._required_levels
        if self._initlx:
            if levels is None:
                levels = set()
            elif not isinstance(levels, (list, tuple)):
                levels = [levels]
            self._required_levels = levels
        return levels

    # -------------------------------------------------------------------------
    @property
    def load_levels(self):
        """
            Lx-levels to load from the database = all levels down to the
            lowest exposed level (L0=highest, L5=lowest)
        """

        load_levels = self._load_levels

        if load_levels is None:
            load_levels = ("L0", "L1", "L2", "L3", "L4", "L5")
            while load_levels:
                if load_levels[-1] in self.levels:
                    break
                else:
                    load_levels = load_levels[:-1]
            self._load_levels = load_levels

        return load_levels

    # -------------------------------------------------------------------------
    @property
    def mobile(self):
        """
            Mobile widget settings

            TODO Expose configuration options
        """

        widget = {"type": "location",
                  }

        return widget

    # -------------------------------------------------------------------------
    def __call__(self, field, value, **attributes):
        """
            Widget renderer

            Args:
                field: the Field
                value: the current value(s)
                attr: additional HTML attributes for the widget
        """

        # Environment
        T = current.T
        db = current.db

        s3db = current.s3db

        request = current.request
        s3 = current.response.s3

        self.field = field

        # Is the location input required?
        requires = field.requires
        if requires:
            required = not hasattr(requires, "other")
        else:
            required = False

        # Don't use this widget/validator in appadmin
        if request.controller == "appadmin":
            attr = FormWidget._attributes(field, {}, **attributes)
            if required:
                requires = IS_LOCATION()
            else:
                requires = IS_EMPTY_OR(IS_LOCATION())
            return TAG[""](INPUT(**attr), requires=requires)

        # Settings
        settings = current.deployment_settings
        countries = settings.get_gis_countries()

        # Read the currently active GIS config
        gis = current.gis
        config = gis.get_config()

        # Parse the current value
        values = self.parse(value)
        values_get = values.get
        location_id = values_get("id")

        # Determine the default location and bounds
        gtable = s3db.gis_location

        default = field.default
        default_bounds = None

        if not default:
            # Check for a default location in the active gis_config
            default = config.default_location_id

        if not default:
            # Fall back to default country (if only one)
            if len(countries) == 1:
                ttable = s3db.gis_location_tag
                query = (ttable.tag == "ISO2") & \
                        (ttable.value == countries[0]) & \
                        (ttable.location_id == gtable.id)
                country = db(query).select(gtable.id,
                                           gtable.lat_min,
                                           gtable.lon_min,
                                           gtable.lat_max,
                                           gtable.lon_max,
                                           cache = s3db.cache,
                                           limitby = (0, 1)
                                           ).first()
                try:
                    default = country.id
                    default_bounds = [country.lon_min,
                                      country.lat_min,
                                      country.lon_max,
                                      country.lat_max,
                                      ]
                except AttributeError:
                    error = "Default country data not in database (incorrect prepop setting?)"
                    current.log.critical(error)
                    if s3.debug:
                        raise RuntimeError(error)

        if not location_id and list(values.keys()) == ["id"]:
            location_id = values["id"] = default

        # Update the values dict from the database
        values = self.extract(location_id, values=values)

        # The lowest level we have a value for, but no selector exposed
        levels = self.levels
        load_levels = self.load_levels
        lowest_lx = None
        for level in load_levels[::-1]:
            if level not in levels and values_get(level):
                lowest_lx = level
                break

        # Field name for ID construction
        fieldname = attributes.get("_name")
        if not fieldname:
            fieldname = str(field).replace(".", "_")

        # Load initial Hierarchy Labels (for Lx dropdowns)
        labels, labels_compact = self._labels(levels,
                                              country = values_get("L0"),
                                              )

        # Load initial Hierarchy Locations (to populate Lx dropdowns)
        location_dict = self._locations(levels,
                                        values,
                                        default_bounds = default_bounds,
                                        filter_lx = self._filter_lx,
                                        lowest_lx = lowest_lx,
                                        config = config,
                                        )

        # Render visual components
        components = {}
        manual_input = self._input

        # Street Address INPUT
        show_address = self.show_address
        if show_address:
            address = values_get("address")
            if show_address is True:
                label = gtable.addr_street.label
            else:
                label = show_address
            components["address"] = manual_input(fieldname,
                                                 "address",
                                                 address,
                                                 label,
                                                 hidden = not address,
                                                 required = self.address_required,
                                                 )

        # Postcode INPUT
        show_postcode = self.show_postcode
        if show_postcode is None:
            # Use global setting
            show_postcode = settings.get_gis_postcode_selector()
        if show_postcode:
            postcode = values_get("postcode")
            postcode_component = manual_input(fieldname,
                                              "postcode",
                                              postcode,
                                              settings.get_ui_label_postcode(),
                                              hidden = not postcode,
                                              required = self.postcode_required,
                                              )
            if self.postcode_to_address:
                # Generate form key
                formkey = uuid4().hex

                # Store form key in session
                session = current.session
                keyname = "_formkey[geocode]"
                session[keyname] = session.get(keyname, [])[-9:] + [formkey]

                # Store form key in form
                postcode_component[1]["data"] = {"k": formkey}

                # Add controls
                input_id = "%s_postcode_to_address" % fieldname
                widget = DIV(A(T("Enter address manually"),
                               _id = input_id,
                               ))
                component = ("",    # label
                             widget,
                             input_id,
                             True, # hidden
                             )
                components["postcode_to_address"] = component

            components["postcode"] = postcode_component

        # Lat/Lon INPUTs
        lat = values_get("lat")
        lon = values_get("lon")
        if self.show_latlon:
            hidden = not lat and not lon
            components["lat"] = manual_input(fieldname,
                                             "lat",
                                             lat,
                                             T("Latitude"),
                                             hidden = hidden,
                                             _class = "double",
                                             )
            components["lon"] = manual_input(fieldname,
                                             "lon",
                                             lon,
                                             T("Longitude"),
                                             hidden = hidden,
                                             _class = "double",
                                             )

        # Lx Dropdowns
        multiselect = settings.get_ui_multiselect_widget()
        lx_rows = self._lx_selectors(field,
                                     fieldname,
                                     levels,
                                     labels,
                                     multiselect = multiselect,
                                     required = required,
                                     )
        components.update(lx_rows)

        # Lat/Lon Input Mode Toggle
        if self.latlon_mode_toggle:
            latlon_labels = {"decimal": T("Use decimal"),
                             "dms": T("Use deg, min, sec"),
                             }
            if self.latlon_mode == "dms":
                latlon_label = latlon_labels["decimal"]
            else:
                latlon_label = latlon_labels["dms"]
            toggle_id = fieldname + "_latlon_toggle"
            components["latlon_toggle"] = ("",
                                           A(latlon_label,
                                             _id = toggle_id,
                                             _class = "action-lnk",
                                             ),
                                           toggle_id,
                                           False,
                                           )
        else:
            latlon_labels = None

        # Already loaded? (to prevent duplicate JS injection)
        location_selector_loaded = s3.gis.location_selector_loaded

        # Action labels i18n
        if not location_selector_loaded:
            global_append = s3.js_global.append
            global_append('''i18n.select="%s"''' % T("Select"))
            if multiselect == "search":
                global_append('''i18n.search="%s"''' % T("Search"))
            if latlon_labels:
                global_append('''i18n.latlon_mode='''
                              '''{decimal:"%(decimal)s",dms:"%(dms)s"}''' %
                              latlon_labels)
                global_append('''i18n.latlon_error='''
                              '''{lat:"%s",lon:"%s",min:"%s",sec:"%s",format:"%s"}''' %
                              (T("Latitude must be -90..90"),
                               T("Longitude must be -180..180"),
                               T("Minutes must be 0..59"),
                               T("Seconds must be 0..59"),
                               T("Unrecognized format"),
                               ))

        # If we need to show the map since we have an existing lat/lon/wkt
        # then we need to launch the client-side JS as a callback to the
        # MapJS loader
        wkt = values_get("wkt")
        radius = values_get("radius")
        if lat is not None or lon is not None or wkt is not None:
            use_callback = True
        else:
            use_callback = False

        # Widget JS options
        options = {"hideLx": self.hide_lx,
                   "reverseLx": self.reverse_lx,
                   "locations": location_dict,
                   "labels": labels_compact,
                   "showLabels": self.labels,
                   "featureRequired": self.feature_required,
                   "latlonMode": self.latlon_mode,
                   "latlonModeToggle": self.latlon_mode_toggle,
                   }
        if self.min_bbox:
            options["minBBOX"] = self.min_bbox
        if self.open_map_on_load:
            options["openMapOnLoad"] = True
        script = '''$('#%s').selectLocation(%s)''' % \
                 (fieldname, json.dumps(options, separators=JSONSEPARATORS))

        show_map = self.show_map
        callback = None
        if show_map and use_callback:
            callback = script
        elif not location_selector_loaded or \
             not location_selector_loaded.get(fieldname):
            s3.jquery_ready.append(script)

        # Inject LocationSelector JS
        if s3.debug:
            script = "s3.ui.locationselector.js"
        else:
            script = "s3.ui.locationselector.min.js"
        script = "/%s/static/scripts/S3/%s" % (request.application, script)

        scripts = s3.scripts
        if script not in scripts:
            scripts.append(script)

        # Should we use the Geocoder?
        geocoder = config.geocoder and show_address

        # Inject map
        if show_map:
            map_icon = self._map(field,
                                 fieldname,
                                 lat,
                                 lon,
                                 wkt,
                                 radius,
                                 callback = callback,
                                 geocoder = geocoder,
                                 tablename = field.tablename,
                                 )
        else:
            map_icon = None

        # LocationSelector is now loaded! (=prevent duplicate JS injection)
        if location_selector_loaded:
            location_selector_loaded[fieldname] = True
        else:
            s3.gis.location_selector_loaded = {fieldname: True}

        # Real input
        classes = ["location-selector"]
        if fieldname.startswith("sub_"):
            is_inline = True
            classes.append("inline-locationselector-widget")
        else:
            is_inline = False
        real_input = self.inputfield(field, values, classes, **attributes)

        # The overall layout of the components
        visible_components = self._layout(components,
                                          map_icon = map_icon,
                                          inline = is_inline,
                                          )

        return TAG[""](DIV(_class = "throbber"),
                       real_input,
                       visible_components,
                       )

    # -------------------------------------------------------------------------
    @staticmethod
    def _labels(levels, country=None):
        """
            Extract the hierarchy labels

            Args:
                levels: the exposed hierarchy levels
                country: the country (gis_location record ID) for which
                         to read the hierarchy labels

            Returns:
                tuple (labels, compact) where labels is for internal use
                with _lx_selectors, and compact the version ready for JSON
                output

            TODO Country-specific Translations of Labels
        """

        T = current.T
        table = current.s3db.gis_hierarchy

        fields = [table[level] for level in levels if level != "L0"]

        query = (table.uuid == "SITE_DEFAULT")
        if country:
            # Read both country-specific and default
            fields.append(table.uuid)
            query |= (table.location_id == country)
            limit = 2
        else:
            # Default only
            limit = 1

        rows = current.db(query).select(*fields, limitby=(0, limit))

        labels = {}
        compact = {}

        if "L0" in levels:
            labels["L0"] = current.messages.COUNTRY

        if country:
            for row in rows:
                if row.uuid == "SITE_DEFAULT":
                    d = compact["d"] = {}
                    for level in levels:
                        if level == "L0":
                            continue
                        d[int(level[1:])] = row[level]
                else:
                    d = compact[country] = {}
                    for level in levels:
                        if level == "L0":
                            continue
                        label = row[level]
                        label = s3_str(T(label)) if label else level
                        labels[level] = d[int(level[1:])] = label
        else:
            row = rows.first()
            d = compact["d"] = {}
            for level in levels:
                if level == "L0":
                    continue
                d[int(level[1:])] = s3_str(T(row[level]))

        return labels, compact

    # -------------------------------------------------------------------------
    @staticmethod
    def _locations(levels,
                   values,
                   default_bounds = None,
                   filter_lx = None,
                   lowest_lx = None,
                   config = None,
                   ):
        """
            Build initial location dict (to populate Lx dropdowns)

            Args:
                levels: the exposed levels
                values: the current values
                default_bounds: the default bounds (if already known, e.g.
                                single-country deployment)
                filter_lx: filter the top-level Lx by names
                lowest_lx: the lowest un-selectable Lx level (to determine
                           default bounds if not passed in)
                config: the current GIS config

            Returns:
                dict of location data, ready for JSON output

            TODO DRY with controllers/gis.py ldata()
        """

        db = current.db
        s3db = current.s3db
        settings = current.deployment_settings

        values_get = values.get
        L0 = values_get("L0")
        L1 = values_get("L1")
        L2 = values_get("L2")
        L3 = values_get("L3")
        L4 = values_get("L4")
        #L5 = values_get("L5")

        # Read all visible levels
        # NB (level != None) is to handle Missing Levels
        gtable = s3db.gis_location

        if isinstance(filter_lx, (tuple, list, set)):
            top_level = min(levels)
        else:
            filter_lx = top_level = None

        # @todo: DRY this:
        if "L0" in levels:
            query = (gtable.level == "L0")
            countries = settings.get_gis_countries()
            if len(countries):
                ttable = s3db.gis_location_tag
                query &= ((ttable.tag == "ISO2") & \
                          (ttable.value.belongs(countries)) & \
                          (ttable.location_id == gtable.id))
            if filter_lx and top_level == "L0":
                query &= gtable.name.belongs(filter_lx)
            if L0 and "L1" in levels:
                query |= (gtable.level != None) & \
                         (gtable.parent == L0)
            if L1 and "L2" in levels:
                query |= (gtable.level != None) & \
                         (gtable.parent == L1)
            if L2 and "L3" in levels:
                query |= (gtable.level != None) & \
                         (gtable.parent == L2)
            if L3 and "L4" in levels:
                query |= (gtable.level != None) & \
                         (gtable.parent == L3)
            if L4 and "L5" in levels:
                query |= (gtable.level != None) & \
                         (gtable.parent == L4)
        elif L0 and "L1" in levels:
            query = (gtable.level != None) & \
                    (gtable.parent == L0)
            if filter_lx and top_level == "L1":
                query &= gtable.name.belongs(filter_lx)
            if L1 and "L2" in levels:
                query |= (gtable.level != None) & \
                         (gtable.parent == L1)
            if L2 and "L3" in levels:
                query |= (gtable.level != None) & \
                         (gtable.parent == L2)
            if L3 and "L4" in levels:
                query |= (gtable.level != None) & \
                         (gtable.parent == L3)
            if L4 and "L5" in levels:
                query |= (gtable.level != None) & \
                         (gtable.parent == L4)
        elif L1 and "L2" in levels:
            query = (gtable.level != None) & \
                    (gtable.parent == L1)
            if filter_lx and top_level == "L2":
                query &= gtable.name.belongs(filter_lx)
            if L2 and "L3" in levels:
                query |= (gtable.level != None) & \
                         (gtable.parent == L2)
            if L3 and "L4" in levels:
                query |= (gtable.level != None) & \
                         (gtable.parent == L3)
            if L4 and "L5" in levels:
                query |= (gtable.level != None) & \
                         (gtable.parent == L4)
        elif L2 and "L3" in levels:
            query = (gtable.level != None) & \
                    (gtable.parent == L2)
            if filter_lx and top_level == "L3":
                query &= gtable.name.belongs(filter_lx)
            if L3 and "L4" in levels:
                query |= (gtable.level != None) & \
                         (gtable.parent == L3)
            if L4 and "L5" in levels:
                query |= (gtable.level != None) & \
                         (gtable.parent == L4)
        elif L3 and "L4" in levels:
            query = (gtable.level != None) & \
                    (gtable.parent == L3)
            if filter_lx and top_level == "L4":
                query &= gtable.name.belongs(filter_lx)
            if L4 and "L5" in levels:
                query |= (gtable.level != None) & \
                         (gtable.parent == L4)
        elif L4 and "L5" in levels:
            query = (gtable.level != None) & \
                    (gtable.parent == L4)
            if filter_lx and top_level == "L5":
                query &= gtable.name.belongs(filter_lx)
        else:
            query = None

        # Translate options using gis_location_name?
        language = current.session.s3.language
        if language in ("en", "en-gb"):
            # We assume that Location names default to the English version
            translate = False
        else:
            translate = settings.get_L10n_translate_gis_location()

        if query is None:
            locations = []
            if levels != []:
                # Misconfigured (e.g. no default for a hidden Lx level)
                current.log.warning("LocationSelector: no default for hidden Lx level?")
        else:
            query &= (gtable.deleted == False) & \
                     (gtable.end_date == None)
            fields = [gtable.id,
                      gtable.name,
                      gtable.level,
                      gtable.parent,
                      gtable.inherited,
                      gtable.lat_min,
                      gtable.lon_min,
                      gtable.lat_max,
                      gtable.lon_max,
                      ]

            if translate:
                ntable = s3db.gis_location_name
                fields.append(ntable.name_l10n)
                left = ntable.on((ntable.deleted == False) & \
                                 (ntable.language == language) & \
                                 (ntable.location_id == gtable.id))
            else:
                left = None
            locations = db(query).select(*fields, left=left)

        location_dict = {}
        if default_bounds:

            # Only L0s get set before here
            location_dict["d"] = {"id": L0,
                                  "b": default_bounds,
                                  }
            location_dict[L0] = {"b": default_bounds,
                                 "l": 0,
                                 }

        elif lowest_lx:
            # What is the lowest-level un-selectable Lx?
            lx = values_get(lowest_lx)
            record = db(gtable.id == lx).select(gtable.lat_min,
                                                gtable.lon_min,
                                                gtable.lat_max,
                                                gtable.lon_max,
                                                cache = s3db.cache,
                                                limitby = (0, 1)
                                                ).first()
            try:
                bounds = [record.lon_min,
                          record.lat_min,
                          record.lon_max,
                          record.lat_max
                          ]
            except:
                # Record not found!
                raise ValueError

            location_dict["d"] = {"id": lx,
                                  "b": bounds,
                                  }
            location_dict[lx] = {"b": bounds,
                                 "l": int(lowest_lx[1:]),
                                 }
        else:
            fallback = None
            default_location = config.default_location_id
            if default_location:
                query = (gtable.id == default_location)
                record = db(query).select(gtable.level,
                                          gtable.lat_min,
                                          gtable.lon_min,
                                          gtable.lat_max,
                                          gtable.lon_max,
                                          cache = s3db.cache,
                                          limitby = (0, 1)
                                          ).first()
                if record and record.level:
                    bounds = [record.lon_min,
                              record.lat_min,
                              record.lon_max,
                              record.lat_max,
                              ]
                    if any(bounds):
                        fallback = {"id": default_location, "b": bounds}
            if fallback is None:
                fallback = {"b": [config.lon_min,
                                  config.lat_min,
                                  config.lon_max,
                                  config.lat_max,
                                  ]
                            }
            location_dict["d"] = fallback

        if translate:
            for location in locations:
                l = location["gis_location"]
                name = location["gis_location_name.name_l10n"] or l.name
                data = {"n": name,
                        "l": int(l.level[1]),
                        }
                if l.parent:
                    data["f"] = int(l.parent)
                if not l.inherited:
                    data["b"] = [l.lon_min,
                                 l.lat_min,
                                 l.lon_max,
                                 l.lat_max,
                                 ]
                location_dict[int(l.id)] = data
        else:
            for l in locations:
                level = l.level
                if level:
                    level = int(level[1])
                else:
                    current.log.warning("LocationSelector",
                                        "Location Hierarchy not setup properly")
                    continue
                data = {"n": l.name,
                        "l": level,
                        }
                if l.parent:
                    data["f"] = int(l.parent)
                if not l.inherited:
                    data["b"] = [l.lon_min,
                                 l.lat_min,
                                 l.lon_max,
                                 l.lat_max,
                                 ]
                location_dict[int(l.id)] = data

        return location_dict

    # -------------------------------------------------------------------------
    @staticmethod
    def _layout(components,
                map_icon = None,
                formstyle = None,
                inline = False):
        """
            Overall layout for visible components

            Args:
                components: the components as dict
                            {name: (label, widget, id, hidden)}
                map_icon: the map icon
                formstyle: the formstyle (falls back to CRUD formstyle)
        """

        if formstyle is None:
            formstyle = current.response.s3.crud.formstyle

        # Test the formstyle
        row = formstyle("test", "test", "test", "test")
        if isinstance(row, tuple):
            # Formstyle with separate row for label
            # (e.g. old default Eden formstyle)
            tuple_rows = True
            table_style = inline and row[0].tag == "tr"
        else:
            # Formstyle with just a single row (e.g. Foundation)
            tuple_rows = False
            table_style = False

        selectors = DIV() if not table_style else TABLE()
        sappend = selectors.append
        for name in ("L0", "L1", "L2", "L3", "L4", "L5"):
            if name in components:
                label, widget, input_id, hidden = components[name]
                formrow = formstyle("%s__row" % input_id,
                                    label,
                                    widget,
                                    "",
                                    hidden = hidden,
                                    )
                if tuple_rows:
                    sappend(formrow[0])
                    sappend(formrow[1])
                else:
                    sappend(formrow)

        inputs = TAG[""]() if not table_style else TABLE()
        for name in ("address",
                     "postcode",
                     "postcode_to_address",
                     "lat",
                     "lon",
                     "latlon_toggle",
                     ):
            if name in components:
                label, widget, input_id, hidden = components[name]
                formrow = formstyle("%s__row" % input_id,
                                    label,
                                    widget,
                                    "",
                                    hidden = hidden,
                                    )
                if tuple_rows:
                    inputs.append(formrow[0])
                    inputs.append(formrow[1])
                else:
                    inputs.append(formrow)

        output = TAG[""](selectors, inputs)
        if map_icon:
            output.append(map_icon)
        return output

    # -------------------------------------------------------------------------
    def _lx_selectors(self,
                      field,
                      fieldname,
                      levels,
                      labels,
                      multiselect = False,
                      required = False):
        """
            Render the Lx-dropdowns

            Args:
                field: the field (to construct the HTML Names)
                fieldname: the fieldname (to construct the HTML IDs)
                levels: tuple of levels in order, like ("L0", "L1", ...)
                labels: the labels for the hierarchy levels as dict {level:label}
                multiselect: Use multiselect-dropdowns (specify "search" to
                             make the dropdowns searchable)
                required: whether selection is required

            Returns:
                a dict of components {name: (label, widget, id, hidden)}
        """

        # Use multiselect widget?
        if multiselect == "search":
            _class = "lx-select multiselect search"
        elif multiselect:
            _class = "lx-select multiselect"
        else:
            _class = None

        # Initialize output
        selectors = {}

        # 1st level is always hidden until populated
        hidden = True

        _fieldname = fieldname.split("%s_" % field.tablename)[1]

        #T = current.T
        required_levels = self.required_levels
        for level in levels:

            _name = "%s_%s" % (_fieldname, level)

            _id = "%s_%s" % (fieldname, level)

            label = labels.get(level, level)

            # Widget (options to be populated client-side)
            #placeholder = T("Select %(level)s") % {"level": label}
            placeholder = ""
            widget = SELECT(OPTION(placeholder, _value=""),
                            _name = _name,
                            _id = _id,
                            _class = _class,
                            )

            # Mark as required?
            if required or level in required_levels:
                widget.add_class("required")
                label = s3_required_label(label)

                if required and ("L%s" % (int(level[1:]) - 1)) not in levels:
                    # This is the highest level, treat subsequent levels
                    # as optional unless they are explicitly configured
                    # as required
                    required = False

            # Throbber
            throbber = DIV(_id = "%s__throbber" % _id,
                           _class = "throbber hide",
                           )

            if self.labels:
                label = LABEL(label,
                              _for = _id,
                              )
            else:
                label = ""
            selectors[level] = (label, TAG[""](widget, throbber), _id, hidden)

            # Follow hide-setting for all subsequent levels (default: True),
            # client-side JS will open when-needed
            hidden = self.hide_lx

        return selectors

    # -------------------------------------------------------------------------
    def _input(self,
               fieldname,
               name,
               value,
               label,
               hidden = False,
               required = False,
               _class = "string"):
        """
            Render a text input (e.g. address or postcode field)

            Args:
                fieldname: the field name (for ID construction)
                name: the name for the input field
                value: the initial value for the input
                label: the label for the input
                hidden: render hidden
                required: mark as required

            Returns:
                a tuple (label, widget, id, hidden)
        """

        input_id = "%s_%s" % (fieldname, name)

        if label and self.labels:
            if required:
                label = s3_required_label(label)
            else:
                label = "%s:" % label
            _label = LABEL(label,
                           _for = input_id,
                           )
        else:
            _label = ""
        if label and self.placeholders:
            _placeholder = label
        else:
            _placeholder = None

        widget = INPUT(_name = name,
                       _id = input_id,
                       _class = _class,
                       _placeholder = _placeholder,
                       value = s3_str(value),
                       )
        if required:
            # Enable client-side validation:
            widget.add_class("required")

        return (_label, widget, input_id, hidden)

    # -------------------------------------------------------------------------
    def _map(self,
             field,
             fieldname,
             lat,
             lon,
             wkt,
             radius,
             callback = None,
             geocoder = False,
             tablename = None):
        """
            Initialize the map

            Args:
                field: the field
                fieldname: the field name (to construct HTML IDs)
                lat: the Latitude of the current point location
                lon: the Longitude of the current point location
                wkt: the WKT
                radius: the radius of the location
                callback: the script to initialize the widget, if to be
                          initialized as callback of the MapJS loader
                geocoder: use a geocoder
                tablename: tablename to determine the controller/function
                           for custom colorpicker style

            Returns:
                the HTML components for the map (including the map icon row)

            TODO: handle multiple LocationSelectors in 1 page
                 (=> multiple callbacks, as well as the need to migrate options
                 from globals to a parameter)
        """

        lines = self.lines
        points = self.points
        polygons = self.polygons
        circles = self.circles

        # Toolbar options
        add_points_active = add_polygon_active = add_line_active = add_circle_active = False
        if points and lines:
            # Allow selection between drawing a point or a line
            toolbar = True
            if wkt:
                if not polygons or wkt.startswith("LINE"):
                    add_line_active = True
                elif polygons:
                    add_polygon_active = True
                else:
                    add_line_active = True
            else:
                add_points_active = True
        elif points and polygons:
            # Allow selection between drawing a point or a polygon
            toolbar = True
            if wkt:
                add_polygon_active = True
            else:
                add_points_active = True
        elif points and circles:
            # Allow selection between drawing a point or a circle
            toolbar = True
            if wkt:
                add_circle_active = True
            else:
                add_points_active = True
        elif points:
            # No toolbar needed => always drawing points
            toolbar = False
            add_points_active = True
        elif lines and polygons:
            # Allow selection between drawing a line or a polygon
            toolbar = True
            if wkt:
                if wkt.startswith("LINE"):
                    add_line_active = True
                else:
                    add_polygon_active = True
            else:
                add_polygon_active = True
        elif lines and circles:
            # Allow selection between drawing a line or a circle
            toolbar = True
            if wkt:
                if wkt.startswith("LINE"):
                    add_line_active = True
                else:
                    add_circle_active = True
            else:
                add_circle_active = True
        elif lines:
            # No toolbar needed => always drawing lines
            toolbar = False
            add_line_active = True
        elif polygons and circles:
            # Allow selection between drawing a polygon or a circle
            toolbar = True
            if wkt:
                if radius is not None:
                    add_circle_active = True
                else:
                    add_polygon_active = True
            else:
                add_polygon_active = True
        elif polygons:
            # No toolbar needed => always drawing polygons
            toolbar = False
            add_polygon_active = True
        elif circles:
            # No toolbar needed => always drawing circles
            toolbar = False
            add_circle_active = True
        else:
            # No Valid options!
            raise SyntaxError

        s3 = current.response.s3
        settings = current.deployment_settings

        # Create the map
        _map = current.gis.show_map(id = "location_selector_%s" % fieldname,
                                    collapsed = True,
                                    height = settings.get_gis_map_selector_height(),
                                    width = settings.get_gis_map_selector_width(),
                                    add_feature = points,
                                    add_feature_active = add_points_active,
                                    add_line = lines,
                                    add_line_active = add_line_active,
                                    add_polygon = polygons,
                                    add_polygon_active = add_polygon_active,
                                    add_circle = circles,
                                    add_circle_active = add_circle_active,
                                    catalogue_layers = self.catalog_layers,
                                    toolbar = toolbar,
                                    # Hide controls from toolbar
                                    clear_layers = False,
                                    nav = False,
                                    print_control = False,
                                    area = False,
                                    zoomWheelEnabled = False,
                                    # Don't use normal callback (since we postpone rendering Map until DIV unhidden)
                                    # but use our one if we need to display a map by default
                                    callback = callback,
                                    )

        # Inject map icon labels
        if polygons or lines:
            show_map_add = settings.get_ui_label_locationselector_map_polygon_add()
            show_map_view = settings.get_ui_label_locationselector_map_polygon_view()
            if wkt is not None:
                label = show_map_view
            else:
                label = show_map_add
        else:
            show_map_add = settings.get_ui_label_locationselector_map_point_add()
            show_map_view = settings.get_ui_label_locationselector_map_point_view()
            if lat is not None or lon is not None:
                label = show_map_view
            else:
                label = show_map_add

        T = current.T
        global_append = s3.js_global.append
        location_selector_loaded = s3.gis.location_selector_loaded

        if not location_selector_loaded:
            global_append('''i18n.show_map_add="%s"
i18n.show_map_view="%s"
i18n.hide_map="%s"
i18n.map_feature_required="%s"''' % (show_map_add,
                                     show_map_view,
                                     T("Hide Map"),
                                     T("Map Input Required"),
                                     ))

        # Generate map icon
        icon_id = "%s_map_icon" % fieldname
        row_id = "%s_map_icon__row" % fieldname
        _formstyle = settings.ui.formstyle
        if not _formstyle or \
           isinstance(_formstyle, str) and "foundation" in _formstyle:
            # Default: Foundation
            # Need to add custom classes to core HTML markup
            map_icon = DIV(DIV(BUTTON(ICON("globe"),
                                      SPAN(label),
                                      _type = "button", # defaults to 'submit' otherwise!
                                      _id = icon_id,
                                      _class = "btn tiny button gis_loc_select_btn",
                                      ),
                               _class = "small-12 columns",
                               ),
                           _id = row_id,
                           _class = "form-row row hide",
                           )
        else:
            # Old default
            map_icon = DIV(DIV(BUTTON(ICON("globe"),
                                      SPAN(label),
                                      _type = "button", # defaults to 'submit' otherwise!
                                      _id = icon_id,
                                      _class = "btn gis_loc_select_btn",
                                      ),
                               _class = "w2p_fl",
                               ),
                           _id = row_id,
                           _class = "hide",
                           )

        # Geocoder?
        if geocoder:
            if not location_selector_loaded:
                global_append('''i18n.address_mapped="%s"
i18n.address_not_mapped="%s"
i18n.location_found="%s"
i18n.location_not_found="%s"''' % (T("Address Mapped"),
                                   T("Address NOT Mapped"),
                                   T("Address Found"),
                                   T("Address NOT Found"),
                                   ))

            # Generate form key
            formkey = uuid4().hex

            # Store form key in session
            session = current.session
            keyname = "_formkey[geocode]"
            session[keyname] = session.get(keyname, [])[-9:] + [formkey]

            map_icon.append(DIV(DIV(_class = "throbber hide"),
                                DIV(_class = "geocode_success hide"),
                                DIV(_class = "geocode_fail hide"),
                                BUTTON(T("Geocode"),
                                       _class = "hide",
                                       _type = "button", # defaults to 'submit' otherwise!
                                       data = {"k": formkey},
                                       ),
                                _class = "controls geocode",
                                _id = "%s_geocode" % fieldname,
                                ))

        # Inject map directly behind map icon
        map_icon.append(_map)

        return map_icon

    # -------------------------------------------------------------------------
    def inputfield(self, field, values, classes, **attributes):
        """
            Generate the (hidden) input field. Should be used in __call__.

            Args:
                field: the Field
                values: the parsed value (as dict)
                classes: standard HTML classes
                attributes: the widget attributes as passed in to the widget

            Returns:
                the INPUT field
        """

        if isinstance(classes, (tuple, list)):
            _class = " ".join(classes)
        else:
            _class = classes

        requires = self.postprocess

        fieldname = str(field).replace(".", "_")
        if fieldname.startswith("sub_"):
            from ..tools import SKIP_VALIDATION
            requires = SKIP_VALIDATION(requires)

        defaults = {"requires": requires,
                    "_type": "hidden",
                    "_class": _class,
                    }
        attr = FormWidget._attributes(field, defaults, **attributes)

        return INPUT(_value = self.serialize(values), **attr)

    # -------------------------------------------------------------------------
    def extract(self, record_id, values=None):
        """
            Load record data from database and update the values dict

            Args:
                record_id: the location record ID
                values: the values dict
        """

        # Initialize the values dict
        if values is None:
            values = {}
        for key in ("L0", "L1", "L2", "L3", "L4", "L5", "specific", "parent", "radius"):
            if key not in values:
                values[key] = None

        values["id"] = record_id

        if not record_id:
            return values

        db = current.db
        table = current.s3db.gis_location

        levels = self.load_levels

        values_get = values.get
        lat = values_get("lat")
        lon = values_get("lon")
        wkt = values_get("wkt")
        radius = values_get("radius")
        address = values_get("address")
        postcode = values_get("postcode")

        # Load the record
        record = db(table.id == record_id).select(table.id,
                                                  table.path,
                                                  table.parent,
                                                  table.level,
                                                  table.gis_feature_type,
                                                  table.inherited,
                                                  table.lat,
                                                  table.lon,
                                                  table.wkt,
                                                  table.radius,
                                                  table.addr_street,
                                                  table.addr_postcode,
                                                  limitby = (0, 1)
                                                  ).first()
        if not record:
            raise ValueError

        level = record.level

        # Parse the path
        path = record.path
        if path is None:
            # Not updated yet? => do it now
            try:
                path = current.gis.update_location_tree({"id": record_id})
            except ValueError:
                pass
        path = [] if path is None else path.split("/")

        path_ok = True
        if level:
            # Lx location
            #values["level"] = level # Currently unused and not updated by s3.ui.locationselector.js
            values["specific"] = None

            if len(path) != (int(level[1:]) + 1):
                # We don't have a full path
                path_ok = False

        else:
            # Specific location
            values["parent"] = record.parent
            values["specific"] = record.id

            if len(path) < (len(levels) + 1):
                # We don't have a full path
                path_ok = False

            # Only use a specific Lat/Lon when they are not inherited
            if not record.inherited:
                if self.points:
                    if lat is None or lat == "":
                        if record.gis_feature_type == 1:
                            # Only use Lat for Points
                            lat = record.lat
                        else:
                            lat = None
                    if lon is None or lon == "":
                        if record.gis_feature_type == 1:
                            # Only use Lat for Points
                            lon = record.lon
                        else:
                            lon = None
                else:
                    lat = None
                    lon = None
                if self.lines or self.polygons or self.circles:
                    if not wkt:
                        if record.gis_feature_type != 1:
                            # Only use WKT for non-Points
                            wkt = record.wkt
                            if record.radius is not None:
                                radius = record.radius
                        else:
                            wkt = None
                else:
                    wkt = None
            if address is None:
                address = record.addr_street
            if postcode is None:
                postcode = record.addr_postcode

        # Path
        if path_ok:
            for level in levels:
                idx = int(level[1:])
                if len(path) > idx:
                    values[level] = int(path[idx])
        else:
            # Retrieve all records in the path to match them up to their Lx
            rows = db(table.id.belongs(path)).select(table.id, table.level)
            for row in rows:
                if row.level:
                    values[row.level] = row.id

        # Address data
        values["address"] = address
        values["postcode"] = postcode

        # Lat/Lon/WKT/Radius
        values["lat"] = lat
        values["lon"] = lon
        values["wkt"] = wkt
        values["radius"] = radius

        return values

    # -------------------------------------------------------------------------
    def serialize(self, values):
        """
            Serialize the values (as JSON string). Called from inputfield().

            Args:
                values: the values (as dict)

            Returns:
                the serialized values
        """

        return json.dumps(values, separators=JSONSEPARATORS)

    # -------------------------------------------------------------------------
    def parse(self, value):
        """
            Parse the form value into a dict. The value would be a record
            id if coming from the database, or a JSON string when coming
            from a form. Should be called from validate(), doesn't need to
            be re-implemented in subclass.

            Args:
                value: the value

            Returns:
                the parsed data as dict
        """

        record_id = None
        values = None

        if value:
            if isinstance(value, str):
                if value.isdigit():
                    record_id = int(value)
                else:
                    try:
                        values = json.loads(value)
                    except ValueError:
                        pass
            else:
                record_id = value
        else:
            record_id = None

        if values is None:
            values = {"id": record_id}

        return values
    # -------------------------------------------------------------------------
    def represent(self, value):
        """
            Representation of a new/updated location row (before DB commit).
                - this method is called during BasicCRUD.validate for inline
                  components

            Args:
                values: the values dict

            Returns:
                string representation for the values dict

            Note:
                Using a fake path here in order to prevent
                gis_LocationRepresent.represent_row() from running
                update_location_tree as that would change DB status which
                is an invalid action at this point (row not committed yet).
        """

        if not value:
            # No data
            return current.messages["NONE"]
        value_get = value.get
        if not any(value_get(key) for key in self.keys):
            # No data
            return current.messages["NONE"]

        lat = value_get("lat")
        lon = value_get("lon")
        wkt = value_get("wkt")
        #radius = value_get("radius")
        address = value_get("address")
        postcode = value_get("postcode")

        record = Storage(name = value_get("name"),
                         lat = lat,
                         lon = lon,
                         addr_street = address,
                         addr_postcode = postcode,
                         parent = value_get("parent"),
                         )

        # Is this a specific location?
        specific = value_get("specific")
        if specific:
            record_id = specific
        elif address or postcode or lat or lon or wkt:
            specific = True
            record_id = value_get("id")
        else:
            record_id = None
        if not record_id:
            record_id = 0
        record.id = record_id

        lx_ids = {}

        # Construct the path (must have a path to prevent update_location_tree)
        path = [str(record_id)]
        level = None
        append = None
        for l in range(5, -1, -1):
            lx = value_get("L%s" % l)
            if lx:
                if not level and not specific and l < 5:
                    level = l
                elif level and not record.parent:
                    record.parent = lx
                lx_ids[l] = lx
                if append is None:
                    append = path.append
            if append:
                append(str(lx))
        path.reverse()
        record.path = "/".join(path)

        # Determine the Lx level
        if specific or level is None:
            record.level = None
        else:
            record.level = "L%s" % level

        # Get the Lx names
        s3db = current.s3db
        ltable = s3db.gis_location

        if lx_ids:
            query = ltable.id.belongs(set(lx_ids.values()))
            limitby = (0, len(lx_ids))
            lx_names = current.db(query).select(ltable.id,
                                                ltable.name,
                                                limitby = limitby
                                                ).as_dict()
            for l in range(0, 6):
                if l in lx_ids:
                    lx_name = lx_names.get(lx_ids[l])["name"]
                else:
                    lx_name = None
                if not lx_name:
                    lx_name = ""
                record["L%s" % l] = lx_name
                if level == l:
                    record["name"] = lx_name

        # Call standard location represent
        represent = self._represent
        if represent is None:
            # Fall back to default
            represent = s3db.gis_location_id().represent

        if hasattr(represent, "alt_represent_row"):
            text = represent.alt_represent_row(record)
        else:
            text = represent(record)

        return s3_str(text)

    # -------------------------------------------------------------------------
    def validate(self, value, requires=None):
        """
            Parse and validate the input value, but don't create or update
            any location data

            Args:
                value: the value from the form
                requires: the field validator

            Returns:
                tuple (values, error) with values being the parsed
                value dict, and error any validation errors
        """

        values = self.parse(value)

        if not values:
            # No data
            if requires and not isinstance(requires, IS_EMPTY_OR):
                return values, current.T("Location data required")
            return values, None
        values_get = values.get
        if not any(values_get(key) for key in self.keys):
            # No data
            if requires and not isinstance(requires, IS_EMPTY_OR):
                return values, current.T("Location data required")
            return values, None

        errors = {}

        # Check for valid Lat/Lon/WKT/Radius (if any)
        lat = values_get("lat")
        if lat:
            try:
                lat = float(lat)
            except ValueError:
                errors["lat"] = current.T("Latitude is Invalid!")
        elif lat == "":
            lat = None

        lon = values_get("lon")
        if lon:
            try:
                lon = float(lon)
            except ValueError:
                errors["lon"] = current.T("Longitude is Invalid!")
        elif lon == "":
            lon = None

        wkt = values_get("wkt")
        if wkt:
            try:
                from shapely.wkt import loads as wkt_loads
                wkt_loads(wkt)
            except:
                errors["wkt"] = current.T("WKT is Invalid!")
        elif wkt == "":
            wkt = None

        radius = values_get("radius")
        if radius:
            try:
                radius = float(radius)
            except ValueError:
                errors["radius"] = current.T("Radius is Invalid!")
        elif radius == "":
            radius = None

        # Lx Required?
        required_levels = self._required_levels or []
        for level in required_levels:
            l = values_get(level)
            if not l:
                errors[level] = current.T("Location Hierarchy is Required!")
                break

        # Address Required?
        address = values_get("address")
        if self.address_required and not address:
            errors["address"] = current.T("Address is Required!")

        # Postcode Required?
        postcode = values_get("postcode")
        if self.postcode_required and not postcode:
            errors["postcode"] = current.T("Postcode is Required!")

        if errors:
            error = "\n".join(s3_str(errors[fn]) for fn in errors)
            return (values, error)

        table = current.s3db.gis_location
        feature = None
        onvalidation = None
        msg = self.error_message

        specific = values_get("specific")
        location_id = values_get("id")

        if specific and location_id and location_id != specific:
            # Reset from a specific location to an Lx
            # Currently not possible
            #   => widget always retains specific
            #   => must take care of orphaned specific locations otherwise
            lat = lon = wkt = radius = None
        else:
            # Read other details
            parent = values_get("parent")

        if parent or address or postcode or \
           wkt is not None or \
           lat is not None or \
           lon is not None or \
           radius is not None:

            # Specific location with details
            if specific:
                values["id"] = specific

                # Would-be update => get original record
                query = (table.id == specific) & \
                        (table.deleted == False) & \
                        (table.level == None) # specific Locations only
                location = current.db(query).select(table.lat,
                                                    table.lon,
                                                    table.wkt,
                                                    table.addr_street,
                                                    table.addr_postcode,
                                                    table.parent,
                                                    limitby = (0, 1)
                                                    ).first()
                if not location:
                    return (values, msg or current.T("Invalid Location!"))

                # Check for changes
                changed = False
                lparent = location.parent
                if parent and lparent:
                    if int(parent) != int(lparent):
                        changed = True
                elif parent or lparent:
                    changed = True
                if not changed:
                    laddress = location.addr_street
                    if (address or laddress) and \
                        address != laddress:
                        changed = True
                    else:
                        lpostcode = location.addr_postcode
                        if (postcode or lpostcode) and \
                            postcode != lpostcode:
                            changed = True
                        else:
                            lwkt = location.wkt
                            if (wkt or lwkt) and \
                               wkt != lwkt:
                                changed = True
                            else:
                                # Float comparisons need care
                                # - just check the 1st 5 decimal points, as
                                #   that's all we care about
                                llat = location.lat
                                if lat is not None and llat is not None:
                                    if round(lat, 5) != round(llat, 5):
                                        changed = True
                                elif lat is not None or llat is not None:
                                    changed = True
                                if not changed:
                                    llon = location.lon
                                    if lon is not None and llon is not None:
                                        if round(lon, 5) != round(llon, 5):
                                            changed = True
                                    elif lon is not None or llon is not None:
                                        changed = True

                if changed:
                    # Update specific location (indicated by id=specific)

                    # Permission to update?
                    if not current.auth.s3_has_permission("update", table,
                                                          record_id = specific):
                        return (values, current.auth.messages.access_denied)

                    # Schedule for onvalidation
                    feature = Storage(addr_street = address,
                                      addr_postcode = postcode,
                                      parent = parent,
                                      )
                    if any(detail is not None for detail in (lat, lon, wkt, radius)):
                        feature.lat = lat
                        feature.lon = lon
                        feature.wkt = wkt
                        feature.radius = radius
                        feature.inherited = False
                    onvalidation = current.s3db.gis_location_onvalidation

                else:
                    # No changes => skip (indicated by specific=0)
                    values["specific"] = 0

            else:
                # Create new specific location (indicate by id=0)
                values["id"] = 0

                # Skip Permission check if the field is JSON type (e.g. during Registration)
                if self.field.type != "json":
                    # Permission to create?
                    if not current.auth.s3_has_permission("create", table):
                        return (values, current.auth.messages.access_denied)

                # Check for duplicate address
                if self.prevent_duplicate_addresses:
                    query = (table.addr_street == address) & \
                            (table.parent == parent) & \
                            (table.deleted == False)
                    duplicate = current.db(query).select(table.id,
                                                         limitby = (0, 1)
                                                         ).first()
                    if duplicate:
                        return (values, current.T("Duplicate Address"))

                # Schedule for onvalidation
                feature = Storage(addr_street = address,
                                  addr_postcode = postcode,
                                  parent = parent,
                                  inherited = True,
                                  )
                if any(detail is not None for detail in (lat, lon, wkt, radius)):
                    feature.lat = lat
                    feature.lon = lon
                    feature.wkt = wkt
                    feature.radius = radius
                    feature.inherited = False
                onvalidation = current.s3db.gis_location_onvalidation

        elif specific:
            # Update specific location (indicated by id=specific)
            values["id"] = specific

            # Permission to update?
            if not current.auth.s3_has_permission("update", table,
                                                  record_id = specific):
                return (values, current.auth.messages.access_denied)

            # Make sure parent/address are properly removed
            values["parent"] = None
            values["address"] = None
            values["postcode"] = None

        else:
            # Lx location => check level
            ## @todo:
            #if not location_id:
                ## Get lowest selected Lx

            if location_id:
                levels = self.levels
                if levels == []:
                    # Widget set to levels=False
                    # No Street Address specified, so skip
                    return (None, None)
                query = (table.id == location_id) & \
                        (table.deleted == False)
                location = current.db(query).select(table.level,
                                                    limitby = (0, 1)
                                                    ).first()
                if not location:
                    return (values, msg or current.T("Invalid Location!"))

                level = location.level
                if level:
                    # Accept all levels above and including the lowest selectable level
                    for i in range(5, -1, -1):
                        if "L%s" % i in levels:
                            accepted_levels = set("L%s" % l for l in range(i, -1, -1))
                            break
                    if level not in accepted_levels:
                        return (values, msg or \
                                        current.T("Location is of incorrect level!"))
            # Do not update (indicate by specific = None)
            values["specific"] = None

        if feature and onvalidation:

            form = Storage(errors = errors,
                           vars = feature,
                           )
            try:
                # @todo: should use callback()
                onvalidation(form)
            except:
                if current.response.s3.debug:
                    raise
                else:
                    error = "onvalidation failed: %s (%s)" % (
                                onvalidation, sys.exc_info()[1])
                    current.log.error(error)
            if form.errors:
                errors = form.errors
                error = "\n".join(s3_str(errors[fn]) for fn in errors)
                return (values, error)
            elif feature:
                # gis_location_onvalidation adds/updates form vars (e.g.
                # gis_feature_type, the_geom) => must also update values
                values.update(feature)

        # Success
        return (values, None)

    # -------------------------------------------------------------------------
    def postprocess(self, value):
        """
            Takes the JSON from the real input and returns a location ID
            for it. Creates or updates the location if necessary.

            Args:
                value: the JSON from the real input

            Returns:
                tuple (location_id, error)

            TODO Audit
        """

        # Convert and validate
        values, error = self.validate(value)
        if values:
            values_get = values.get
            location_id = values.get("id")
        else:
            location_id = None

        # Return on validation error
        if error:
            # Make sure to return None to not override the field values
            # @todo: consider a custom INPUT subclass without
            #        _postprocessing() to prevent _value override
            #        after successful POST
            return None, error

        # Skip if location_id is None
        if location_id is None:
            return location_id, None

        if self.field.type == "json":
            # Save raw data suitable for later link to location_id or creation of new location
            # e.g. during Approval of a new Registration
            if location_id == 0:
                del values["id"]
            try:
                del values["specific"]
            except KeyError:
                pass
            try:
                del values["address"] # Duplicate of addr_street
            except KeyError:
                pass
            try:
                del values["postcode"] # Duplicate of addr_postcode
            except KeyError:
                pass
            return values, None

        db = current.db
        table = current.s3db.gis_location

        # Read the values
        lat = values_get("lat")
        lon = values_get("lon")
        lat_min = values_get("lat_min") # Values brought in by onvalidation
        lon_min = values_get("lon_min")
        lat_max = values_get("lat_max")
        lon_max = values_get("lon_max")
        wkt = values_get("wkt")
        radius = values_get("radius")
        the_geom = values_get("the_geom")
        address = values_get("address")
        postcode = values_get("postcode")
        parent = values_get("parent")
        gis_feature_type = values_get("gis_feature_type")

        if location_id == 0:
            # Create new location
            if wkt is not None or (lat is not None and lon is not None):
                inherited = False
            else:
                inherited = True

            feature = Storage(lat = lat,
                              lon = lon,
                              lat_min = lat_min,
                              lon_min = lon_min,
                              lat_max = lat_max,
                              lon_max = lon_max,
                              wkt = wkt,
                              radius = radius,
                              inherited = inherited,
                              addr_street = address,
                              addr_postcode = postcode,
                              parent = parent,
                              )

            # These could have been added during validate:
            if gis_feature_type:
                feature.gis_feature_type = gis_feature_type
            if the_geom:
                feature.the_geom = the_geom

            location_id = table.insert(**feature)
            feature.id = location_id
            current.gis.update_location_tree(feature)

        else:
            specific = values_get("specific")
            # specific is 0 to skip update (unchanged)
            # specific is None for Lx locations
            if specific and specific == location_id:
                # Update specific location
                feature = Storage(addr_street = address,
                                  addr_postcode = postcode,
                                  parent = parent,
                                  )
                if any(detail is not None for detail in (lat, lon, wkt, radius)):
                    feature.lat = lat
                    feature.lon = lon
                    feature.lat_min = lat_min
                    feature.lon_min = lon_min
                    feature.lat_max = lat_max
                    feature.lon_max = lon_max
                    feature.wkt = wkt
                    feature.radius = radius
                    feature.inherited = False

                # These could have been added during validate:
                if gis_feature_type:
                    feature.gis_feature_type = gis_feature_type
                if the_geom:
                    feature.the_geom = the_geom

                db(table.id == location_id).update(**feature)
                feature.id = location_id
                current.gis.update_location_tree(feature)

        return location_id, None

# =============================================================================
class PersonSelector(FormWidget):
    """
        Widget for person_id or human_resource_id fields that
        allows to either select an existing person/hrm (autocomplete), or to
        create a new person/hrm record inline

        Features:
        - embedded fields configurable in deployment settings
        - can use single name field (with on-submit name splitting),
          alternatively separate fields for first/middle/last names
        - can check for possible duplicates during data entry
        - fully encapsulated, works with regular validators (IS_ONE_OF)

        => Uses client-side script s3.ui.personselector.js (injected)
    """

    def __init__(self,
                 controller = None,
                 separate_name_fields = None,
                 first_name_only = None,
                 occupation = False,
                 pe_label = False,
                 pe_label_ignore = None,
                 nationality = False,
                 ):
        """
            Args:
                controller: controller for autocomplete
                separate_name_fields: use separate name fields, overrides
                                      deployment setting
                first_name_only: treat single name field entirely as
                                 first name (=do not split into name parts),
                                 overrides auto-detection, otherwise default
                                 for right-to-left written languages
                occupation: expose free-text occupation field
                pe_label: expose ID label field
                nationality: expose nationality field
        """

        self.controller = controller

        self.separate_name_fields = separate_name_fields
        self.first_name_only = first_name_only

        self.nationality = nationality
        self.occupation = occupation
        self.pe_label = pe_label

        if pe_label_ignore is None:
            self.pe_label_ignore = current.deployment_settings.get_pr_generate_pe_label()
        else:
            self.pe_label_ignore = pe_label_ignore

        self.hrm = False

        self.fields = {}
        self.labels = {}
        self.required = {}

        self.editable_fields = None

    # -------------------------------------------------------------------------
    def __call__(self, field, value, **attributes):
        """
            Widget builder

            Args:
                field: the Field
                value: the current or default value
                attributes: additional HTML attributes for the widget
        """

        T = current.T
        s3db = current.s3db

        # Attributes for the main input
        default = {"_type": "text",
                   "value": (value is not None and str(value)) or "",
                   }
        attr = StringWidget._attributes(field, default, **attributes)

        # Translations
        i18n = {"none_of_the_above": T("None of the above"),
                "loading": T("loading")
                }

        # Determine reference type
        reference_type = str(field.type)[10:]
        if reference_type == "pr_person":
            hrm = False
            fn = "person"
        elif reference_type == "hrm_human_resource":
            self.hrm = hrm = True
            fn = "human_resource"
        else:
            raise TypeError("PersonSelector: unsupported field type %s" % field.type)

        settings = current.deployment_settings

        # Field label overrides
        # (all other labels are looked up from the corresponding Field)
        labels = {"full_name": T(settings.get_pr_label_fullname()),
                  "email": T("Email"),
                  "mobile_phone": settings.get_ui_label_mobile_phone(),
                  "home_phone": T("Home Phone"),
                  }

        # Tag labels (...and tags, in order as configured)
        tags = []
        for label, tag in settings.get_pr_request_tags():
            if tag not in labels:
                labels[tag] = label
            tags.append(tag)

        self.labels = labels

        # Fields which, if enabled, are required
        # (all other fields are assumed to not be required)
        required = {"full_name": True,
                    "first_name": True,
                    "middle_name": settings.get_L10n_mandatory_middlename(),
                    "last_name": settings.get_L10n_mandatory_lastname(),
                    "date_of_birth": settings.get_pr_dob_required(),
                    "email": settings.get_hrm_email_required() if hrm else False,
                    }

        # Determine controller for autocomplete
        controller = self.controller
        if not controller:
            controller = current.request.controller
            if controller not in ("pr", "dvr", "hrm", "vol"):
                controller = "hrm" if hrm else "pr"

        # Fields to extract and fields in form
        ptable = s3db.pr_person
        dtable = s3db.pr_person_details

        fields = {}
        details = False

        trigger = None
        formfields = []
        fappend = formfields.append

        values = {}

        if hrm:
            # Organisation ID
            htable = s3db.hrm_human_resource
            f = htable.organisation_id
            if f.default:
                values["organisation_id"] = s3_str(f.default)
            fields["organisation_id"] = f
            fappend("organisation_id")
            required["organisation_id"] = settings.get_hrm_org_required()

        self.required = required

        # ID Label
        pe_label = self.pe_label
        if pe_label:
            fields["pe_label"] = ptable.pe_label
            fappend("pe_label")

        # Name fields (always extract all)
        fields["first_name"] = ptable.first_name
        fields["last_name"] = ptable.last_name
        fields["middle_name"] = ptable.middle_name

        separate_name_fields = self.separate_name_fields
        if separate_name_fields is None:
            separate_name_fields = settings.get_pr_separate_name_fields()

        if separate_name_fields:

            # Detect order of name fields
            name_format = settings.get_pr_name_format()
            keys = StringTemplateParser.keys(name_format)

            if keys and keys[0] == "last_name":
                # Last name first
                trigger = "last_name"
                fappend("last_name")
                fappend("first_name")
            else:
                # First name first
                trigger = "first_name"
                fappend("first_name")
                fappend("last_name")

            if separate_name_fields == 3:
                if keys and keys[-1] == "middle_name":
                    fappend("middle_name")
                else:
                    formfields.insert(-1, "middle_name")
        else:
            # Single combined name field
            fields["full_name"] = True
            fappend("full_name")

        if settings.get_pr_request_dob():
            fields["date_of_birth"] = ptable.date_of_birth
            fappend("date_of_birth")

        # Nationality
        nationality = self.nationality
        if nationality is None:
            nationality = settings.get_pr_request_nationality()
        if nationality:
            fields["nationality"] = dtable.nationality
            details = True
            fappend("nationality")

        # Gender
        if settings.get_pr_request_gender():
            f = ptable.gender
            if f.default:
                values["gender"] = s3_str(f.default)
            fields["gender"] = f
            fappend("gender")

        # Occupation
        if self.occupation or controller == "vol":
            fields["occupation"] = dtable.occupation
            details = True
            fappend("occupation")

        # Contact Details
        if settings.get_pr_request_email():
            fields["email"] = True
            fappend("email")
        if settings.get_pr_request_mobile_phone():
            fields["mobile_phone"] = True
            fappend("mobile_phone")
        if settings.get_pr_request_home_phone():
            fields["home_phone"] = True
            fappend("home_phone")

        # Tags
        for tag in tags:
            if tag not in fields:
                fields[tag] = True
                fappend(tag)
            elif current.response.s3.debug:
                # This error would be very hard to diagnose because it only
                # messes up the data without ever hitting an exception, so
                # we raise one right here before it can do any harm:
                raise RuntimeError("PersonSelector person field <-> tag name collision")

        self.fields = fields
        editable_fields = settings.get_pr_editable_fields()
        editable_fields = [fname for fname in editable_fields if fname in fields]
        self.editable_fields = editable_fields

        # Extract existing values
        if value:
            record_id = None
            if isinstance(value, str) and not value.isdigit():
                data, error = self.parse(value)
                if not error:
                    if all(k in data for k in formfields):
                        values = data
                    else:
                        record_id = data.get("id")
            else:
                record_id = value
            if record_id:
                values = self.extract(record_id, fields, details=details, tags=tags, hrm=hrm)

        # Generate the embedded rows
        widget_id = str(field).replace(".", "_")
        formrows = self.embedded_form(field.label, widget_id, formfields, values)

        # Widget Options (pass only non-default options)
        widget_options = {}

        # Duplicate checking?
        lookup_duplicates = settings.get_pr_lookup_duplicates()
        if lookup_duplicates:
            # Add translations for duplicates-review
            i18n.update({"Yes": T("Yes"),
                         "No": T("No"),
                         "dupes_found": T("_NUM_ duplicates found"),
                         })
            widget_options["lookupDuplicates"] = True

        if settings.get_ui_icons() != "font-awesome":
            # Non-default icon theme => pass icon classes
            widget_options["downIcon"] = ICON("down").attributes.get("_class")
            widget_options["yesIcon"] = ICON("deployed").attributes.get("_class")
            widget_options["noIcon"] = ICON("remove").attributes.get("_class")

        # Use separate name fields?
        if separate_name_fields:
            widget_options["separateNameFields"] = True
            if trigger:
                widget_options["trigger"] = trigger

        # Editable Fields
        if editable_fields:
            widget_options["editableFields"] = editable_fields

        # Tags
        if tags:
            widget_options["tags"] = tags

        # Non default AC controller/function?
        if controller != "pr":
            widget_options["c"] = controller
        if fn != "person":
            widget_options["f"] = fn

        # Non-default AC trigger parameters?
        delay = settings.get_ui_autocomplete_delay()
        if delay != 800:
            widget_options["delay"] = delay
        chars = settings.get_ui_autocomplete_min_chars()
        if chars != 2:
            widget_options["chars"] = chars

        if self.pe_label_ignore:
            widget_options["ignoreLabel"] = True

        # Inject the scripts
        self.inject_script(widget_id, widget_options, i18n)

        # Create and return the main input
        attr["_class"] = "hide"

        # Prepend internal validation
        requires = field.requires
        if requires:
            requires = (self.validate, requires)
        else:
            requires = self.validate
        attr["requires"] = requires

        return TAG[""](DIV(INPUT(**attr), _class = "hide"), formrows)

    # -------------------------------------------------------------------------
    def extract(self, record_id, fields, details=False, tags=None, hrm=False):
        """
            Extract the data for a record ID

            Args:
                record_id: the record ID
                fields: the fields to extract, dict {propName: Field}
                details: includes person details
                tags: list of Tags
                hrm: record ID is a hrm_human_resource ID rather than person ID

            Returns:
                dict of {propName: value}
        """

        db = current.db
        s3db = current.s3db

        ptable = s3db.pr_person
        dtable = s3db.pr_person_details

        qfields = [f for f in fields.values() if type(f) is not bool]
        qfields.append(ptable.pe_id)

        if hrm:
            if tags:
                qfields.append(ptable.id)
            htable = s3db.hrm_human_resource
            query = (htable.id == record_id)
            join = ptable.on(ptable.id == htable.person_id)
        else:
            query = (ptable.id == record_id)
            join = None

        if details:
            left = dtable.on(dtable.person_id == ptable.id)
        else:
            left = None

        row = db(query).select(join = join,
                               left = left,
                               limitby = (0, 1),
                               *qfields).first()
        if not row:
            # Raise?
            return {}


        person = row.pr_person if join or left else row
        values = {k: person[k] for k in person}

        if fields.get("full_name"):
            values["full_name"] = s3_fullname(person)

        if details:
            details = row.pr_person_details
            for k in details:
                values[k] = details[k]

        if hrm:
            human_resource = row.hrm_human_resource
            for k in human_resource:
                values[k] = human_resource[k]
            person_id = person.id
        else:
            person_id = record_id

        # Add tags
        if tags:
            for k, v in self.get_tag_data(person_id, tags).items():
                if k not in values:
                    values[k] = v

        values.update(self.get_contact_data(person.pe_id))

        return values

    # -------------------------------------------------------------------------
    def get_contact_data(self, pe_id):
        """
            Extract the contact data for a pe_id; extracts only the first
            value per contact method

            Args:
                pe_id: the pe_id

            Returns:
                a dict {fieldname: value}, where field names correspond to
                the contact method (field map)
        """

        # Map contact method <=> form field name
        names = {"EMAIL": "email",
                 "HOME_PHONE": "home_phone",
                 "SMS": "mobile_phone",
                 }

        # Determine relevant contact methods
        fields = self.fields
        methods = set(m for m in names if fields.get(names[m]))

        # Initialize values with relevant fields
        values = dict.fromkeys((names[m] for m in methods), "")

        if methods:

            # Retrieve the contact data
            ctable = current.s3db.pr_contact
            query = (ctable.pe_id == pe_id) & \
                    (ctable.deleted == False) & \
                    (ctable.contact_method.belongs(methods))

            rows = current.db(query).select(ctable.contact_method,
                                            ctable.value,
                                            orderby = ctable.priority,
                                            )

            # Extract the values
            for row in rows:
                method = row.contact_method
                if method in methods:
                    values[names[method]] = row.value
                    methods.discard(method)
                if not methods:
                    break

        return values

    # -------------------------------------------------------------------------
    @staticmethod
    def get_tag_data(person_id, tags):
        """
            Extract the tag data for a person_id

            Args:
                person_id: the person_id
                tags: list of tags

            Returns:
                a dict {fieldname: value}, where field names correspond to
                the tag name (field map)
        """

        ttable = current.s3db.pr_person_tag
        query = (ttable.person_id == person_id) & \
                (ttable.tag.belongs(tags)) & \
                (ttable.deleted == False)

        rows = current.db(query).select(ttable.tag,
                                        ttable.value,
                                        )
        return {row.tag: row.value for row in rows}

    # -------------------------------------------------------------------------
    def embedded_form(self, label, widget_id, formfields, values):
        """
            Construct the embedded form

            Args:
                label: the label for the embedded form
                       (= field label for the person_id)
                widget_id: the widget ID
                           (=element ID of the person_id field)
                formfields: list of field names indicating which
                            fields to render and in which order
                values: dict with values to populate the embedded form

            Returns:
                a DIV containing the embedded form rows
        """

        T = current.T
        s3 = current.response.s3

        # Test the formstyle
        formstyle = s3.crud.formstyle
        tuple_rows = isinstance(formstyle("", "", "", ""), tuple)

        rows = DIV()

        # Section Title + Actions
        title_id = "%s_title" % widget_id
        label = LABEL(label, _for=title_id)

        if len(self.editable_fields):
            edit_btn = A(ICON("edit"),
                         _class = "edit-action",
                         _title = T("Edit Entry"),
                         )
        else:
            edit_btn = ""

        widget = DIV(edit_btn,
                     A(ICON("eraser"),
                       _class = "clear-action",
                       _title = T("Clear Entry"),
                       ),
                     A(ICON("undo"),
                       _class = "undo-action",
                       _title = T("Revert Entry"),
                       ),
                     _class = "add_person_edit_bar hide",
                     _id = "%s_edit_bar" % widget_id,
                     )

        if tuple_rows:
            row = TR(TD(DIV(label, widget, _class="box_top_inner"),
                        _class = "box_top_td",
                        _colspan = 2,
                        ),
                     _id = "%s__row" % title_id,
                     )
        else:
            row = formstyle("%s__row" % title_id, label, widget, "")
            row.add_class("box_top hide")

        rows.append(row)

        # Input rows
        fields_get = self.fields.get
        get_label = self.get_label
        get_widget = self.get_widget
        for fname in formfields:
            field = fields_get(fname)
            if not field:
                continue # Field is disabled

            field_id = "%s_%s" % (widget_id, fname)

            label = get_label(fname)
            required = self.required.get(fname, False)
            if required:
                label = DIV("%s:" % label, SPAN(" *", _class="req"))
            else:
                label = "%s:" % label
            label = LABEL(label, _for=field_id)

            widget = get_widget(fname, field)
            value = values.get(fname, "")
            if widget:
                widget = widget(field,
                                value,
                                requires = None,
                                _id = field_id,
                                old_value = value,
                                )
                comment = None
            else:
                value = s3_str(value)
                widget = INPUT(_id = field_id,
                               _name = fname,
                               _value = value,
                               old_value = value,
                               )
                comment = None

            row = formstyle("%s__row" % field_id, label, widget, comment)
            if tuple_rows:
                row[0].add_class("box_middle")
                row[1].add_class("box_middle")
                rows.append(row[0])
                rows.append(row[1])
            else:
                row.add_class("box_middle hide")
                rows.append(row)

        # Divider (bottom box)
        if tuple_rows:
            row = formstyle("%s_box_bottom" % widget_id, "", "", "")
            row = row[0]
            row.add_class("box_bottom")
        else:
            row = DIV(_id = "%s_box_bottom" % widget_id,
                      _class = "box_bottom hide",
                      )
        rows.append(row)

        return rows

    # -------------------------------------------------------------------------
    def get_label(self, fieldname):
        """
            Get a label for an embedded field

            Args:
                fieldname: the name of the embedded form field

            Returns:
                the label
        """

        label = self.labels.get(fieldname)
        if label is None:
            # use self.fields
            field = self.fields.get(fieldname)
            if not field or field is True:
                label = ""
            else:
                label = field.label

        return label

    # -------------------------------------------------------------------------
    @staticmethod
    def get_widget(fieldname, field):
        """
            Get a widget for an embedded field; only when the field needs
            a specific widget => otherwise return None here, so the form
            builder will render a standard INPUT

            Args:
                fieldname: the name of the embedded form field
                field: the Field corresponding to the form field

            Returns:
                the widget; or None if no specific widget is required
        """

        # Fields which require a specific widget
        widget = None

        if fieldname in ("organisation_id",
                         "nationality",
                         "gender",
                         ):
            widget = OptionsWidget.widget

        elif fieldname == "date_of_birth":
            if hasattr(field, "widget"):
                widget = field.widget

        return widget

    # -------------------------------------------------------------------------
    def inject_script(self, widget_id, options, i18n):
        """
            Inject the necessary JavaScript for the widget

            Args:
                widget_id: the widget ID (=element ID of the person_id field)
                options: JSON-serializable dict of widget options
                i18n: translations of screen messages rendered by the
                      client-side script, a dict {messageKey: translation}
        """

        s3 = current.response.s3

        # Static script
        if s3.debug:
            script = "/%s/static/scripts/S3/s3.ui.personselector.js" % \
                     current.request.application
        else:
            script = "/%s/static/scripts/S3/s3.ui.personselector.min.js" % \
                     current.request.application
        scripts = s3.scripts
        if script not in scripts:
            scripts.append(script)
            self.inject_i18n(i18n)

        # Widget options
        opts = {}
        if options:
            opts.update(options)

        # Widget instantiation
        script = '''$('#%(widget_id)s').selectPerson(%(options)s)''' % \
                 {"widget_id": widget_id,
                  "options": json.dumps(opts, separators=JSONSEPARATORS),
                  }
        jquery_ready = s3.jquery_ready
        if script not in jquery_ready:
            jquery_ready.append(script)

    # -------------------------------------------------------------------------
    @staticmethod
    def inject_i18n(labels):
        """
            Inject translations for screen messages rendered by the
            client-side script

            Args:
                labels: dict of translations {messageKey: translation}
        """

        strings = ['''i18n.%s="%s"''' % (k, s3_str(v))
                                        for k, v in labels.items()]
        current.response.s3.js_global.append("\n".join(strings))

    # -------------------------------------------------------------------------
    def validate(self, value, record_id=None):
        """
            Validate main input value

            Args:
                value: the main input value (JSON)
                record_id: the record ID (unused, for API compatibility)

            Returns:
                tuple (id, error), where "id" is the record ID of the
                selected or newly created record
        """

        if not isinstance(value, str) or value.isdigit():
            # Not a JSON object => return as-is
            return value, None

        data, error = self.parse(value)
        if (error):
            return value, error

        data_get = data.get

        record_id = data_get("id")
        if record_id:
            # Existing record selected
            if len(data) == 1:
                # Not edited => return ID as-is
                return record_id, None
        else:
            # Establish the name(s)
            names = self.get_names(data)
            if not names:
                # Treat as empty
                return None, None
            else:
                data.update(names)

        # Validate phone numbers
        mobile = data_get("mobile_phone")
        if mobile:
            validator = IS_PHONE_NUMBER_SINGLE(international=True)
            mobile, error = validator(mobile)
            if error:
                return (record_id, error)

        home_phone = data_get("home_phone")
        if home_phone:
            validator = IS_PHONE_NUMBER_MULTI()
            home_phone, error = validator(home_phone)
            if error:
                return (record_id, error)

        # Validate date of birth
        dob = data_get("date_of_birth")
        if not dob and \
           self.fields.get("date_of_birth") and \
           self.required.get("date_of_birth"):
            return (record_id, current.T("Date of Birth is Required"))

        # Validate the email
        error = self.validate_email(data_get("email"))[1]
        if error:
            return (record_id, error)

        if record_id:
            # Try to update the person's related records
            return self.update_person(data)
        else:
            # Try to create the person records (and related records)
            return self.create_person(data)

    # -------------------------------------------------------------------------
    @staticmethod
    def parse(value):
        """
            Parse the main input JSON when the form gets submitted

            Args:
                value: the main input value (JSON)

            Returns:
                tuple (data, error), where data is a dict with the
                submitted data like: {fieldname: value, ...}
        """

        #from ..tools import JSONERRORS
        try:
            data = json.loads(value)
        except JSONERRORS:
            return value, "invalid JSON"

        if type(data) is not dict:
            return value, "invalid JSON"

        return data, None

    # -------------------------------------------------------------------------
    def get_names(self, data):
        """
            Get first, middle and last names from the input data

            Args:
                data: the input data dict

            Returns:
                dict with the name parts found
        """

        settings = current.deployment_settings

        separate_name_fields = self.separate_name_fields
        if separate_name_fields is None:
            separate_name_fields = settings.get_pr_separate_name_fields()

        keys = ["first_name",
                "middle_name",
                "last_name",
                ]

        if separate_name_fields:

            names = {}

            for key in keys:
                value = data.get(key)
                if value:
                    names[key] = value

        else:

            fullname = data.get("full_name")

            if fullname:

                # Shall all name parts go into first_name?
                first_name_only = self.first_name_only
                if first_name_only is None:
                    # Activate by default if using RTL
                    first_name_only = current.response.s3.direction == "rtl"

                if first_name_only:

                    # Put all name parts into first_name
                    names = {"first_name": fullname}

                else:

                    # Separate the name parts
                    name_format = settings.get_pr_name_format()
                    parts = StringTemplateParser.keys(name_format)
                    if parts and parts[0] == "last_name":
                        keys.reverse()
                    names = dict(zip(keys, self.split_names(fullname)))

            else:

                names = {}

        return names

    # -------------------------------------------------------------------------
    @staticmethod
    def split_names(name):
        """
            Split a full name into first/middle/last

            Args:
                name: the full name

            Returns:
                tuple (first, middle, last)
        """

        # https://github.com/derek73/python-nameparser
        from nameparser import HumanName
        name = HumanName(name)

        return name.first, name.middle, name.last

    # -------------------------------------------------------------------------
    def validate_email(self, value, person_id=None):
        """
            Validate the email address; checks whether the email address
            is valid and unique

            Args:
                value: the email address
                person_id: the person ID, if known

            Returns:
                tuple (value, error), where error is None if the email
                address is valid, otherwise contains the error message
        """

        T = current.T

        error_message = T("Please enter a valid email address")

        if value is not None:
            value = value.strip()

        # No email?
        if not value:
            # @todo: may not need to check whether email is enabled?
            email_required = self.fields.get("email") and \
                             self.required.get("email")
            if email_required:
                return (value, error_message)
            return (value, None)

        # Valid email?
        value, error = IS_EMAIL()(value)
        if error:
            return value, error_message

        # Unique email?
        s3db = current.s3db
        ctable = s3db.pr_contact
        query = (ctable.deleted == False) & \
                (ctable.contact_method == "EMAIL") & \
                (ctable.value == value)
        if person_id:
            ptable = s3db.pr_person
            query &= (ctable.pe_id == ptable.pe_id) & \
                     (ptable.id != person_id)
        email = current.db(query).select(ctable.id,
                                         limitby = (0, 1)
                                         ).first()
        if email:
            error_message = T("This email address is already in use")
            return value, error_message

        # Ok!
        return value, None

    # -------------------------------------------------------------------------
    def create_person(self, data):
        """
            Create a new record from form data

            Args:
                data - the submitted data

            Returns:
                tuple (id, error), where "id" is the record ID of the newly
                created record
        """

        T = current.T
        s3db = current.s3db

        # Validate the person fields
        ptable = s3db.pr_person
        person = {}
        for f in filter_fields(ptable, data):
            if f == "id":
                continue
            if f == "pe_label" and self.pe_label_ignore:
                continue
            value, error = s3_validate(ptable, f, data[f])
            if error:
                label = ptable[f].label or f
                return (None, "%s: %s" % (label, error))
            else:
                person[f] = value

        # Onvalidation? (doesn't currently exist)

        set_record_owner = current.auth.s3_set_record_owner
        update_super = s3db.update_super

        # Create new person record
        person["id"] = person_id = ptable.insert(**person)
        update_super(ptable, person)

        if not person_id:
            return (None, T("Could not add person record"))

        data_get = data.get

        hrm = self.hrm
        if hrm:
            # Create the HRM record
            htable = s3db.hrm_human_resource
            human_resource_id = htable.insert(person_id = person_id,
                                              organisation_id = data_get("organisation_id"),
                                              )
            update_super(ptable, {"id": human_resource_id})
            set_record_owner(htable, human_resource_id)

        # Update ownership & realm
        set_record_owner(ptable, person_id)

        # Onaccept
        s3db.onaccept(ptable, person)

        # Read the created pe_id
        pe_id = person.get("pe_id")
        if not pe_id:
            return (None, T("Could not add person details"))

        # Add contact information as provided
        ctable = s3db.pr_contact
        contacts = {"email": "EMAIL",
                    "home_phone": "HOME_PHONE",
                    "mobile_phone": "SMS",
                    }
        for fname, contact_method in contacts.items():
            value = data_get(fname)
            if value:
                ctable.insert(pe_id = pe_id,
                              contact_method = contact_method,
                              value = value,
                              )

        # Add details as provided
        details = {}
        for fname in ("nationality",
                      "occupation",
                      ):
            value = data_get(fname)
            if value:
                details[fname] = value
        if details:
            details["person_id"] = person_id
            s3db.pr_person_details.insert(**details)

        # Add tags as provided
        for _, tag in current.deployment_settings.get_pr_request_tags():
            value = data_get(tag)
            if value:
                s3db.pr_person_tag.insert(person_id = person_id,
                                          tag = tag,
                                          value = value,
                                          )

        if hrm:
            return human_resource_id, None
        else:
            return person_id, None

    # -------------------------------------------------------------------------
    def update_person(self, data):
        """
            Create/Update records from form data

            Args:
                data - the submitted data

            Returns:
                tuple (id, error), where "id" is the record ID of the
                existing person record
        """

        db = current.db
        s3db = current.s3db

        data_get = data.get
        record_id = data_get("id")
        hrm = self.hrm

        if hrm:
            # Read the HR record
            htable = s3db.hrm_human_resource
            hr = db(htable.id == record_id).select(htable.id,
                                                   htable.organisation_id,
                                                   htable.person_id,
                                                   limitby = (0, 1)
                                                   ).first()
            organisation_id = data_get("organisation_id")
            if organisation_id != hr.organisation_id:
                hr.update_record(organisation_id = organisation_id)
            person_id = hr.person_id
        else:
            person_id = record_id

        # Read the Person
        ptable = s3db.pr_person
        person = db(ptable.id == person_id).select(ptable.pe_id,
                                                   limitby = (0, 1)
                                                   ).first()
        pe_id = person.pe_id

        # @ToDo: Handle updates to Name/DoB/Gender/pe_label

        # Update ownership & realm
        current.auth.s3_set_record_owner(ptable, person_id)

        editable_fields = self.editable_fields

        # Add/Update contact information as provided
        ctable = s3db.pr_contact
        contacts = {"email": "EMAIL",
                    "home_phone": "HOME_PHONE",
                    "mobile_phone": "SMS",
                    }
        for fname, contact_method in contacts.items():
            if fname not in editable_fields:
                continue
            value = data_get(fname)
            query = (ctable.pe_id == pe_id) & \
                    (ctable.contact_method == contact_method)
            contact = db(query).select(ctable.id,
                                       ctable.value,
                                       limitby = (0, 1)
                                       ).first()
            if contact:
                if value:
                    if value != contact.value:
                        contact.update_record(value = value)
                else:
                    db(query).delete()
            elif value:
                ctable.insert(pe_id = pe_id,
                              contact_method = contact_method,
                              value = value,
                              )

        # Add/Update details as provided
        details = {}
        for fname in ("nationality",
                      "occupation",
                      ):
            if fname not in editable_fields:
                continue
            details[fname] = data_get(fname)
        if details:
            dtable = s3db.pr_person_details
            drecord = db(dtable.person_id == person_id).select(dtable.id,
                                                               limitby = (0, 1)
                                                               ).first()
            if drecord:
                drecord.update_record(**details)
            else:
                details["person_id"] = person_id
                dtable.insert(**details)

        # Add/Update tags as provided
        tags = current.deployment_settings.get_pr_request_tags()
        if tags:
            ttable = s3db.pr_person_tag
            for _, tag in tags:
                if tag not in editable_fields:
                    continue
                value = data_get(tag)
                query = (ttable.person_id == person_id) & \
                        (ttable.tag == tag)
                trecord = db(query).select(ttable.id,
                                           ttable.value,
                                           limitby = (0, 1)
                                           ).first()
                if trecord:
                    if value != trecord.value:
                        trecord.update_record(value = value)
                elif value:
                    ttable.insert(person_id = person_id,
                                  tag = tag,
                                  value = value,
                                  )

        return record_id, None

# END =========================================================================
