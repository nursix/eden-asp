"""
    Map Layer Configuration

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

import datetime # Needed for Feed Refresh checks & web2py version check
import json
import os
import re

from http import cookies as Cookie
from urllib.parse import quote as urllib_quote

from gluon import current, URL
from gluon.languages import regex_translate

from ..model import META_FIELD_NAMES
from ..tools import JSONERRORS, JSONSEPARATORS, s3_str

from .marker import Marker
from .projection import Projection

# Map Defaults
# Also in static/S3/s3.gis.js
# http://dev.openlayers.org/docs/files/OpenLayers/Strategy/Cluster-js.html
CLUSTER_ATTRIBUTE = "colour"
CLUSTER_DISTANCE = 20   # pixels
CLUSTER_THRESHOLD = 2   # minimum # of features to form a cluster

# =============================================================================
class Layer:
    """
        Abstract base class for Layers from Catalogue
    """

    tablename = None
    dictname = "layer_generic"
    style = False

    def __init__(self, all_layers, openlayers=6):

        self.openlayers = openlayers

        sublayers = []
        append = sublayers.append
        # List of Scripts to load async with the Map JavaScript
        self.scripts = []

        s3_has_role = current.auth.s3_has_role

        tablename = self.tablename
        table = current.s3db[tablename]
        fields = [table[f] for f in table.fields if f not in META_FIELD_NAMES]
        layer_ids = [row["gis_layer_config.layer_id"] for row in all_layers if \
                     row["gis_layer_entity.instance_type"] == tablename]
        query = (table.layer_id.belongs(set(layer_ids)))
        rows = current.db(query).select(*fields)

        # Flag to show whether we've set the default baselayer
        # (otherwise a config higher in the hierarchy can overrule one lower down)
        base = True
        # Layers requested to be visible via URL (e.g. embedded map)
        visible = current.request.get_vars.get("layers", None)
        if visible:
            visible = visible.split(".")
        else:
            visible = []
        metadata = current.deployment_settings.get_gis_layer_metadata()
        styled = self.style

        for record in rows:
            layer_id = record.layer_id

            # Find the 1st row in all_layers which matches this
            row = None
            for candidate in all_layers:
                if candidate["gis_layer_config.layer_id"] == layer_id:
                    row = candidate
                    break
            if not row:
                continue

            # Check if layer is enabled
            layer_config = row["gis_layer_config"]
            if layer_config.enabled is False:
                continue

            # Check user is allowed to access the layer
            role_required = record.role_required
            if role_required and not s3_has_role(role_required):
                continue

            # All OK - add SubLayer
            record["visible"] = layer_config.visible or str(layer_id) in visible
            if base and layer_config.base:
                # var name can't conflict with OSM/WMS/ArcREST layers
                record["_base"] = True
                base = False
            else:
                record["_base"] = False

            record["dir"] = layer_config.dir

            if styled:
                style = row.get("gis_style", None)
                if style:
                    style_dict = style.style
                    if isinstance(style_dict, str):
                        # Matryoshka (=double-serialized JSON)?
                        # - should no longer happen, but a (now-fixed) bug
                        #   regularly produced double-serialized JSON, so
                        #   catching it here to keep it working with legacy
                        #   databases:
                        try:
                            style_dict = json.loads(style_dict)
                        except JSONERRORS:
                            pass
                    if style_dict:
                        record["style"] = style_dict
                    else:
                        record["style"] = None
                        marker = row.get("gis_marker", None)
                        if marker:
                            record["marker"] = Marker(marker)
                        #if style.marker_id:
                        #    record["marker"] = Marker(marker_id=style.marker_id)
                        else:
                            # Default Marker?
                            record["marker"] = Marker(tablename=tablename)
                    record["opacity"] = style.opacity or 1
                    record["popup_format"] = style.popup_format
                    record["cluster_distance"] = style.cluster_distance or CLUSTER_DISTANCE
                    if style.cluster_threshold != None:
                        record["cluster_threshold"] = style.cluster_threshold
                    else:
                        record["cluster_threshold"] = CLUSTER_THRESHOLD
                else:
                    record["style"] = None
                    record["opacity"] = 1
                    record["popup_format"] = None
                    record["cluster_distance"] = CLUSTER_DISTANCE
                    record["cluster_threshold"] = CLUSTER_THRESHOLD
                    # Default Marker?
                    record["marker"] = Marker(tablename=tablename)

            if metadata:
                post_id = row.get("cms_post_layer.post_id", None)
                record["post_id"] = post_id

            if tablename in ("gis_layer_bing", "gis_layer_google"):
                # SubLayers handled differently
                append(record)
            else:
                append(self.SubLayer(record, openlayers))

        # Alphasort layers
        # - client will only sort within their type: s3.gis.layers.js
        self.sublayers = sorted(sublayers, key=lambda row: row.name)

    # -------------------------------------------------------------------------
    def as_dict(self, options=None):
        """
            Output the Layers as a Python dict
        """

        sublayer_dicts = []
        append = sublayer_dicts.append
        sublayers = self.sublayers
        for sublayer in sublayers:
            # Read the output dict for this sublayer
            sublayer_dict = sublayer.as_dict()
            if sublayer_dict:
                # Add this layer to the list of layers for this layer type
                append(sublayer_dict)

        if sublayer_dicts and options:
            # Used by Map._setup()
            options[self.dictname] = sublayer_dicts

        return sublayer_dicts

    # -------------------------------------------------------------------------
    def as_json(self):
        """
            Output the Layers as JSON
        """

        result = self.as_dict()
        if result:
            return json.dumps(result, separators=JSONSEPARATORS)
        else:
            return ""

    # -------------------------------------------------------------------------
    def as_javascript(self):
        """
            Output the Layers as global Javascript
            - suitable for inclusion in the HTML page
        """

        result = self.as_json()
        if result:
            return '''S3.gis.%s=%s\n''' % (self.dictname, result)
        else:
            return ""

    # -------------------------------------------------------------------------
    class SubLayer:
        def __init__(self, record, openlayers):
            # Ensure all attributes available (even if Null)
            self.__dict__.update(record)
            del record
            if current.deployment_settings.get_L10n_translate_gis_layer():
                self.safe_name = re.sub('[\\"]', "", s3_str(current.T(self.name)))
            else:
                self.safe_name = re.sub('[\\"]', "", self.name)

            self.openlayers = openlayers

            if hasattr(self, "projection_id"):
                self.projection = Projection(self.projection_id)

        def as_dict(self):
            raise NotImplementedError

        def __getattr__(self, key):
            return self.__dict__.__getattribute__(key)

        def setup_clustering(self, output):
            if hasattr(self, "cluster_attribute"):
                cluster_attribute = self.cluster_attribute
            else:
                cluster_attribute = None
            cluster_distance = self.cluster_distance
            cluster_threshold = self.cluster_threshold
            if cluster_attribute and \
               cluster_attribute != CLUSTER_ATTRIBUTE:
                output["cluster_attribute"] = cluster_attribute
            if cluster_distance != CLUSTER_DISTANCE:
                output["cluster_distance"] = cluster_distance
            if cluster_threshold != CLUSTER_THRESHOLD:
                output["cluster_threshold"] = cluster_threshold

        def setup_folder(self, output):
            if self.dir:
                output["dir"] = s3_str(current.T(self.dir))

        def setup_folder_and_visibility(self, output):
            if not self.visible:
                output["visibility"] = False
            if self.dir:
                output["dir"] = s3_str(current.T(self.dir))

        def setup_folder_visibility_and_opacity(self, output):
            if not self.visible:
                output["visibility"] = False
            if self.opacity != 1:
                output["opacity"] = "%.1f" % self.opacity
            if self.dir:
                output["dir"] = s3_str(current.T(self.dir))

        # ---------------------------------------------------------------------
        @staticmethod
        def add_attributes_if_not_default(output, **values_and_defaults):
            # could also write values in debug mode, to check if defaults ignored.
            # could also check values are not being overwritten.
            for key, (value, defaults) in values_and_defaults.items():
                if value not in defaults:
                    output[key] = value

# -----------------------------------------------------------------------------
class LayerArcREST(Layer):
    """
        ArcGIS REST Layers from Catalogue
    """

    tablename = "gis_layer_arcrest"
    dictname = "layers_arcrest"
    style = False

    # -------------------------------------------------------------------------
    class SubLayer(Layer.SubLayer):
        def as_dict(self):
            # Mandatory attributes
            output = {"id": self.layer_id,
                      "type": "arcrest",
                      "name": self.safe_name,
                      "url": self.url,
                      }

            # Attributes which are defaulted client-side if not set
            self.setup_folder_and_visibility(output)
            self.add_attributes_if_not_default(
                output,
                layers = (self.layers, ([0],)),
                transparent = (self.transparent, (True,)),
                base = (self.base, (False,)),
                _base = (self._base, (False,)),
                format = (self.img_format, ("png",)),
            )

            return output

# -----------------------------------------------------------------------------
class LayerBing(Layer):
    """
        Bing Layers from Catalogue
    """

    tablename = "gis_layer_bing"
    dictname = "Bing"
    style = False

    # -------------------------------------------------------------------------
    def as_dict(self, options=None):

        sublayers = self.sublayers
        if sublayers:
            if Projection().epsg != 900913:
                raise Exception("Cannot display Bing layers unless we're using the Spherical Mercator Projection\n")
            apikey = current.deployment_settings.get_gis_api_bing()
            if not apikey:
                raise Exception("Cannot display Bing layers unless we have an API key\n")
            # Mandatory attributes
            ldict = {"ApiKey": apikey
                     }

            for sublayer in sublayers:
                # Attributes which are defaulted client-side if not set
                if sublayer._base:
                    # Set default Base layer
                    ldict["Base"] = sublayer.type
                if sublayer.type == "aerial":
                    ldict["Aerial"] = {"name": sublayer.name or "Bing Satellite",
                                       "id": sublayer.layer_id}
                elif sublayer.type == "road":
                    ldict["Road"] = {"name": sublayer.name or "Bing Roads",
                                     "id": sublayer.layer_id}
                elif sublayer.type == "hybrid":
                    ldict["Hybrid"] = {"name": sublayer.name or "Bing Hybrid",
                                       "id": sublayer.layer_id}
            if options:
                # Used by Map._setup()
                options[self.dictname] = ldict
        else:
            ldict = None

        # Used by as_json() and hence as_javascript()
        return ldict

# -----------------------------------------------------------------------------
class LayerCoordinate(Layer):
    """
        Coordinate Layer from Catalogue
        - there should only be one of these
    """

    tablename = "gis_layer_coordinate"
    dictname = "CoordinateGrid"
    style = False

    # -------------------------------------------------------------------------
    def as_dict(self, options=None):
        sublayers = self.sublayers
        if sublayers:
            sublayer = sublayers[0]
            name_safe = re.sub("'", "", sublayer.name)
            ldict = {"name": name_safe,
                     "visibility": sublayer.visible,
                     "id": sublayer.layer_id,
                     }
            if options:
                # Used by Map._setup()
                options[self.dictname] = ldict
        else:
            ldict = None

        # Used by as_json() and hence as_javascript()
        return ldict

# -----------------------------------------------------------------------------
class LayerEmpty(Layer):
    """
        Empty Layer from Catalogue
        - there should only be one of these
    """

    tablename = "gis_layer_empty"
    dictname = "EmptyLayer"
    style = False

    # -------------------------------------------------------------------------
    def as_dict(self, options=None):

        sublayers = self.sublayers
        if sublayers:
            sublayer = sublayers[0]
            name = s3_str(current.T(sublayer.name))
            name_safe = re.sub("'", "", name)
            ldict = {"name": name_safe,
                     "id": sublayer.layer_id,
                     }
            if sublayer._base:
                ldict["base"] = True
            if options:
                # Used by Map._setup()
                options[self.dictname] = ldict
        else:
            ldict = None

        # Used by as_json() and hence as_javascript()
        return ldict

# -----------------------------------------------------------------------------
class LayerFeature(Layer):
    """
        Feature Layers from Catalogue
    """

    tablename = "gis_layer_feature"
    dictname = "layers_feature"
    style = True

    # -------------------------------------------------------------------------
    class SubLayer(Layer.SubLayer):
        def __init__(self, record, openlayers):
            controller = record.controller
            self.skip = False
            if controller is not None:
                if controller not in current.deployment_settings.modules:
                    # Module is disabled
                    self.skip = True
                if not current.auth.permission.has_permission("read",
                                                              c=controller,
                                                              f=record.function):
                    # User has no permission to this resource (in ACL)
                    self.skip = True
            else:
                error = "Feature Layer Record '%s' has no controller" % \
                    record.name
                raise Exception(error)
            super(LayerFeature.SubLayer, self).__init__(record, openlayers)

        def as_dict(self):
            if self.skip:
                # Skip layer
                return None
            # @ToDo: Option to force all filters via POST?
            if self.aggregate:
                # id is used for url_format
                url = "%s.geojson?layer=%i&show_ids=true" % \
                    (URL(c=self.controller, f=self.function, args="report"),
                     self.layer_id)
                # Use gis/location controller in all reports
                url_format = "%s/{id}.plain" % URL(c="gis", f="location")
            else:
                if self.use_site:
                    maxdepth = 1
                else:
                    maxdepth = 0
                _url = URL(self.controller, self.function)
                # id is used for url_format
                url = "%s.geojson?layer=%i&mcomponents=None&maxdepth=%s&show_ids=true" % \
                    (_url,
                     self.layer_id,
                     maxdepth)
                url_format = "%s/{id}.plain" % _url
            if self.filter:
                url = "%s&%s" % (url, self.filter)
            if self.trackable:
                url = "%s&track=1" % url

            # Mandatory attributes
            output = {"id": self.layer_id,
                      # Defaults client-side if not-provided
                      #"type": "feature",
                      "name": self.safe_name,
                      "url_format": url_format,
                      "url": url,
                      }

            popup_format = self.popup_format
            if popup_format:
                # New-style
                if "T(" in popup_format:
                    # i18n
                    T = current.T
                    items = regex_translate.findall(popup_format)
                    for item in items:
                        titem = str(T(item[1:-1]))
                        popup_format = popup_format.replace("T(%s)" % item,
                                                            titem)
                output["popup_format"] = popup_format
            else:
                # @ToDo: Deprecate
                popup_fields = self.popup_fields
                if popup_fields:
                    # Old-style
                    popup_label = self.popup_label
                    if popup_label:
                        popup_format = "{%s} (%s)" % (popup_fields[0],
                                                      current.T(popup_label))
                    else:
                        popup_format = "%s" % popup_fields[0]
                    for f in popup_fields[1:]:
                        popup_format = "%s<br/>{%s}" % (popup_format, f)
                output["popup_format"] = popup_format or ""

            # Attributes which are defaulted client-side if not set
            self.setup_folder_visibility_and_opacity(output)
            self.setup_clustering(output)
            if self.aggregate:
                # Enable the Cluster Strategy, so that it can be enabled/disabled
                # depending on the zoom level & hence Points or Polygons
                output["cluster"] = 1
            if not popup_format:
                # Need this to differentiate from e.g. FeatureQueries
                output["no_popups"] = 1
            if self.style:
                output["style"] = self.style
            else:
                self.marker.add_attributes_to_output(output)

            return output

# -----------------------------------------------------------------------------
class LayerGeoJSON(Layer):
    """
        GeoJSON Layers from Catalogue
    """

    tablename = "gis_layer_geojson"
    dictname = "layers_geojson"
    style = True

    # -------------------------------------------------------------------------
    class SubLayer(Layer.SubLayer):
        def as_dict(self):
            # Mandatory attributes
            output = {"id": self.layer_id,
                      "type": "geojson",
                      "name": self.safe_name,
                      "url": self.url,
                      }

            # Attributes which are defaulted client-side if not set
            projection = self.projection
            if projection.epsg != 4326:
                output["projection"] = projection.epsg
            self.setup_folder_visibility_and_opacity(output)
            self.setup_clustering(output)
            if self.style:
                output["style"] = self.style
            else:
                self.marker.add_attributes_to_output(output)

            popup_format = self.popup_format
            if popup_format:
                if "T(" in popup_format:
                    # i18n
                    T = current.T
                    items = regex_translate.findall(popup_format)
                    for item in items:
                        titem = str(T(item[1:-1]))
                        popup_format = popup_format.replace("T(%s)" % item,
                                                            titem)
                output["popup_format"] = popup_format

            return output

# -----------------------------------------------------------------------------
class LayerGeoRSS(Layer):
    """
        GeoRSS Layers from Catalogue
    """

    tablename = "gis_layer_georss"
    dictname = "layers_georss"
    style = True

    def __init__(self, all_layers, openlayers=6):
        super().__init__(all_layers, openlayers)
        LayerGeoRSS.SubLayer.cachetable = current.s3db.gis_cache

    # -------------------------------------------------------------------------
    class SubLayer(Layer.SubLayer):
        def as_dict(self):
            db = current.db
            request = current.request
            response = current.response
            cachetable = self.cachetable

            url = self.url
            # Check to see if we should Download layer to the cache
            download = True
            query = (cachetable.source == url)
            existing_cached_copy = db(query).select(cachetable.modified_on,
                                                    limitby = (0, 1)).first()
            refresh = self.refresh or 900 # 15 minutes set if we have no data (legacy DB)
            if existing_cached_copy:
                modified_on = existing_cached_copy.modified_on
                cutoff = modified_on + datetime.timedelta(seconds=refresh)
                if request.utcnow < cutoff:
                    download = False
            if download:
                # Download layer to the Cache
                from gluon.tools import fetch
                # @ToDo: Call directly without going via HTTP
                # @ToDo: Make this async by using S3Task (also use this for the refresh time)
                fields = ""
                if self.data:
                    fields = "&data_field=%s" % self.data
                if self.image:
                    fields = "%s&image_field=%s" % (fields, self.image)
                _url = "%s%s/update.georss?fetchurl=%s%s" % (current.deployment_settings.get_base_public_url(),
                                                             URL(c="gis", f="cache_feed"),
                                                             url,
                                                             fields)
                # Keep Session for local URLs
                cookie = Cookie.SimpleCookie()
                cookie[response.session_id_name] = response.session_id
                current.session._unlock(response)
                try:
                    # @ToDo: Need to commit to not have DB locked with SQLite?
                    fetch(_url, cookie=cookie)
                    if existing_cached_copy:
                        # Clear old selfs which are no longer active
                        query = (cachetable.source == url) & \
                                (cachetable.modified_on < cutoff)
                        db(query).delete()
                except Exception as exception:
                    current.log.error("GeoRSS %s download error" % url, exception)
                    # Feed down
                    if existing_cached_copy:
                        # Use cached copy
                        # Should we Update timestamp to prevent every
                        # subsequent request attempting the download?
                        #query = (cachetable.source == url)
                        #db(query).update(modified_on=request.utcnow)
                        pass
                    else:
                        response.warning += "%s down & no cached copy available" % url

            name_safe = self.safe_name

            # Pass the GeoJSON URL to the client
            # Filter to the source of this feed
            url = "%s.geojson?cache.source=%s" % (URL(c="gis", f="cache_feed"),
                                                  url)

            # Mandatory attributes
            output = {"id": self.layer_id,
                      "type": "georss",
                      "name": name_safe,
                      "url": url,
                      }
            self.marker.add_attributes_to_output(output)

            # Attributes which are defaulted client-side if not set
            if self.refresh != 900:
                output["refresh"] = self.refresh
            self.setup_folder_visibility_and_opacity(output)
            self.setup_clustering(output)

            return output

# -----------------------------------------------------------------------------
class LayerGoogle(Layer):
    """
        Google Layers/Tools from Catalogue
    """

    tablename = "gis_layer_google"
    dictname = "Google"
    style = False

    # -------------------------------------------------------------------------
    def as_dict(self, options=None):

        sublayers = self.sublayers

        if sublayers:
            T = current.T
            spherical_mercator = (Projection().epsg == 900913)
            settings = current.deployment_settings
            apikey = settings.get_gis_api_google()
            s3 = current.response.s3
            debug = s3.debug
            # Google scripts use document.write so cannot be loaded async
            s3_scripts = s3.scripts

            ldict = {}

            if spherical_mercator:
                # Earth was the only layer which can run in non-Spherical Mercator
                # @ToDo: Warning?
                for sublayer in sublayers:
                    # Attributes which are defaulted client-side if not set
                    #if sublayer.type == "earth":
                    #    # Deprecated:
                    #    # https://maps-apis.googleblog.com/2014/12/announcing-deprecation-of-google-earth.html
                    #    ldict["Earth"] = str(T("Switch to 3D"))
                    #    #{"modules":[{"name":"earth","version":"1"}]}
                    #    script = "//www.google.com/jsapi?key=" + apikey + "&autoload=%7B%22modules%22%3A%5B%7B%22name%22%3A%22earth%22%2C%22version%22%3A%221%22%7D%5D%7D"
                    #    if script not in s3_scripts:
                    #        s3_scripts.append(script)
                    #    # Dynamic Loading not supported: https://developers.google.com/loader/#Dynamic
                    #    #s3.jquery_ready.append('''try{google.load('earth','1')catch(e){}''')
                    #    if debug:
                    #        self.scripts.append("gis/gxp/widgets/GoogleEarthPanel.js")
                    #    else:
                    #        self.scripts.append("gis/gxp/widgets/GoogleEarthPanel.min.js")
                    #    s3.js_global.append('''S3.public_url="%s"''' % settings.get_base_public_url())
                    if sublayer._base:
                        # Set default Base layer
                        ldict["Base"] = sublayer.type
                    if sublayer.type == "satellite":
                        ldict["Satellite"] = {"name": sublayer.name or "Google Satellite",
                                              "id": sublayer.layer_id}
                    elif sublayer.type == "maps":
                        ldict["Maps"] = {"name": sublayer.name or "Google Maps",
                                         "id": sublayer.layer_id}
                    elif sublayer.type == "hybrid":
                        ldict["Hybrid"] = {"name": sublayer.name or "Google Hybrid",
                                           "id": sublayer.layer_id}
                    elif sublayer.type == "streetview":
                        ldict["StreetviewButton"] = "Click where you want to open Streetview"
                    elif sublayer.type == "terrain":
                        ldict["Terrain"] = {"name": sublayer.name or "Google Terrain",
                                            "id": sublayer.layer_id}
                    elif sublayer.type == "mapmaker":
                        ldict["MapMaker"] = {"name": sublayer.name or "Google MapMaker",
                                             "id": sublayer.layer_id}
                    elif sublayer.type == "mapmakerhybrid":
                        ldict["MapMakerHybrid"] = {"name": sublayer.name or "Google MapMaker Hybrid",
                                                   "id": sublayer.layer_id}

                if "MapMaker" in ldict or "MapMakerHybrid" in ldict:
                    # Need to use v2 API
                    # This should be able to be fixed in OpenLayers now since Google have fixed in v3 API:
                    # http://code.google.com/p/gmaps-api-issues/issues/detail?id=2349#c47
                    script = "//maps.google.com/maps?file=api&v=2&key=%s" % apikey
                    if script not in s3_scripts:
                        s3_scripts.append(script)
                else:
                    # v3 API
                    # https://developers.google.com/maps/documentation/javascript/versions
                    script = "//maps.google.com/maps/api/js?v=quarterly&key=%s" % apikey
                    if script not in s3_scripts:
                        s3_scripts.append(script)
                    if "StreetviewButton" in ldict:
                        # Streetview doesn't work with v2 API
                        ldict["StreetviewButton"] = str(T("Click where you want to open Streetview"))
                        ldict["StreetviewTitle"] = str(T("Street View"))
                        if debug:
                            self.scripts.append("gis/gxp/widgets/GoogleStreetViewPanel.js")
                        else:
                            self.scripts.append("gis/gxp/widgets/GoogleStreetViewPanel.min.js")

            if options:
                # Used by Map._setup()
                options[self.dictname] = ldict
        else:
            ldict = None

        # Used by as_json() and hence as_javascript()
        return ldict

# -----------------------------------------------------------------------------
class LayerGPX(Layer):
    """
        GPX Layers from Catalogue
    """

    tablename = "gis_layer_gpx"
    dictname = "layers_gpx"
    style = True

    # -------------------------------------------------------------------------
    class SubLayer(Layer.SubLayer):
        def as_dict(self):
            url = URL(c="default", f="download",
                      args=self.track)

            # Mandatory attributes
            output = {"id": self.layer_id,
                      "name": self.safe_name,
                      "url": url,
                      }

            # Attributes which are defaulted client-side if not set
            self.marker.add_attributes_to_output(output)
            self.add_attributes_if_not_default(
                output,
                waypoints = (self.waypoints, (True,)),
                tracks = (self.tracks, (True,)),
                routes = (self.routes, (True,)),
            )
            self.setup_folder_visibility_and_opacity(output)
            self.setup_clustering(output)
            return output

# -----------------------------------------------------------------------------
class LayerJS(Layer):
    """
        JS Layers from Catalogue
        - these are raw Javascript layers for use by expert OpenLayers people
          to quickly add/configure new data sources without needing support
          from back-end Sahana programmers
    """

    tablename = "gis_layer_js"
    dictname = "layers_js"
    style = False

    # -------------------------------------------------------------------------
    def as_dict(self, options=None):

        sublayer_dicts = []

        sublayers = self.sublayers
        if sublayers:
            append = sublayer_dicts.append
            for sublayer in sublayers:
                append(sublayer.code)
            if options:
                # Used by Map._setup()
                options[self.dictname] = sublayer_dicts
        else:
            sublayer_dicts = []

        # Used by as_json() and hence as_javascript()
        return sublayer_dicts

# -----------------------------------------------------------------------------
class LayerKML(Layer):
    """
        KML Layers from Catalogue
    """

    tablename = "gis_layer_kml"
    dictname = "layers_kml"
    style = True

    # -------------------------------------------------------------------------
    def __init__(self, all_layers, openlayers=6, init=True):
        "Set up the KML cache, should be done once per request"

        super().__init__(all_layers, openlayers)

        # Can we cache downloaded KML feeds?
        # Needed for unzipping & filtering as well
        # @ToDo: Should we move this folder to static to speed up access to cached content?
        #           Do we need to secure it?
        request = current.request
        cachepath = os.path.join(request.folder,
                                 "uploads",
                                 "gis_cache")

        if os.path.exists(cachepath):
            cacheable = os.access(cachepath, os.W_OK)
        else:
            try:
                os.mkdir(cachepath)
            except OSError as os_error:
                current.log.error("GIS: KML layers cannot be cached: %s %s" % \
                                  (cachepath, os_error))
                cacheable = False
            else:
                cacheable = True
        # @ToDo: Migrate to gis_cache
        LayerKML.cachetable = current.s3db.gis_cache2
        LayerKML.cacheable = cacheable
        LayerKML.cachepath = cachepath

    # -------------------------------------------------------------------------
    class SubLayer(Layer.SubLayer):
        def as_dict(self):
            db = current.db
            request = current.request

            cachetable = LayerKML.cachetable
            cacheable = LayerKML.cacheable
            #cachepath = LayerKML.cachepath

            name = self.name
            if cacheable:
                _name = urllib_quote(name)
                _name = _name.replace("%", "_")
                filename = "%s.file.%s.kml" % (cachetable._tablename,
                                               _name)


                # Should we download a fresh copy of the source file?
                download = True
                query = (cachetable.name == name)
                cached = db(query).select(cachetable.modified_on,
                                          limitby = (0, 1)).first()
                refresh = self.refresh or 900 # 15 minutes set if we have no data (legacy DB)
                if cached:
                    modified_on = cached.modified_on
                    cutoff = modified_on + datetime.timedelta(seconds=refresh)
                    if request.utcnow < cutoff:
                        download = False

                if download:
                    # Download file (async, if workers alive)
                    response = current.response
                    session_id_name = response.session_id_name
                    session_id = response.session_id
                    current.s3task.run_async("gis_download_kml",
                                             args = [self.id,
                                                     filename,
                                                     session_id_name,
                                                     session_id,
                                                     ])
                    if cached:
                        db(query).update(modified_on=request.utcnow)
                    else:
                        cachetable.insert(name=name, file=filename)

                url = URL(c="default", f="download",
                          args=[filename])
            else:
                # No caching possible (e.g. GAE), display file direct from remote (using Proxy)
                # (Requires OpenLayers.Layer.KML to be available)
                url = self.url

            # Mandatory attributes
            output = {"id": self.layer_id,
                      "name": self.safe_name,
                      "url": url,
                      }

            # Attributes which are defaulted client-side if not set
            self.add_attributes_if_not_default(
                output,
                title = (self.title, ("name", None, "")),
                body = (self.body, ("description", None)),
                refresh = (self.refresh, (900,)),
            )
            self.setup_folder_visibility_and_opacity(output)
            self.setup_clustering(output)
            if self.style:
                output["style"] = self.style
            else:
                self.marker.add_attributes_to_output(output)

            return output

# -----------------------------------------------------------------------------
class LayerOSM(Layer):
    """
        OpenStreetMap Layers from Catalogue

        @ToDo: Provide a catalogue of standard layers which are fully-defined
               in static & can just have name over-ridden, as well as
               fully-custom layers.
    """

    tablename = "gis_layer_openstreetmap"
    dictname = "layers_osm"
    style = False

    # -------------------------------------------------------------------------
    class SubLayer(Layer.SubLayer):
        def as_dict(self):

            if Projection().epsg not in (3857, 900913):
                # Cannot display OpenStreetMap layers unless we're using the Spherical Mercator Projection
                return {}

            if self.openlayers == 6:
                # Mandatory attributes
                output = {#"id": self.layer_id,
                          #"name": self.safe_name,
                          #"url": self.url1,
                          }

                # Attributes which are defaulted client-side if not set
                url = self.url1
                if not url.endswith("png"):
                    # Convert legacy URL format
                    url = "%s{z}/{x}/{y}.png" % url
                    if self.url2:
                        url = url.replace("/a.", "/{a-c}.")

                self.add_attributes_if_not_default(
                    output,
                    base = (self.base, (True,)),
                    _base = (self._base, (False,)),
                    url = (url, ("https://{a-c}.tile.openstreetmap.org/{z}/{x}/{y}.png",)),
                    maxZoom = (self.zoom_levels, (19,)),
                    attribution = (self.attribution and self.attribution.replace("\"", "'"), (None,)),
                )
            else:
                # OpenLayers 2.13
                output = {"id": self.layer_id,
                          "name": self.safe_name,
                          "url1": self.url1,
                          }

                # Attributes which are defaulted client-side if not set
                self.add_attributes_if_not_default(
                    output,
                    base = (self.base, (True,)),
                    _base = (self._base, (False,)),
                    url2 = (self.url2, ("",)),
                    url3 = (self.url3, ("",)),
                    zoomLevels = (self.zoom_levels, (19,)),
                    attribution = (self.attribution, (None,)),
                )

            self.setup_folder_and_visibility(output)

            return output

# -----------------------------------------------------------------------------
class LayerOpenWeatherMap(Layer):
    """
       OpenWeatherMap Layers from Catalogue
    """

    tablename = "gis_layer_openweathermap"
    dictname = "layers_openweathermap"
    style = False

    # -------------------------------------------------------------------------
    def as_dict(self, options=None):

        sublayers = self.sublayers
        if sublayers:
            apikey = current.deployment_settings.get_gis_api_openweathermap()
            if not apikey:
                # Raising exception prevents gis/index view from loading
                # - logging the error should suffice?
                #raise Exception("Cannot display OpenWeatherMap layers unless we have an API key\n")
                current.log.error("Cannot display OpenWeatherMap layers unless we have an API key")
                return {}
            current.response.s3.js_global.append("S3.gis.openweathermap='%s'" % apikey)
            ldict = {}
            for sublayer in sublayers:
                ldict[sublayer.type] = {"name": sublayer.name,
                                        "id": sublayer.layer_id,
                                        "dir": sublayer.dir,
                                        "visibility": sublayer.visible
                                        }
            if options:
                # Used by Map._setup()
                options[self.dictname] = ldict
        else:
            ldict = None

        # Used by as_json() and hence as_javascript()
        return ldict

# -----------------------------------------------------------------------------
class LayerShapefile(Layer):
    """
        Shapefile Layers from Catalogue
    """

    tablename = "gis_layer_shapefile"
    dictname = "layers_shapefile"
    style = True

    # -------------------------------------------------------------------------
    class SubLayer(Layer.SubLayer):
        def as_dict(self):
            url = "%s/%s/data.geojson" % \
                (URL(c="gis", f="layer_shapefile"), self.id)
            if self.filter:
                url = "%s?layer_shapefile_%s.%s" % (url, self.id, self.filter)

            # Mandatory attributes
            output = {"id": self.layer_id,
                      "type": "shapefile",
                      "name": self.safe_name,
                      "url": url,
                      # Shapefile layers don't alter their contents, so don't refresh
                      "refresh": 0,
                      }

            # Attributes which are defaulted client-side if not set
            self.add_attributes_if_not_default(
                output,
                desc = (self.description, (None, "")),
                src = (self.source_name, (None, "")),
                src_url = (self.source_url, (None, "")),
            )
            # We convert on-upload to have BBOX handling work properly
            #projection = self.projection
            #if projection.epsg != 4326:
            #    output["projection"] = projection.epsg
            self.setup_folder_visibility_and_opacity(output)
            self.setup_clustering(output)
            if self.style:
                output["style"] = self.style
            else:
                self.marker.add_attributes_to_output(output)

            return output

# -----------------------------------------------------------------------------
class LayerTheme(Layer):
    """
        Theme Layers from Catalogue
    """

    tablename = "gis_layer_theme"
    dictname = "layers_theme"
    style = True

    # -------------------------------------------------------------------------
    class SubLayer(Layer.SubLayer):
        def as_dict(self):
            url = "%s.geojson?theme_data.layer_theme_id=%i&polygons=1&maxdepth=0" % \
                (URL(c="gis", f="theme_data"), self.id)

            # Mandatory attributes
            output = {"id": self.layer_id,
                      "type": "theme",
                      "name": self.safe_name,
                      "url": url,
                      }

            # Attributes which are defaulted client-side if not set
            self.setup_folder_visibility_and_opacity(output)
            self.setup_clustering(output)
            style = self.style
            if style:
                output["style"] = style

            return output

# -----------------------------------------------------------------------------
class LayerTMS(Layer):
    """
        TMS Layers from Catalogue
    """

    tablename = "gis_layer_tms"
    dictname = "layers_tms"
    style = False

    # -------------------------------------------------------------------------
    class SubLayer(Layer.SubLayer):
        def as_dict(self):
            # Mandatory attributes
            output = {"id": self.layer_id,
                      "type": "tms",
                      "name": self.safe_name,
                      "url": self.url,
                      "layername": self.layername
                      }

            # Attributes which are defaulted client-side if not set
            self.add_attributes_if_not_default(
                output,
                _base = (self._base, (False,)),
                url2 = (self.url2, (None,)),
                url3 = (self.url3, (None,)),
                format = (self.img_format, ("png", None)),
                zoomLevels = (self.zoom_levels, (19,)),
                attribution = (self.attribution, (None,)),
            )
            self.setup_folder(output)
            return output

# -----------------------------------------------------------------------------
class LayerWFS(Layer):
    """
        WFS Layers from Catalogue
    """

    tablename = "gis_layer_wfs"
    dictname = "layers_wfs"
    style = True

    # -------------------------------------------------------------------------
    class SubLayer(Layer.SubLayer):
        def as_dict(self):
            # Mandatory attributes
            output = {"id": self.layer_id,
                      "name": self.safe_name,
                      "url": self.url,
                      "title": self.title,
                      "featureType": self.featureType,
                      }

            # Attributes which are defaulted client-side if not set
            self.add_attributes_if_not_default(
                output,
                version = (self.version, ("1.1.0",)),
                featureNS = (self.featureNS, (None, "")),
                geometryName = (self.geometryName, ("the_geom",)),
                schema = (self.wfs_schema, (None, "")),
                username = (self.username, (None, "")),
                password = (self.password, (None, "")),
                projection = (self.projection.epsg, (4326,)),
                desc = (self.description, (None, "")),
                src = (self.source_name, (None, "")),
                src_url = (self.source_url, (None, "")),
                refresh = (self.refresh, (0,)),
                #editable
            )
            self.setup_folder_visibility_and_opacity(output)
            self.setup_clustering(output)
            if self.style:
                output["style"] = self.style
            else:
                self.marker.add_attributes_to_output(output)

            return output

# -----------------------------------------------------------------------------
class LayerWMS(Layer):
    """
        WMS Layers from Catalogue
    """

    tablename = "gis_layer_wms"
    dictname = "layers_wms"
    style = False

    # -------------------------------------------------------------------------
    def __init__(self, all_layers, openlayers=6):
        super().__init__(all_layers, openlayers)
        if self.sublayers:
            if current.response.s3.debug:
                self.scripts.append("gis/gxp/plugins/WMSGetFeatureInfo.js")
            else:
                self.scripts.append("gis/gxp/plugins/WMSGetFeatureInfo.min.js")

    # -------------------------------------------------------------------------
    class SubLayer(Layer.SubLayer):
        def as_dict(self):
            if self.queryable:
                current.response.s3.gis.get_feature_info = True
            # Mandatory attributes
            output = {"id": self.layer_id,
                      "name": self.safe_name,
                      "url": self.url,
                      "layers": self.layers,
                      }

            # Attributes which are defaulted client-side if not set
            legend_url = self.legend_url
            if legend_url and not legend_url.startswith("http"):
                legend_url = "%s/%s%s" % \
                    (current.deployment_settings.get_base_public_url(),
                     current.request.application,
                     legend_url)
            attr = {"transparent": (self.transparent, (True,)),
                    "version": (self.version, ("1.1.1",)),
                    "format": (self.img_format, ("image/png",)),
                    "map": (self.map, (None, "")),
                    "username": (self.username, (None, "")),
                    "password": (self.password, (None, "")),
                    "buffer": (self.buffer, (0,)),
                    "base": (self.base, (False,)),
                    "_base": (self._base, (False,)),
                    "style": (self.style, (None, "")),
                    "bgcolor": (self.bgcolor, (None, "")),
                    "tiled": (self.tiled, (False,)),
                    "singleTile": (self.single_tile, (False,)),
                    "legendURL": (legend_url, (None, "")),
                    "queryable": (self.queryable, (False,)),
                    "desc": (self.description, (None, "")),
                    }

            if current.deployment_settings.get_gis_layer_metadata():
                # Use CMS to add info about sources
                attr["post_id"] = (self.post_id, (None, ""))
            else:
                # Link direct to sources
                attr.update(src = (self.source_name, (None, "")),
                            src_url = (self.source_url, (None, "")),
                            )

            self.add_attributes_if_not_default(output, **attr)
            self.setup_folder_visibility_and_opacity(output)

            return output

# -----------------------------------------------------------------------------
class LayerXYZ(Layer):
    """
        XYZ Layers from Catalogue
    """

    tablename = "gis_layer_xyz"
    dictname = "layers_xyz"
    style = False

    # -------------------------------------------------------------------------
    class SubLayer(Layer.SubLayer):
        def as_dict(self):
            # Mandatory attributes
            output = {"id": self.layer_id,
                      "name": self.safe_name,
                      "url": self.url
                      }

            # Attributes which are defaulted client-side if not set
            self.add_attributes_if_not_default(
                output,
                _base = (self._base, (False,)),
                url2 = (self.url2, (None,)),
                url3 = (self.url3, (None,)),
                format = (self.img_format, ("png", None)),
                zoomLevels = (self.zoom_levels, (19,)),
                attribution = (self.attribution, (None,)),
            )
            self.setup_folder(output)
            return output

# END =========================================================================
