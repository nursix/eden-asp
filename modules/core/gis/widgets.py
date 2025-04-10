"""
    MAP Widgets

    Copyright: (c) 2010-2022 Sahana Software Foundation

    Permission is hereby granted, free of charge, to any person
    obtaining a copy of this software and associated documentation
    files (the "Software"), to deal in the Software without
    restriction, including without limitation the rights to use,
    copy, modify, merge, publish, distribute, sublicense, and/or sell
    copies of the Software, and to permit persons to whom the
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

import json
import os
import re

from urllib.parse import quote as urllib_quote

from gluon import current, URL, DIV, XML, A, HTTP
from gluon.languages import regex_translate

from ..tools import JSONERRORS, JSONSEPARATORS, include_ext_js, include_underscore_js, s3_str

from .base import GIS
from .layers import LayerArcREST, LayerBing, LayerCoordinate, LayerEmpty, LayerFeature, \
                    LayerGPX, LayerGeoJSON, LayerGeoRSS, LayerGoogle, LayerJS, LayerKML, \
                    LayerOSM, LayerOpenWeatherMap, LayerShapefile, LayerTMS, LayerTheme, \
                    LayerWFS, LayerWMS, LayerXYZ, \
                    CLUSTER_ATTRIBUTE, CLUSTER_DISTANCE, CLUSTER_THRESHOLD
from .marker import Marker

# =============================================================================
class MAP(DIV):
    """
        HTML Helper to render a Map
        - allows the Map to be generated only when being rendered
        - used by gis.show_map()
    """

    def __init__(self, **opts):
        """
            Args:
                opts: options to pass to the Map for server-side processing
        """

        # We haven't yet run _setup()
        self.setup = False

        # Options for server-side processing
        self.opts = opts
        opts_get = opts.get

        # Adapt CSS to size of Map
        _class = "map_wrapper"
        if opts_get("window"):
            _class = "%s fullscreen" % _class
        if opts_get("print_mode"):
            _class = "%s print" % _class

        # Set Map ID
        self.id = map_id = opts_get("id", "default_map")

        super(MAP, self).__init__(_class=_class, _id=map_id)

        # Options for client-side processing
        self.options = {}

        self.callback = None
        self.error_message = None
        self.parent = None

        self.globals = None
        self.i18n = None
        self.scripts = None
        self.plugin_callbacks = None

    # -------------------------------------------------------------------------
    def _setup(self):
        """
            Setup the Map
            - not done during init() to be as Lazy as possible
            - separated from xml() in order to be able to read options to put
              into scripts (callback or otherwise)
        """

        # Fresh _setup() call, reset error message
        self.error_message = None

        auth = current.auth

        # Read configuration
        config = GIS.get_config()
        if not config:
            # No prepop - Bail
            if auth.s3_has_permission("create", "gis_hierarchy"):
                error_message = DIV(_class="mapError")
                # Deliberately not T() to save unneccessary load on translators
                error_message.append("Map cannot display without GIS config!")
                error_message.append(XML(" (You can can create one "))
                error_message.append(A("here", _href=URL(c="gis", f="config")))
                error_message.append(")")
                self.error_message = error_message
            else:
                self.error_message = DIV(
                    "Map cannot display without GIS config!",  # Deliberately not T() to save unneccessary load on translators
                    _class="mapError"
                    )
            return None

        T = current.T
        db = current.db
        s3db = current.s3db
        request = current.request
        response = current.response
        if not response.warning:
            response.warning = ""
        s3 = response.s3
        ctable = db.gis_config
        settings = current.deployment_settings
        MAP_ADMIN = auth.s3_has_role(current.session.s3.system_roles.MAP_ADMIN)

        opts_get = self.opts.get

        # Support bookmarks (such as from the control)
        # - these over-ride the arguments
        get_vars_get = request.get_vars.get

        # JS Globals
        js_globals = {}

        # Map Options for client-side processing
        options = {}

        # Strings used by all Maps
        i18n = {"gis_base_layers": T("Base Layers"),
                "gis_overlays": T(settings.get_gis_label_overlays()),
                "gis_layers": T(settings.get_gis_layers_label()),
                "gis_draft_layer": T("Draft Features"),
                "gis_cluster_multiple": T("There are multiple records at this location"),
                "gis_loading": T("Loading"),
                "gis_requires_login": T("Requires Login"),
                "gis_too_many_features": T("There are too many features, please Zoom In or Filter"),
                "gis_zoomin": T("Zoom In"),
                }

        ##########
        # Loader
        ##########

        self.append(DIV(DIV(_class="map_loader"), _id="%s_panel" % self.id))

        ##########
        # Viewport
        ##########

        height = opts_get("height", None)
        if height:
            map_height = height
        else:
            map_height = settings.get_gis_map_height()
        options["map_height"] = map_height
        width = opts_get("width", None)
        if width:
            map_width = width
        else:
            map_width = settings.get_gis_map_width()
        options["map_width"] = map_width

        zoom = get_vars_get("zoom", None)
        if zoom is not None:
            zoom = int(zoom)
        else:
            zoom = opts_get("zoom", None)
        if not zoom:
            zoom = config.zoom
        options["zoom"] = zoom or 1

        # Bounding Box or Center/Zoom
        bbox = opts_get("bbox", None)
        if (bbox
            and (-90 <= bbox["lat_max"] <= 90)
            and (-90 <= bbox["lat_min"] <= 90)
            and (-180 <= bbox["lon_max"] <= 180)
            and (-180 <= bbox["lon_min"] <= 180)
            ):
            # We have sane Bounds provided, so we should use them
            pass
        elif zoom is None:
            # Build Bounds from Config
            bbox = config
        else:
            # No bounds or we've been passed bounds which aren't sane
            bbox = None
            # Use Lat/Lon/Zoom to center instead
            lat = get_vars_get("lat", None)
            if lat is not None:
                lat = float(lat)
            else:
                lat = opts_get("lat", None)
            if lat is None or lat == "":
                lat = config.lat
            lon = get_vars_get("lon", None)
            if lon is not None:
                lon = float(lon)
            else:
                lon = opts_get("lon", None)
            if lon is None or lon == "":
                lon = config.lon

        if bbox:
            # Calculate from Bounds
            options["bbox"] = [bbox["lon_min"], # left
                               bbox["lat_min"], # bottom
                               bbox["lon_max"], # right
                               bbox["lat_max"], # top
                               ]
        else:
            options["lat"] = lat
            options["lon"] = lon

        options["numZoomLevels"] = config.zoom_levels

        options["restrictedExtent"] = (config.lon_min,
                                       config.lat_min,
                                       config.lon_max,
                                       config.lat_max,
                                       )

        ############
        # Projection
        ############

        projection = opts_get("projection", None)
        if not projection:
            projection = config.epsg
        options["projection"] = projection
        if projection not in (900913, 4326):
            # Test for Valid Projection file in Proj4JS library
            projpath = os.path.join(
                request.folder, "static", "scripts", "gis", "proj4js", \
                "lib", "defs", "EPSG%s.js" % projection
            )
            try:
                f = open(projpath, "r")
                f.close()
            except:
                if projection:
                    proj4js = config.proj4js
                    if proj4js:
                        # Create it
                        try:
                            f = open(projpath, "w")
                        except IOError as e:
                            response.error =  \
                        T("Map not available: Cannot write projection file - %s") % e
                        else:
                            f.write('''Proj4js.defs["EPSG:4326"]="%s"''' % proj4js)
                            f.close()
                    else:
                        response.warning =  \
    T("Map not available: Projection %(projection)s not supported - please add definition to %(path)s") % \
        {"projection": "'%s'" % projection,
         "path": "/static/scripts/gis/proj4js/lib/defs",
         }
                else:
                    response.error =  \
                        T("Map not available: No Projection configured")
                return None
            options["maxExtent"] = config.maxExtent
            options["units"] = config.units

        ########
        # Marker
        ########

        if config.marker_image:
            options["marker_default"] = {"i": config.marker_image,
                                         "h": config.marker_height,
                                         "w": config.marker_width,
                                         }
        # @ToDo: show_map() opts with fallback to settings
        # Keep these in sync with scaleImage() in s3.gis.js
        marker_max_height = settings.get_gis_marker_max_height()
        if marker_max_height != 35:
            options["max_h"] = marker_max_height
        marker_max_width = settings.get_gis_marker_max_width()
        if marker_max_width != 30:
            options["max_w"] = marker_max_width

        #########
        # Colours
        #########

        # Keep these in sync with s3.gis.js
        cluster_fill = settings.get_gis_cluster_fill()
        if cluster_fill and cluster_fill != '8087ff':
            options["cluster_fill"] = cluster_fill
        cluster_stroke = settings.get_gis_cluster_stroke()
        if cluster_stroke and cluster_stroke != '2b2f76':
            options["cluster_stroke"] = cluster_stroke
        select_fill = settings.get_gis_select_fill()
        if select_fill and select_fill != 'ffdc33':
            options["select_fill"] = select_fill
        select_stroke = settings.get_gis_select_stroke()
        if select_stroke and select_stroke != 'ff9933':
            options["select_stroke"] = select_stroke
        if not settings.get_gis_cluster_label():
            options["cluster_label"] = False

        ########
        # Layout
        ########

        if not opts_get("closable", False):
            options["windowNotClosable"] = True
        if opts_get("window", False):
            options["window"] = True
            if opts_get("window_hide", False):
                options["windowHide"] = True

        if opts_get("maximizable", False):
            options["maximizable"] = True
        else:
            options["maximizable"] = False

        # Collapsed
        if opts_get("collapsed", False):
            options["west_collapsed"] = True

        # LayerTree
        if not settings.get_gis_layer_tree_base():
            options["hide_base"] = True
        if not settings.get_gis_layer_tree_overlays():
            options["hide_overlays"] = True
        if not settings.get_gis_layer_tree_expanded():
            options["folders_closed"] = True
        if settings.get_gis_layer_tree_radio():
            options["folders_radio"] = True

        #######
        # Tools
        #######

        # Toolbar
        if opts_get("toolbar", False):
            options["toolbar"] = True

            i18n["gis_length_message"] = T("The length is")
            i18n["gis_length_tooltip"] = T("Measure Length: Click the points along the path & end with a double-click")
            i18n["gis_zoomfull"] = T("Zoom to maximum map extent")

            if settings.get_gis_geolocate_control():
                # Presence of label turns feature on in s3.gis.js
                # @ToDo: Provide explicit option to support multiple maps in a page with different options
                i18n["gis_geoLocate"] = T("Zoom to Current Location")

            # Search
            if opts_get("search", False):
                geonames_username = settings.get_gis_geonames_username()
                if geonames_username:
                    # Presence of username turns feature on in s3.gis.js
                    options["geonames"] = geonames_username
                    # Presence of label adds support JS in Loader
                    i18n["gis_search"] = T("Search location in Geonames")
                    #i18n["gis_search_no_internet"] = T("Geonames.org search requires Internet connectivity!")

            # Show NAV controls?
            # e.g. removed within LocationSelector
            nav = opts_get("nav", None)
            if nav is None:
                nav = settings.get_gis_nav_controls()
            if nav:
                i18n["gis_zoominbutton"] = T("Zoom In: click in the map or use the left mouse button and drag to create a rectangle")
                i18n["gis_zoomout"] = T("Zoom Out: click in the map or use the left mouse button and drag to create a rectangle")
                i18n["gis_pan"] = T("Pan Map: keep the left mouse button pressed and drag the map")
                i18n["gis_navPrevious"] = T("Previous View")
                i18n["gis_navNext"] = T("Next View")
            else:
                options["nav"] = False

            # Show Area control?
            if opts_get("area", False):
                options["area"] = True
                i18n["gis_area_message"] = T("The area is")
                i18n["gis_area_tooltip"] = T("Measure Area: Click the points around the polygon & end with a double-click")

            # Show Print control?
            print_control = opts_get("print_control") is not False and settings.get_gis_print()
            if print_control:
                # @ToDo: Use internal Printing or External Service
                # http://eden.sahanafoundation.org/wiki/BluePrint/GIS/Printing
                #print_service = settings.get_gis_print_service()
                #if print_service:
                #    print_tool = {"url": string,            # URL of print service (e.g. http://localhost:8080/geoserver/pdf/)
                #                  "mapTitle": string,       # Title for the Printed Map (optional)
                #                  "subTitle": string        # subTitle for the Printed Map (optional)
                #                  }
                options["print"] = True
                i18n["gis_print"] = T("Print")
                i18n["gis_paper_size"] = T("Paper Size")
                i18n["gis_print_tip"] = T("Take a screenshot of the map which can be printed")

            # Show Save control?
            # e.g. removed within LocationSelector
            if opts_get("save") is True and auth.s3_logged_in():
                options["save"] = True
                i18n["gis_save"] = T("Save: Default Lat, Lon & Zoom for the Viewport")
                if MAP_ADMIN or (config.pe_id == auth.user.pe_id):
                    # Personal config or MapAdmin, so Save Button does Updates
                    options["config_id"] = config.id

            # OSM Authoring
            pe_id = auth.user.pe_id if auth.s3_logged_in() else None
            if pe_id and s3db.auth_user_options_get_osm(pe_id):
                # Presence of label turns feature on in s3.gis.js
                # @ToDo: Provide explicit option to support multiple maps in a page with different options
                i18n["gis_potlatch"] = T("Edit the OpenStreetMap data for this area")
                i18n["gis_osm_zoom_closer"] = T("Zoom in closer to Edit OpenStreetMap layer")

            # MGRS PDF Browser
            mgrs = opts_get("mgrs", None)
            if mgrs:
                options["mgrs_name"] = mgrs["name"]
                options["mgrs_url"] = mgrs["url"]
        else:
            # No toolbar
            if opts_get("save") is True:
                self.opts["save"] = "float"

        # Show Save control?
        # e.g. removed within LocationSelector
        if opts_get("save") == "float" and auth.s3_logged_in():
            permit = auth.s3_has_permission
            if permit("create", ctable):
                options["save"] = "float"
                i18n["gis_save_map"] = T("Save Map")
                i18n["gis_new_map"] = T("Save as New Map?")
                i18n["gis_name_map"] = T("Name of Map")
                i18n["save"] = T("Save")
                i18n["saved"] = T("Saved")
                config_id = config.id
                _config = db(ctable.id == config_id).select(ctable.uuid,
                                                            ctable.name,
                                                            limitby = (0, 1),
                                                            ).first()
                if MAP_ADMIN:
                    i18n["gis_my_maps"] = T("Saved Maps")
                else:
                    options["pe_id"] = auth.user.pe_id
                    i18n["gis_my_maps"] = T("My Maps")
                if permit("update", ctable, record_id=config_id):
                    options["config_id"] = config_id
                    options["config_name"] = _config.name
                elif _config.uuid != "SITE_DEFAULT":
                    options["config_name"] = _config.name

        # Legend panel
        legend = opts_get("legend", False)
        if legend:
            i18n["gis_legend"] = T("Legend")
            if legend == "float":
                options["legend"] = "float"
                if settings.get_gis_layer_metadata():
                    options["metadata"] = True
                    # MAP_ADMIN better for simpler deployments
                    #if auth.s3_has_permission("create", "cms_post_layer"):
                    if MAP_ADMIN:
                        i18n["gis_metadata_create"] = T("Create 'More Info'")
                        i18n["gis_metadata_edit"] = T("Edit 'More Info'")
                    else:
                        i18n["gis_metadata"] = T("More Info")
            else:
                options["legend"] = True

        # Draw Feature Controls
        if opts_get("add_feature", False):
            i18n["gis_draw_feature"] = T("Add Point")
            if opts_get("add_feature_active", False):
                options["draw_feature"] = "active"
            else:
                options["draw_feature"] = "inactive"

        if opts_get("add_line", False):
            i18n["gis_draw_line"] = T("Add Line")
            if opts_get("add_line_active", False):
                options["draw_line"] = "active"
            else:
                options["draw_line"] = "inactive"

        if opts_get("add_polygon", False):
            i18n["gis_draw_polygon"] = T("Add Polygon")
            i18n["gis_draw_polygon_clear"] = T("Clear Polygon")
            if opts_get("add_polygon_active", False):
                options["draw_polygon"] = "active"
            else:
                options["draw_polygon"] = "inactive"

        if opts_get("add_circle", False):
            i18n["gis_draw_circle"] = T("Add Circle")
            if opts_get("add_circle_active", False):
                options["draw_circle"] = "active"
            else:
                options["draw_circle"] = "inactive"

        # Clear Layers
        clear_layers = opts_get("clear_layers") is not False and settings.get_gis_clear_layers()
        if clear_layers:
            options["clear_layers"] = clear_layers
            i18n["gis_clearlayers"] = T("Clear all Layers")

        # Layer Properties
        if settings.get_gis_layer_properties():
            # Presence of label turns feature on in s3.gis.js
            i18n["gis_properties"] = T("Layer Properties")

        # Upload Layer
        if settings.get_gis_geoserver_password():
            # Presence of label adds support JS in Loader and turns feature on in s3.gis.js
            # @ToDo: Provide explicit option to support multiple maps in a page with different options
            i18n["gis_uploadlayer"] = T("Upload Shapefile")

        # WMS Browser
        wms_browser = opts_get("wms_browser", None)
        if wms_browser:
            options["wms_browser_name"] = wms_browser["name"]
            # urlencode the URL
            options["wms_browser_url"] = urllib_quote(wms_browser["url"])

        # Mouse Position
        # 'normal', 'mgrs' or 'off'
        mouse_position = opts_get("mouse_position", None)
        if mouse_position is None:
            mouse_position = settings.get_gis_mouse_position()
        if mouse_position == "mgrs":
            options["mouse_position"] = "mgrs"
            # Tell loader to load support scripts
            js_globals["mgrs"] = True
        elif mouse_position:
            options["mouse_position"] = True

        # Overview Map
        overview = opts_get("overview", None)
        if overview is None:
            overview = settings.get_gis_overview()
        if not overview:
            options["overview"] = False

        # Permalink
        permalink = opts_get("permalink", None)
        if permalink is None:
            permalink = settings.get_gis_permalink()
        if not permalink:
            options["permalink"] = False

        # ScaleLine
        scaleline = opts_get("scaleline", None)
        if scaleline is None:
            scaleline = settings.get_gis_scaleline()
        if not scaleline:
            options["scaleline"] = False

        # Zoom control
        zoomcontrol = opts_get("zoomcontrol", None)
        if zoomcontrol is None:
            zoomcontrol = settings.get_gis_zoomcontrol()
        if not zoomcontrol:
            options["zoomcontrol"] = False

        zoomWheelEnabled = opts_get("zoomWheelEnabled", True)
        if not zoomWheelEnabled:
            options["no_zoom_wheel"] = True

        ########
        # Layers
        ########

        # Duplicate Features to go across the dateline?
        # @ToDo: Action this again (e.g. for DRRPP)
        if settings.get_gis_duplicate_features():
            options["duplicate_features"] = True

        # Features
        features = opts_get("features", None)
        if features:
            options["features"] = addFeatures(features)

        # Feature Queries
        feature_queries = opts_get("feature_queries", None)
        if feature_queries:
            options["feature_queries"] = addFeatureQueries(feature_queries)

        # Feature Resources
        feature_resources = opts_get("feature_resources", None)
        if feature_resources:
            options["feature_resources"] = addFeatureResources(feature_resources)

        # Layers
        db = current.db
        ltable = db.gis_layer_config
        etable = db.gis_layer_entity
        query = (ltable.deleted == False)
        join = [etable.on(etable.layer_id == ltable.layer_id)]
        fields = [etable.instance_type,
                  ltable.layer_id,
                  ltable.enabled,
                  ltable.visible,
                  ltable.base,
                  ltable.dir,
                  ]

        if opts_get("catalogue_layers", False):
            # Add all enabled Layers from the Catalogue
            stable = db.gis_style
            mtable = db.gis_marker
            query &= (ltable.config_id.belongs(config.ids))
            join.append(ctable.on(ctable.id == ltable.config_id))
            fields.extend((stable.style,
                           stable.cluster_distance,
                           stable.cluster_threshold,
                           stable.opacity,
                           stable.popup_format,
                           mtable.image,
                           mtable.height,
                           mtable.width,
                           ctable.pe_type))
            left = [stable.on((stable.layer_id == etable.layer_id) & \
                              (stable.record_id == None) & \
                              ((stable.config_id == ctable.id) | \
                               (stable.config_id == None))),
                    mtable.on(mtable.id == stable.marker_id),
                    ]
            limitby = None
            # @ToDo: Need to fix this?: make the style lookup a different call
            if settings.get_database_type() == "postgres":
                # None is last
                orderby = [ctable.pe_type, stable.config_id]
            else:
                # None is 1st
                orderby = [ctable.pe_type, ~stable.config_id]
            if settings.get_gis_layer_metadata():
                cptable = s3db.cms_post_layer
                left.append(cptable.on(cptable.layer_id == etable.layer_id))
                fields.append(cptable.post_id)
        else:
            # Add just the default Base Layer
            query &= (ltable.base == True) & \
                     (ltable.config_id == config.id)
            # Base layer doesn't need a style
            left = None
            limitby = (0, 1)
            orderby = None

        layer_types = []
        lappend = layer_types.append
        layers = db(query).select(join = join,
                                  left = left,
                                  limitby = limitby,
                                  orderby = orderby,
                                  *fields)
        if not layers:
            # Use Site Default base layer
            # (Base layer doesn't need a style)
            query = (etable.id == ltable.layer_id) & \
                    (ltable.config_id == ctable.id) & \
                    (ctable.uuid == "SITE_DEFAULT") & \
                    (ltable.base == True) & \
                    (ltable.enabled == True)
            layers = db(query).select(*fields,
                                      limitby = (0, 1))
            if not layers:
                # Just show EmptyLayer
                layer_types = [LayerEmpty]

        for layer in layers:
            layer_type = layer["gis_layer_entity.instance_type"]
            if layer_type == "gis_layer_openstreetmap":
                lappend(LayerOSM)
            elif layer_type == "gis_layer_google":
                # NB v3 doesn't work when initially hidden
                lappend(LayerGoogle)
            elif layer_type == "gis_layer_arcrest":
                lappend(LayerArcREST)
            elif layer_type == "gis_layer_bing":
                lappend(LayerBing)
            elif layer_type == "gis_layer_tms":
                lappend(LayerTMS)
            elif layer_type == "gis_layer_wms":
                lappend(LayerWMS)
            elif layer_type == "gis_layer_xyz":
                lappend(LayerXYZ)
            elif layer_type == "gis_layer_empty":
                lappend(LayerEmpty)
            elif layer_type == "gis_layer_js":
                lappend(LayerJS)
            elif layer_type == "gis_layer_theme":
                lappend(LayerTheme)
            elif layer_type == "gis_layer_geojson":
                lappend(LayerGeoJSON)
            elif layer_type == "gis_layer_gpx":
                lappend(LayerGPX)
            elif layer_type == "gis_layer_coordinate":
                lappend(LayerCoordinate)
            elif layer_type == "gis_layer_georss":
                lappend(LayerGeoRSS)
            elif layer_type == "gis_layer_kml":
                lappend(LayerKML)
            elif layer_type == "gis_layer_openweathermap":
                lappend(LayerOpenWeatherMap)
            elif layer_type == "gis_layer_shapefile":
                lappend(LayerShapefile)
            elif layer_type == "gis_layer_wfs":
                lappend(LayerWFS)
            elif layer_type == "gis_layer_feature":
                lappend(LayerFeature)

        # Make unique
        layer_types = set(layer_types)
        scripts = []
        scripts_append = scripts.append
        for LayerType in layer_types:
            try:
                # Instantiate the Class
                layer = LayerType(layers, openlayers=2)
                layer.as_dict(options)
                for script in layer.scripts:
                    scripts_append(script)
            except Exception as exception:
                error = "%s not shown: %s" % (LayerType.__name__, exception)
                current.log.error(error)
                if s3.debug:
                    raise HTTP(500, error)
                else:
                    response.warning += error

        # WMS getFeatureInfo
        # (loads conditionally based on whether queryable WMS Layers have been added)
        if s3.gis.get_feature_info and settings.get_gis_getfeature_control():
            # Presence of label turns feature on
            # @ToDo: Provide explicit option to support multiple maps in a page
            #        with different options
            i18n["gis_get_feature_info"] = T("Get Feature Info")
            i18n["gis_feature_info"] = T("Feature Info")

        # Callback can be set before _setup()
        if not self.callback:
            self.callback = opts_get("callback", "DEFAULT")
        # These can be read/modified after _setup() & before xml()
        self.options = options

        self.globals = js_globals
        self.i18n = i18n
        self.scripts = scripts

        # Set up map plugins
        # @ToDo: Get these working with new loader
        # This, and any code it generates, is done last
        # However, map plugin should not assume this.
        self.plugin_callbacks = []
        plugins = opts_get("plugins", None)
        if plugins:
            for plugin in plugins:
                plugin.extend_gis_map(self)

        # Flag to xml() that we've already been run
        self.setup = True

        return options

    # -------------------------------------------------------------------------
    def xml(self):
        """
            Render the Map
            - this is primarily done by inserting a lot of JavaScript
            - CSS loaded as-standard to avoid delays in page loading
            - HTML added in init() as a component
        """

        if not self.setup:
            result = self._setup()
            if result is None:
                if self.error_message:
                    self.append(self.error_message)
                    return super(MAP, self).xml()
                return ""

        # Add ExtJS
        # @ToDo: Do this conditionally on whether Ext UI is used
        include_ext_js()

        dumps = json.dumps
        s3 = current.response.s3

        js_global = s3.js_global
        js_global_append = js_global.append

        i18n_dict = self.i18n
        i18n = []
        i18n_append = i18n.append
        for key, val in i18n_dict.items():
            line = '''i18n.%s="%s"''' % (key, val)
            if line not in i18n:
                i18n_append(line)
        i18n = '''\n'''.join(i18n)
        if i18n not in js_global:
            js_global_append(i18n)

        globals_dict = self.globals
        js_globals = []
        for key, val in globals_dict.items():
            line = '''S3.gis.%s=%s''' % (key, dumps(val, separators=JSONSEPARATORS))
            if line not in js_globals:
                js_globals.append(line)
        js_globals = '''\n'''.join(js_globals)
        if js_globals not in js_global:
            js_global_append(js_globals)

        # Underscore for Popup Templates
        include_underscore_js()

        debug = s3.debug
        scripts = s3.scripts

        if debug:
            script = URL(c="static", f="scripts/S3/s3.gis.loader.js")
        else:
            script = URL(c="static", f="scripts/S3/s3.gis.loader.min.js")
        if script not in scripts:
            scripts.append(script)

        callback = self.callback
        map_id = self.id
        options = self.options
        projection = options["projection"]
        try:
            options = dumps(options, separators=JSONSEPARATORS)
        except Exception as exception:
            current.log.error("Map %s failed to initialise" % map_id, exception)
        plugin_callbacks = '''\n'''.join(self.plugin_callbacks)
        if callback:
            if callback == "DEFAULT":
                if map_id == "default_map":
                    callback = '''S3.gis.show_map(null,%s)''' % options
                else:
                    callback = '''S3.gis.show_map(%s,%s)''' % (map_id, options)
            else:
                # Store options where they can be read by a later show_map()
                js_global_append('''S3.gis.options["%s"]=%s''' % (map_id,
                                                                  options))
            if plugin_callbacks:
                callback = '''%s\n%s''' % (callback, plugin_callbacks)
            callback = '''function(){%s}''' % callback
        else:
            # Store options where they can be read by a later show_map()
            js_global_append('''S3.gis.options["%s"]=%s''' % (map_id, options))
            if plugin_callbacks:
                callback = '''function(){%s}''' % plugin_callbacks
            else:
                callback = '''null'''
        loader = \
'''s3_gis_loadjs(%(debug)s,%(projection)s,%(callback)s,%(scripts)s)''' \
            % {"debug": "true" if debug else "false",
               "projection": projection,
               "callback": callback,
               "scripts": self.scripts,
               }
        jquery_ready = s3.jquery_ready
        if loader not in jquery_ready:
            jquery_ready.append(loader)

        # Return the HTML
        return super(MAP, self).xml()

# =============================================================================
class MAP2(DIV):
    """
        HTML Helper to render a Map
        - allows the Map to be generated only when being rendered

        This is the Work-in-Progress update of MAP() to OpenLayers 6
    """

    def __init__(self, **opts):
        """
            Args:
                opts: options to pass to the Map for server-side processing
        """

        self.opts = opts
        opts_get = opts.get

        # Pass options to DIV()
        map_id = opts_get("id", "default_map")
        height = opts_get("height")
        if height is None:
            height = current.deployment_settings.get_gis_map_height()
        super(MAP2, self).__init__(DIV(_class = "s3-gis-tooltip"),
                                   _id = map_id,
                                   _style = "height:%ipx;width:100%%" % height,
                                   )

        # Load CSS now as too late in xml()
        stylesheets = current.response.s3.stylesheets
        stylesheet = "gis/ol6.css"
        if stylesheet not in stylesheets:
            stylesheets.append(stylesheet)
        # @ToDo: Move this to Theme
        stylesheet = "gis/ol6_popup.css"
        if stylesheet not in stylesheets:
            stylesheets.append(stylesheet)

    # -------------------------------------------------------------------------
    def _options(self):
        """
            Configuration for the Map
        """

        # Read Map Config
        config = GIS.get_config()
        if not config:
            # No prepop => Bail
            return None

        options = {}

        # i18n
        if current.session.s3.language != "en":
            T = current.T
            options["i18n"] = {"loading": s3_str(T("Loading")),
                               "requires_login": s3_str(T("Requires Login")),
                               }

        # Read options for this Map
        get_vars_get = current.request.get_vars.get
        opts_get = self.opts.get
        settings = current.deployment_settings

        ##########
        # Viewport
        ##########

        #options["height"] = opts_get("height", settings.get_gis_map_height())
        #options["width"] = opts_get("width", settings.get_gis_map_width())

        zoom = get_vars_get("zoom", None)
        if zoom is not None:
            zoom = int(zoom)
        else:
            zoom = opts_get("zoom", None)
        if not zoom:
            zoom = config.zoom
        options["zoom"] = zoom or 0

        # Bounding Box or Center/Zoom
        bbox = opts_get("bbox", None)
        if (bbox
            and (-90 <= bbox["lat_max"] <= 90)
            and (-90 <= bbox["lat_min"] <= 90)
            and (-180 <= bbox["lon_max"] <= 180)
            and (-180 <= bbox["lon_min"] <= 180)
            ):
            # We have sane Bounds provided, so we should use them
            pass
        elif zoom is None:
            # Build Bounds from Config
            bbox = config
        else:
            # No bounds or we've been passed bounds which aren't sane
            bbox = None
            # Use Lat/Lon/Zoom to center instead
            lat = get_vars_get("lat", None)
            if lat is not None:
                lat = float(lat)
            else:
                lat = opts_get("lat", None)
            if lat is None or lat == "":
                lat = config.lat
            lon = get_vars_get("lon", None)
            if lon is not None:
                lon = float(lon)
            else:
                lon = opts_get("lon", None)
            if lon is None or lon == "":
                lon = config.lon

        if bbox:
            # Calculate from Bounds
            options["bbox"] = [bbox["lon_min"], # left
                               bbox["lat_min"], # bottom
                               bbox["lon_max"], # right
                               bbox["lat_max"], # top
                               ]
        else:
            options["lat"] = lat
            options["lon"] = lon

        #options["numZoomLevels"] = config.zoom_levels

        #options["restrictedExtent"] = (config.lon_min,
        #                               config.lat_min,
        #                               config.lon_max,
        #                               config.lat_max,
        #                               )


        ############
        # Projection
        ############

        #projection = opts_get("projection", config.epsg)
        #if projection == 90013:
        #    # New EPSG for Spherical Mercator
        #    projection = 3857
        #options["projection"] = projection

        #if projection not in (3857, 4326):
        #    # Test for Valid Projection file in Proj4JS library
        #    projpath = os.path.join(
        #        request.folder, "static", "scripts", "gis", "proj4js", \
        #        "lib", "defs", "EPSG%s.js" % projection
        #    )
        #    try:
        #        f = open(projpath, "r")
        #        f.close()
        #    except:
        #        if projection:
        #            proj4js = config.proj4js
        #            if proj4js:
        #                # Create it
        #                try:
        #                    f = open(projpath, "w")
        #                except IOError as e:
        #                    response.error =  \
        #                T("Map not available: Cannot write projection file - %s") % e
        #                else:
        #                    f.write('''Proj4js.defs["EPSG:4326"]="%s"''' % proj4js)
        #                    f.close()
        #            else:
        #                response.warning =  \
        #T("Map not available: Projection %(projection)s not supported - please add definition to %(path)s") % \
        #{"projection": "'%s'" % projection,
        # "path": "/static/scripts/gis/proj4js/lib/defs",
        # }
        #        else:
        #            response.error =  \
        #                T("Map not available: No Projection configured")
        #        return None
        #    options["maxExtent"] = config.maxExtent
        #    options["units"] = config.units

        ##################
        # Marker (Default)
        ##################

        if config.marker_image:
            options["marker"] = config.marker_image

        ########
        # Layers
        ########

        # Duplicate Features to go across the dateline?
        # @ToDo: Action this again (e.g. for DRRPP)
        #if settings.get_gis_duplicate_features():
        #    options["duplicate_features"] = True

        # Features
        features = opts_get("features", None)
        if features:
            options["features"] = addFeatures(features)

        # Feature Queries
        feature_queries = opts_get("feature_queries", None)
        if feature_queries:
            options["feature_queries"] = addFeatureQueries(feature_queries)

        # Feature Resources
        feature_resources = opts_get("feature_resources", None)
        if feature_resources:
            options["feature_resources"] = addFeatureResources(feature_resources)

        # Layers
        db = current.db
        ctable = db.gis_config
        ltable = db.gis_layer_config
        etable = db.gis_layer_entity
        query = (ltable.deleted == False)
        join = [etable.on(etable.layer_id == ltable.layer_id)]
        fields = [etable.instance_type,
                  ltable.layer_id,
                  ltable.enabled,
                  ltable.visible,
                  ltable.base,
                  ltable.dir,
                  ]

        if opts_get("catalogue_layers", False):
            # Add all enabled Layers from the Catalogue
            stable = db.gis_style
            mtable = db.gis_marker
            query &= (ltable.config_id.belongs(config.ids))
            join.append(ctable.on(ctable.id == ltable.config_id))
            fields.extend((stable.style,
                           stable.cluster_distance,
                           stable.cluster_threshold,
                           stable.opacity,
                           stable.popup_format,
                           mtable.image,
                           mtable.height,
                           mtable.width,
                           ctable.pe_type))
            left = [stable.on((stable.layer_id == etable.layer_id) & \
                              (stable.record_id == None) & \
                              ((stable.config_id == ctable.id) | \
                               (stable.config_id == None))),
                    mtable.on(mtable.id == stable.marker_id),
                    ]
            limitby = None
            # @ToDo: Need to fix this?: make the style lookup a different call
            if settings.get_database_type() == "postgres":
                # None is last
                orderby = [ctable.pe_type, stable.config_id]
            else:
                # None is 1st
                orderby = [ctable.pe_type, ~stable.config_id]
            if settings.get_gis_layer_metadata():
                cptable = current.s3db.cms_post_layer
                left.append(cptable.on(cptable.layer_id == etable.layer_id))
                fields.append(cptable.post_id)
        else:
            # Add just the default Base Layer
            query &= (ltable.base == True) & \
                     (ltable.config_id == config.id)
            # Base layer doesn't need a style
            left = None
            limitby = (0, 1)
            orderby = None

        layer_types = []
        lappend = layer_types.append
        layers = db(query).select(join = join,
                                  left = left,
                                  limitby = limitby,
                                  orderby = orderby,
                                  *fields)
        if not layers:
            # Use Site Default base layer
            # (Base layer doesn't need a style)
            query = (etable.id == ltable.layer_id) & \
                    (ltable.config_id == ctable.id) & \
                    (ctable.uuid == "SITE_DEFAULT") & \
                    (ltable.base == True) & \
                    (ltable.enabled == True)
            layers = db(query).select(*fields,
                                      limitby = (0, 1)
                                      )
            if not layers:
                # Just show EmptyLayer
                layer_types = [LayerEmpty]

        for layer in layers:
            layer_type = layer["gis_layer_entity.instance_type"]
            if layer_type == "gis_layer_openstreetmap":
                lappend(LayerOSM)
            elif layer_type == "gis_layer_google":
                # NB v3 doesn't work when initially hidden
                lappend(LayerGoogle)
            elif layer_type == "gis_layer_arcrest":
                lappend(LayerArcREST)
            elif layer_type == "gis_layer_bing":
                lappend(LayerBing)
            elif layer_type == "gis_layer_tms":
                lappend(LayerTMS)
            elif layer_type == "gis_layer_wms":
                lappend(LayerWMS)
            elif layer_type == "gis_layer_xyz":
                lappend(LayerXYZ)
            elif layer_type == "gis_layer_empty":
                lappend(LayerEmpty)
            elif layer_type == "gis_layer_js":
                lappend(LayerJS)
            elif layer_type == "gis_layer_theme":
                lappend(LayerTheme)
            elif layer_type == "gis_layer_geojson":
                lappend(LayerGeoJSON)
            elif layer_type == "gis_layer_gpx":
                lappend(LayerGPX)
            elif layer_type == "gis_layer_coordinate":
                lappend(LayerCoordinate)
            elif layer_type == "gis_layer_georss":
                lappend(LayerGeoRSS)
            elif layer_type == "gis_layer_kml":
                lappend(LayerKML)
            elif layer_type == "gis_layer_openweathermap":
                lappend(LayerOpenWeatherMap)
            elif layer_type == "gis_layer_shapefile":
                lappend(LayerShapefile)
            elif layer_type == "gis_layer_wfs":
                lappend(LayerWFS)
            elif layer_type == "gis_layer_feature":
                lappend(LayerFeature)

        # Make unique
        layer_types = set(layer_types)
        scripts = []
        scripts_append = scripts.append
        for layer_type_class in layer_types:
            try:
                # Instantiate the Class
                layer = layer_type_class(layers)
                layer.as_dict(options)
                for script in layer.scripts:
                    scripts_append(script)
            except Exception as exception:
                error = "%s not shown: %s" % (layer_type_class.__name__, exception)
                current.log.error(error)
                response = current.response
                if response.s3.debug:
                    raise HTTP(500, error)
                else:
                    response.warning += error

        return options

    # -------------------------------------------------------------------------
    def xml(self):
        """
            Render the Map
            - this is primarily done by inserting JavaScript
        """

        # Read Map Config
        options = self._options()

        if options is None:
            # No Map Config: Just show error in the DIV
            auth = current.auth

            if auth.s3_has_permission("create", "gis_hierarchy"):
                error_message = DIV(_class = "mapError")
                # Deliberately not T() to save unneccessary load on translators
                error_message.append("Map cannot display without GIS config!")
                error_message.append(XML(" (You can can create one "))
                error_message.append(A("here", _href=URL(c="gis", f="config")))
                error_message.append(")")
            else:
                error_message = DIV(
                    "Map cannot display without GIS config!",  # Deliberately not T() to save unneccessary load on translators
                    _class="mapError"
                    )

            self.components = [error_message]
            return super(MAP2, self).xml()

        map_id = self.opts.get("id", "default_map")
        options = json.dumps(options, separators=JSONSEPARATORS)

        # Insert the JavaScript
        appname = current.request.application
        s3 = current.response.s3

        # Underscore for Popup Templates
        include_underscore_js()

        # OpenLayers
        script = "/%s/static/scripts/gis/ol.js" % appname
        if script not in s3.scripts:
            s3.scripts.append(script)

        # S3 GIS
        if s3.debug:
            script = "/%s/static/scripts/S3/s3.ui.gis.js" % appname
        else:
            script = "/%s/static/scripts/S3/s3.ui.gis.min.js" % appname
        if script not in s3.scripts_modules:
            s3.scripts_modules.append(script)

        script = '''$('#%(map_id)s').showMap(%(options)s)''' % {"map_id": map_id,
                                                                "options": options,
                                                                }
        s3.jquery_ready.append(script)

        # Return the HTML
        return super(MAP2, self).xml()

# =============================================================================
def addFeatures(features):
    """
        Add Simple Features to the Draft layer
        - used by S3LocationSelectorWidget

        @todo: obsolete?
    """

    simplify = GIS.simplify
    _f = []
    append = _f.append
    for feature in features:
        geojson = simplify(feature, output="geojson")
        if geojson:
            f = {"type": "Feature",
                 "geometry": json.loads(geojson),
                 }
            append(f)
    return _f

# =============================================================================
def addFeatureQueries(feature_queries):
    """
        Add Feature Queries to the map
            - These can be Rows or Storage()

        Note:
            These considerations need to be taken care of before arriving here:
                - Security of data
                - Localisation of name/popup_label
    """

    db = current.db
    s3db = current.s3db
    cache = s3db.cache
    request = current.request
    controller = request.controller
    function = request.function
    fqtable = s3db.gis_feature_query
    mtable = s3db.gis_marker

    auth = current.auth
    auth_user = auth.user
    if auth_user:
        created_by = auth_user.id
        s3_make_session_owner = auth.s3_make_session_owner
    else:
        # Anonymous
        # @ToDo: A deployment with many Anonymous Feature Queries being
        #        accessed will need to change this design - e.g. use session ID instead
        created_by = None

    layers_feature_query = []
    append = layers_feature_query.append
    for layer in feature_queries:
        name = str(layer["name"])
        _layer = {"name": name}
        name_safe = re.sub(r"\W", "_", name)

        # Lat/Lon via Join or direct?
        try:
            join = hasattr(layer["query"][0].gis_location, "lat")
        except (AttributeError, KeyError):
            # Invalid layer
            continue

        # Push the Features into a temporary table in order to have them accessible via GeoJSON
        # @ToDo: Maintenance Script to clean out old entries (> 24 hours?)
        cname = "%s_%s_%s" % (name_safe,
                              controller,
                              function)
        # Clear old records
        query = (fqtable.name == cname) & \
                (fqtable.created_by == created_by)
        db(query).delete()
        for row in layer["query"]:
            rowdict = {"name" : cname}
            if join:
                rowdict["lat"] = row.gis_location.lat
                rowdict["lon"] = row.gis_location.lon
            else:
                rowdict["lat"] = row["lat"]
                rowdict["lon"] = row["lon"]
            if "popup_url" in row:
                rowdict["popup_url"] = row["popup_url"]
            if "popup_label" in row:
                rowdict["popup_label"] = row["popup_label"]
            if "marker" in row:
                rowdict["marker_url"] = URL(c="static", f="img",
                                            args=["markers",
                                                  row["marker"].image])
                rowdict["marker_height"] = row["marker"].height
                rowdict["marker_width"] = row["marker"].width
            else:
                if "marker_url" in row:
                    rowdict["marker_url"] = row["marker_url"]
                if "marker_height" in row:
                    rowdict["marker_height"] = row["marker_height"]
                if "marker_width" in row:
                    rowdict["marker_width"] = row["marker_width"]
            if "shape" in row:
                rowdict["shape"] = row["shape"]
            if "size" in row:
                rowdict["size"] = row["size"]
            if "colour" in row:
                rowdict["colour"] = row["colour"]
            if "opacity" in row:
                rowdict["opacity"] = row["opacity"]
            record_id = fqtable.insert(**rowdict)
            if not created_by:
                s3_make_session_owner(fqtable, record_id)

        # URL to retrieve the data
        url = "%s.geojson?feature_query.name=%s&feature_query.created_by=%s" % \
                (URL(c="gis", f="feature_query"),
                 cname,
                 created_by)
        _layer["url"] = url

        if "active" in layer and not layer["active"]:
            _layer["visibility"] = False

        if "marker" in layer:
            # per-Layer Marker
            marker = layer["marker"]
            if isinstance(marker, int):
                # integer (marker_id) not row
                marker = db(mtable.id == marker).select(mtable.image,
                                                        mtable.height,
                                                        mtable.width,
                                                        limitby = (0, 1),
                                                        cache=cache
                                                        ).first()
            if marker:
                # @ToDo: Single option as Marker.as_json_dict()
                _layer["marker_url"] = marker["image"]
                _layer["marker_height"] = marker["height"]
                _layer["marker_width"] = marker["width"]

        if "opacity" in layer and layer["opacity"] != 1:
            _layer["opacity"] = "%.1f" % layer["opacity"]
        if "cluster_attribute" in layer and \
           layer["cluster_attribute"] != CLUSTER_ATTRIBUTE:
            _layer["cluster_attribute"] = layer["cluster_attribute"]
        if "cluster_distance" in layer and \
           layer["cluster_distance"] != CLUSTER_DISTANCE:
            _layer["cluster_distance"] = layer["cluster_distance"]
        if "cluster_threshold" in layer and \
           layer["cluster_threshold"] != CLUSTER_THRESHOLD:
            _layer["cluster_threshold"] = layer["cluster_threshold"]
        append(_layer)

    return layers_feature_query

# =============================================================================
def addFeatureResources(feature_resources):
    """
        Add Feature Resources to the map
            - REST URLs to back-end resources
    """

    T = current.T
    db = current.db
    s3db = current.s3db
    ftable = s3db.gis_layer_feature
    ltable = s3db.gis_layer_config
    # Better to do a separate query
    #mtable = s3db.gis_marker
    stable = db.gis_style
    config = GIS.get_config()
    config_id = config.id
    postgres = current.deployment_settings.get_database_type() == "postgres"

    layers_feature_resource = []
    append = layers_feature_resource.append
    for layer in feature_resources:
        name = s3_str(layer["name"])
        _layer = {"name": name}
        _id = layer.get("id")
        if _id:
            _id = str(_id)
        else:
            _id = name
        _id = re.sub(r"\W", "_", _id)
        _layer["id"] = _id

        # Are we loading a Catalogue Layer or a simple URL?
        layer_id = layer.get("layer_id", None)
        if layer_id:
            query = (ftable.layer_id == layer_id)
            left = [ltable.on((ltable.layer_id == layer_id) & \
                              (ltable.config_id == config_id)),
                    stable.on((stable.layer_id == layer_id) & \
                              ((stable.config_id == config_id) | \
                               (stable.config_id == None)) & \
                              (stable.record_id == None) & \
                              (stable.aggregate == False)),
                    # Better to do a separate query
                    #mtable.on(mtable.id == stable.marker_id),
                    ]
            # @ToDo: Need to fix this?: make the style lookup a different call
            if postgres:
                # None is last
                orderby = stable.config_id
            else:
                # None is 1st
                orderby = ~stable.config_id
            row = db(query).select(ftable.layer_id,
                                   ftable.controller,
                                   ftable.function,
                                   ftable.filter,
                                   ftable.aggregate,
                                   ftable.trackable,
                                   ftable.use_site,
                                   # @ToDo: Deprecate Legacy
                                   ftable.popup_fields,
                                   # @ToDo: Deprecate Legacy
                                   ftable.popup_label,
                                   ftable.cluster_attribute,
                                   ltable.dir,
                                   # Better to do a separate query
                                   #mtable.image,
                                   #mtable.height,
                                   #mtable.width,
                                   stable.marker_id,
                                   stable.opacity,
                                   stable.popup_format,
                                   # @ToDo: If-required
                                   #stable.url_format,
                                   stable.cluster_distance,
                                   stable.cluster_threshold,
                                   stable.style,
                                   left=left,
                                   limitby = (0, 1),
                                   orderby=orderby,
                                   ).first()
            _dir = layer.get("dir", row["gis_layer_config.dir"])
            # Better to do a separate query
            #_marker = row["gis_marker"]
            _style = row["gis_style"]
            row = row["gis_layer_feature"]
            if row.use_site:
                maxdepth = 1
            else:
                maxdepth = 0
            opacity = layer.get("opacity", _style.opacity) or 1
            cluster_attribute = layer.get("cluster_attribute",
                                          row.cluster_attribute) or \
                                CLUSTER_ATTRIBUTE
            cluster_distance = layer.get("cluster_distance",
                                         _style.cluster_distance) or \
                                CLUSTER_DISTANCE
            cluster_threshold = layer.get("cluster_threshold",
                                          _style.cluster_threshold)
            if cluster_threshold is None:
                cluster_threshold = CLUSTER_THRESHOLD
            style = layer.get("style", None)
            if style:
                try:
                    # JSON Object?
                    style = json.loads(style)
                except JSONERRORS:
                    current.log.error("Invalid Style: %s" % style)
                    style = None
            else:
                style = _style.style
            #url_format = _style.url_format

            # Parameters for Layer URL (in addition to any filters)
            params = layer.get("custom_params") or {}
            params.update({"layer": row.layer_id,
                           "show_ids": "true",
                           })
            aggregate = layer.get("aggregate", row.aggregate)
            if aggregate:
                url = URL(c = row.controller,
                          f = row.function,
                          args = ["report.geojson"],
                          vars = params,
                          )
                #if not url_format:
                # Use gis/location controller in all reports
                url_format = "%s/{id}.plain" % URL(c="gis", f="location")
            else:
                params.update({"mcomponents": "None",
                               "maxdepth": maxdepth,
                               })
                url = URL(c = row.controller,
                          f = "%s.geojson" % row.function,
                          vars = params,
                          )
                #if not url_format
                url_format = "%s/{id}.plain" % URL(c = row.controller, f = row.function)

            # Use specified filter or fallback to the one in the layer
            _filter = layer.get("filter", row.filter)
            if _filter:
                url = "%s&%s" % (url, _filter)
            if row.trackable:
                url = "%s&track=1" % url
            if not style:
                marker = layer.get("marker")
                if marker:
                    marker = Marker(marker).as_json_dict()
                elif _style.marker_id:
                    marker = Marker(marker_id=_style.marker_id).as_json_dict()

            popup_format = _style.popup_format
            if not popup_format:
                # Old-style
                popup_fields = row["popup_fields"]
                if popup_fields:
                    popup_label = row["popup_label"]
                    if popup_label:
                        popup_format = "{%s} (%s)" % (popup_fields[0],
                                                      current.T(popup_label))
                    else:
                        popup_format = "%s" % popup_fields[0]
                    for f in popup_fields[1:]:
                        popup_format = "%s<br />{%s}" % (popup_format, f)

        else:
            # URL to retrieve the data
            url = layer["url"]
            tablename = layer["tablename"]
            table = s3db[tablename]
            # Optimise the query
            if "location_id" in table.fields:
                maxdepth = 0
            elif "site_id" in table.fields:
                maxdepth = 1
            elif tablename == "gis_location":
                maxdepth = 0
            else:
                # Not much we can do!
                # @ToDo: Use Context
                continue
            options = "mcomponents=None&maxdepth=%s&show_ids=true" % maxdepth
            if "?" in url:
                url = "%s&%s" % (url, options)
            else:
                url = "%s?%s" % (url, options)
            opacity = layer.get("opacity", 1)
            cluster_attribute = layer.get("cluster_attribute",
                                          CLUSTER_ATTRIBUTE)
            cluster_distance = layer.get("cluster_distance",
                                         CLUSTER_DISTANCE)
            cluster_threshold = layer.get("cluster_threshold",
                                          CLUSTER_THRESHOLD)
            _dir = layer.get("dir", None)
            style = layer.get("style", None)
            if style:
                try:
                    # JSON Object?
                    style = json.loads(style)
                except JSONERRORS:
                    current.log.error("Invalid Style: %s" % style)
                    style = None
            if not style:
                marker = layer.get("marker", None)
                if marker:
                    marker = Marker(marker).as_json_dict()
            popup_format = layer.get("popup_format")
            url_format = layer.get("url_format")

        if "active" in layer and not layer["active"]:
            _layer["visibility"] = False
        if opacity != 1:
            _layer["opacity"] = "%.1f" % opacity
        if popup_format:
            if "T(" in popup_format:
                # i18n
                items = regex_translate.findall(popup_format)
                for item in items:
                    titem = str(T(item[1:-1]))
                    popup_format = popup_format.replace("T(%s)" % item,
                                                        titem)
            _layer["popup_format"] = popup_format
        if url_format:
            _layer["url_format"] = url_format
        if cluster_attribute != CLUSTER_ATTRIBUTE:
            _layer["cluster_attribute"] = cluster_attribute
        if cluster_distance != CLUSTER_DISTANCE:
            _layer["cluster_distance"] = cluster_distance
        if cluster_threshold != CLUSTER_THRESHOLD:
            _layer["cluster_threshold"] = cluster_threshold
        if _dir:
            _layer["dir"] = _dir

        if style:
            _layer["style"] = style
        elif marker:
            # Per-layer Marker
            _layer["marker"] = marker
        else:
            # Request the server to provide per-feature Markers
            url = "%s&markers=1" % url
        _layer["url"] = url
        append(_layer)

    return layers_feature_resource

# END =========================================================================
