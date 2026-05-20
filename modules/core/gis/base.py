"""
    GIS Module

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

__all__ = ("GIS",
           )

import datetime
import json
import os
import sys

from collections import OrderedDict
from http import cookies as Cookie
from io import StringIO
from lxml import etree
from urllib.error import HTTPError, URLError

from gluon import current, redirect, HTTP, URL, IS_EMPTY_OR, IS_IN_SET
from gluon.fileutils import parse_version
from gluon.languages import lazyT
from gluon.settings import global_settings
from gluon.storage import Storage

from s3dal import Rows

from ..tools import JSONSEPARATORS, S3Trackable, s3_str

KML_NAMESPACE = "http://earth.google.com/kml/2.2"

# Map WKT types to db types
GEOM_TYPES = {"point": 1,
              "linestring": 2,
              "polygon": 3,
              "multipoint": 4,
              "multilinestring": 5,
              "multipolygon": 6,
              "geometrycollection": 7,
              }

# km
RADIUS_EARTH = 6371.01

# Garmin GPS Symbols
GPS_SYMBOLS = ("Airport",
               "Amusement Park"
               "Ball Park",
               "Bank",
               "Bar",
               "Beach",
               "Bell",
               "Boat Ramp",
               "Bowling",
               "Bridge",
               "Building",
               "Campground",
               "Car",
               "Car Rental",
               "Car Repair",
               "Cemetery",
               "Church",
               "Circle with X",
               "City (Capitol)",
               "City (Large)",
               "City (Medium)",
               "City (Small)",
               "Civil",
               "Contact, Dreadlocks",
               "Controlled Area",
               "Convenience Store",
               "Crossing",
               "Dam",
               "Danger Area",
               "Department Store",
               "Diver Down Flag 1",
               "Diver Down Flag 2",
               "Drinking Water",
               "Exit",
               "Fast Food",
               "Fishing Area",
               "Fitness Center",
               "Flag",
               "Forest",
               "Gas Station",
               "Geocache",
               "Geocache Found",
               "Ghost Town",
               "Glider Area",
               "Golf Course",
               "Green Diamond",
               "Green Square",
               "Heliport",
               "Horn",
               "Hunting Area",
               "Information",
               "Levee",
               "Light",
               "Live Theater",
               "Lodging",
               "Man Overboard",
               "Marina",
               "Medical Facility",
               "Mile Marker",
               "Military",
               "Mine",
               "Movie Theater",
               "Museum",
               "Navaid, Amber",
               "Navaid, Black",
               "Navaid, Blue",
               "Navaid, Green",
               "Navaid, Green/Red",
               "Navaid, Green/White",
               "Navaid, Orange",
               "Navaid, Red",
               "Navaid, Red/Green",
               "Navaid, Red/White",
               "Navaid, Violet",
               "Navaid, White",
               "Navaid, White/Green",
               "Navaid, White/Red",
               "Oil Field",
               "Parachute Area",
               "Park",
               "Parking Area",
               "Pharmacy",
               "Picnic Area",
               "Pizza",
               "Police Station",
               "Post Office",
               "Private Field",
               "Radio Beacon",
               "Red Diamond",
               "Red Square",
               "Residence",
               "Restaurant",
               "Restricted Area",
               "Restroom",
               "RV Park",
               "Scales",
               "Scenic Area",
               "School",
               "Seaplane Base",
               "Shipwreck",
               "Shopping Center",
               "Short Tower",
               "Shower",
               "Skiing Area",
               "Skull and Crossbones",
               "Soft Field",
               "Stadium",
               "Summit",
               "Swimming Area",
               "Tall Tower",
               "Telephone",
               "Toll Booth",
               "TracBack Point",
               "Trail Head",
               "Truck Stop",
               "Tunnel",
               "Ultralight Area",
               "Water Hydrant",
               "Waypoint",
               "White Buoy",
               "White Dot",
               "Zoo"
               )

DEFAULT = lambda: None

# -----------------------------------------------------------------------------
class GIS:
    """
        GeoSpatial functions
    """

    # Used to disable location tree updates during prepopulate.
    # It is not appropriate to use auth.override for this, as there are times
    # (e.g. during tests) when auth.override is turned on, but location tree
    # updates should still be enabled.
    disable_update_location_tree = False

    def __init__(self):
        messages = current.messages
        #messages.centroid_error = str(A("Shapely", _href="http://pypi.python.org/pypi/Shapely/", _target="_blank")) + " library not found, so can't find centroid!"
        messages.centroid_error = "Shapely library not functional, so can't find centroid! Install Geos & Shapely for Line/Polygon support"
        messages.unknown_type = "Unknown Type!"
        messages.invalid_wkt_point = "Invalid WKT: must be like POINT (3 4)"
        messages.invalid_wkt = "Invalid WKT: see http://en.wikipedia.org/wiki/Well-known_text"
        messages.lon_empty = "Invalid: Longitude can't be empty if Latitude specified!"
        messages.lat_empty = "Invalid: Latitude can't be empty if Longitude specified!"
        messages.unknown_parent = "Invalid: %(parent_id)s is not a known Location"
        self.DEFAULT_SYMBOL = "White Dot"
        self.hierarchy_level_keys = ("L0", "L1", "L2", "L3", "L4", "L5")
        self.hierarchy_levels = {}
        self.max_allowed_level_num = 4

        self.relevant_hierarchy_levels = None

        #self.google_geocode_retry = True

    # -------------------------------------------------------------------------
    @staticmethod
    def gps_symbols():
        return GPS_SYMBOLS

    # -------------------------------------------------------------------------
    def download_kml(self, record_id, filename, session_id_name, session_id):
        """
            Download a KML file:
                - unzip it if-required
                - follow NetworkLinks recursively if-required

            Save the file to the /uploads folder

            Designed to be called asynchronously using:
                current.s3task.run_async("download_kml", [record_id, filename])

            Args:
                record_id: id of the record in db.gis_layer_kml
                filename: name to save the file as
                session_id_name: name of the session
                session_id: id of the session

            TODO Pass error messages to Result & have JavaScript listen for these
        """

        table = current.s3db.gis_layer_kml
        record = current.db(table.id == record_id).select(table.url,
                                                          limitby = (0, 1)
                                                          ).first()
        url = record.url

        filepath = os.path.join(global_settings.applications_parent,
                                current.request.folder,
                                "uploads",
                                "gis_cache",
                                filename)

        warning = self.fetch_kml(url, filepath, session_id_name, session_id)

        # @ToDo: Handle errors
        #query = (cachetable.name == name)
        if "URLError" in warning or "HTTPError" in warning:
            # URL inaccessible
            if os.access(filepath, os.R_OK):
                statinfo = os.stat(filepath)
                if statinfo.st_size:
                    # Use cached version
                    #date = db(query).select(cachetable.modified_on,
                    #                        limitby = (0, 1)).first().modified_on
                    #response.warning += "%s %s %s\n" % (url,
                    #                                    T("not accessible - using cached version from"),
                    #                                    str(date))
                    #url = URL(c="default", f="download",
                    #          args=[filename])
                    pass
                else:
                    # 0k file is all that is available
                    #response.warning += "%s %s\n" % (url,
                    #                                 T("not accessible - no cached version available!"))
                    # skip layer
                    return
            else:
                # No cached version available
                #response.warning += "%s %s\n" % (url,
                #                                 T("not accessible - no cached version available!"))
                # skip layer
                return
        else:
            # Download was succesful
            #db(query).update(modified_on=request.utcnow)
            if "ParseError" in warning:
                # @ToDo Parse detail
                #response.warning += "%s: %s %s\n" % (T("Layer"),
                #                                     name,
                #                                     T("couldn't be parsed so NetworkLinks not followed."))
                pass
            if "GroundOverlay" in warning or "ScreenOverlay" in warning:
                #response.warning += "%s: %s %s\n" % (T("Layer"),
                #                                     name,
                #                                     T("includes a GroundOverlay or ScreenOverlay which aren't supported in OpenLayers yet, so it may not work properly."))
                # Code to support GroundOverlay:
                # https://github.com/openlayers/openlayers/pull/759
                pass

    # -------------------------------------------------------------------------
    def fetch_kml(self, url, filepath, session_id_name, session_id):
        """
            Fetch a KML file:
                - unzip it if-required
                - follow NetworkLinks recursively if-required
            Designed as a helper function for download_kml()

            Returns:
                a file object
        """

        from gluon.tools import fetch

        response = current.response
        public_url = current.deployment_settings.get_base_public_url()

        warning = ""

        local = False
        if not url.startswith("http"):
            local = True
            url = "%s%s" % (public_url, url)
        elif len(url) > len(public_url) and url[:len(public_url)] == public_url:
            local = True
        if local:
            # Keep Session for local URLs
            cookie = Cookie.SimpleCookie()
            cookie[session_id_name] = session_id
            # For sync connections
            current.session._unlock(response)
            try:
                file = fetch(url, cookie=cookie)
            except HTTPError:
                warning = "HTTPError"
                return warning
            except URLError:
                warning = "URLError"
                return warning
        else:
            try:
                file = fetch(url)
            except HTTPError:
                warning = "HTTPError"
                return warning
            except URLError:
                warning = "URLError"
                return warning

        filenames = []
        if file[:2] == "PK":
            # Unzip
            fp = StringIO(file)
            import zipfile
            myfile = zipfile.ZipFile(fp)
            files = myfile.infolist()
            main = None
            candidates = []
            for _file in files:
                filename = _file.filename
                if filename == "doc.kml":
                    main = filename
                elif filename[-4:] == ".kml":
                    candidates.append(filename)
            if not main:
                if candidates:
                    # Any better way than this to guess which KML file is the main one?
                    main = candidates[0]
                else:
                    response.error = "KMZ contains no KML Files!"
                    return ""
            # Write files to cache (other than the main one)
            request = current.request
            path = os.path.join(request.folder, "static", "cache", "kml")
            if not os.path.exists(path):
                os.makedirs(path)
            for _file in files:
                filename = _file.filename
                if filename != main:
                    if "/" in filename:
                        _filename = filename.split("/")
                        dir = os.path.join(path, _filename[0])
                        if not os.path.exists(dir):
                            os.mkdir(dir)
                        _filepath = os.path.join(path, *_filename)
                    else:
                        _filepath = os.path.join(path, filename)

                    try:
                        f = open(_filepath, "wb")
                    except:
                        # Trying to write the Folder
                        pass
                    else:
                        filenames.append(filename)
                        __file = myfile.read(filename)
                        f.write(__file)
                        f.close()

            # Now read the main one (to parse)
            file = myfile.read(main)
            myfile.close()

        # Check for NetworkLink
        if "<NetworkLink>" in file:
            try:
                # Remove extraneous whitespace
                parser = etree.XMLParser(recover=True, remove_blank_text=True)
                tree = etree.XML(file, parser)
                # Find contents of href tag (must be a better way?)
                url = ""
                for element in tree.iter():
                    if element.tag == "{%s}href" % KML_NAMESPACE:
                        url = element.text
                if url:
                    # Follow NetworkLink (synchronously)
                    warning2 = self.fetch_kml(url, filepath, session_id_name, session_id)
                    warning += warning2
            except (etree.XMLSyntaxError,):
                e = sys.exc_info()[1]
                warning += "<ParseError>%s %s</ParseError>" % (e.line, e.errormsg)

        # Check for Overlays
        if "<GroundOverlay>" in file:
            warning += "GroundOverlay"
        if "<ScreenOverlay>" in file:
            warning += "ScreenOverlay"

        for filename in filenames:
            replace = "%s/%s" % (URL(c="static", f="cache", args=["kml"]),
                                 filename)
            # Rewrite all references to point to the correct place
            # need to catch <Icon><href> (which could be done via lxml)
            # & also <description><![CDATA[<img src=" (which can't)
            file = file.replace(filename, replace)

        # Write main file to cache
        f = open(filepath, "w")
        f.write(file)
        f.close()

        return warning

    # -------------------------------------------------------------------------
    @staticmethod
    def geocode(address, postcode=None, Lx_ids=None, geocoder=None):
        """
            Geocode an Address
            - used by LocationSelector
                      settings.get_gis_geocode_imported_addresses

            Args:
                address: street address
                postcode: postcode
                Lx_ids: list of ancestor IDs
                geocoder: which geocoder service to use
        """

        try:
            from geopy import geocoders
        except ImportError:
            current.log.error("S3GIS unresolved dependency: geopy required for Geocoder support")
            return "S3GIS unresolved dependency: geopy required for Geocoder support"

        settings = current.deployment_settings
        if geocoder is None:
            geocoder = settings.get_gis_geocode_service()

        if geocoder == "nominatim":
            g = geocoders.Nominatim(user_agent = "Sahana Eden")
        elif geocoder == "geonames":
            username = settings.get_gis_api_google()
            if not username:
                current.log.error("Geocoder: No Username defined for GeoNames")
                return "No Username"
            g = geocoders.GeoNames(username = username)
        elif geocoder == "google":
            api_key = settings.get_gis_geonames_username()
            if not api_key:
                current.log.error("Geocoder: No API Key defined for Google")
                return "No API Key"
            g = geocoders.GoogleV3(api_key = api_key)
            #if current.gis.google_geocode_retry:
            #    # Retry when reaching maximum requests per second
            #    import time
            #    from geopy.geocoders.googlev3 import GTooManyQueriesError
            #    def geocode_(names, g=g, **kwargs):
            #        attempts = 0
            #        while attempts < 3:
            #            try:
            #                result = g.geocode(names, **kwargs)
            #            except GTooManyQueriesError:
            #                if attempts == 2:
            #                    # Daily limit reached
            #                    current.gis.google_geocode_retry = False
            #                    raise
            #                time.sleep(1)
            #            else:
            #                break
            #            attempts += 1
            #        return result
            #else:
        elif callable(geocoder):
            # A custom class
            g = geocoder()
        else:
            raise NotImplementedError

        geocode_ = lambda names, inst=g, **kwargs: inst.geocode(names, **kwargs)

        location = address
        if postcode:
            location = "%s,%s" % (location, postcode)

        Lx = L5 = L4 = L3 = L2 = L1 = L0 = None
        if Lx_ids:
            # Convert Lx IDs to Names
            table = current.s3db.gis_location
            limit = len(Lx_ids)
            if limit > 1:
                query = (table.id.belongs(Lx_ids))
            else:
                query = (table.id == Lx_ids[0])
            db = current.db
            Lx = db(query).select(table.id,
                                  table.name,
                                  table.level,
                                  table.gis_feature_type,
                                  # Better as separate query
                                  #table.lon_min,
                                  #table.lat_min,
                                  #table.lon_max,
                                  #table.lat_max,
                                  # Better as separate query
                                  #table.wkt,
                                  limitby=(0, limit),
                                  orderby=~table.level
                                  )
            if Lx:
                Lx_names = ",".join([l.name for l in Lx])
                location = "%s,%s" % (location, Lx_names)
                for l in Lx:
                    if l.level == "L0":
                        L0 = l.id
                        continue
                    elif l.level == "L1":
                        L1 = l.id
                        continue
                    elif l.level == "L2":
                        L2 = l.id
                        continue
                    elif l.level == "L3":
                        L3 = l.id
                        continue
                    elif l.level == "L4":
                        L4 = l.id
                        continue
                    elif l.level == "L5":
                        L5 = l.id
                Lx = Lx.as_dict()

        try:
            results = geocode_(location, exactly_one=False)
        except:
            error = sys.exc_info()[1]
            output = str(error)
        else:
            if results is None:
                output = "No results found"
            elif len(results) > 1:
                output = "Multiple results found"
                # @ToDo: Iterate through the results to see if just 1 is within the right bounds
            else:
                place, (lat, lon) = results[0]
                if Lx:
                    output = None
                    # Check Results are for a specific address & not just that for the City
                    results = geocode_(Lx_names, exactly_one=False)
                    if not results:
                        output = "Can't check that these results are specific enough"
                    for result in results:
                        place2 = result[0]
                        if place == place2:
                            output = "We can only geocode to the Lx"
                            break
                    if not output:
                        # Check Results are within relevant bounds
                        L0_row = None
                        wkt = None
                        if L5 and Lx[L5]["gis_feature_type"] != 1:
                            wkt = db(table.id == L5).select(table.wkt,
                                                            limitby = (0, 1)
                                                            ).first().wkt
                            used_Lx = L5
                        elif L4 and Lx[L4]["gis_feature_type"] != 1:
                            wkt = db(table.id == L4).select(table.wkt,
                                                            limitby = (0, 1)
                                                            ).first().wkt
                            used_Lx = L4
                        elif L3 and Lx[L3]["gis_feature_type"] != 1:
                            wkt = db(table.id == L3).select(table.wkt,
                                                            limitby = (0, 1)
                                                            ).first().wkt
                            used_Lx = L3
                        elif L2 and Lx[L2]["gis_feature_type"] != 1:
                            wkt = db(table.id == L2).select(table.wkt,
                                                            limitby = (0, 1)
                                                            ).first().wkt
                            used_Lx = L2
                        elif L1 and Lx[L1]["gis_feature_type"] != 1:
                            wkt = db(table.id == L1).select(table.wkt,
                                                            limitby = (0, 1)
                                                            ).first().wkt
                            used_Lx = L1
                        elif L0:
                            L0_row = db(table.id == L0).select(table.wkt,
                                                               table.lon_min,
                                                               table.lat_min,
                                                               table.lon_max,
                                                               table.lat_max,
                                                               limitby = (0, 1)
                                                               ).first()
                            if not L0_row.wkt.startswith("POI"): # Point
                                wkt = L0_row.wkt
                            used_Lx = L0
                        if wkt:
                            from shapely.geometry import point
                            from shapely.wkt import loads as wkt_loads
                            try:
                                # Enable C-based speedups available from 1.2.10+
                                from shapely import speedups
                                speedups.enable()
                            except:
                                current.log.info("S3GIS",
                                                 "Upgrade Shapely for Performance enhancements")
                            test = point.Point(lon, lat)
                            shape = wkt_loads(wkt)
                            ok = test.intersects(shape)
                            if not ok:
                                output = "Returned value not within %s" % Lx[used_Lx]["name"]
                        elif L0:
                            # Check within country at least
                            if not L0_row:
                                L0_row = db(table.id == L0).select(table.lon_min,
                                                                   table.lat_min,
                                                                   table.lon_max,
                                                                   table.lat_max,
                                                                   limitby = (0, 1)
                                                                   ).first()
                            if lat < L0_row["lat_max"] and \
                               lat > L0_row["lat_min"] and \
                               lon < L0_row["lon_max"] and \
                               lon > L0_row["lon_min"]:
                                ok = True
                            else:
                                ok = False
                                output = "Returned value not within %s" % Lx["name"]
                        else:
                            # We'll just have to trust it!
                            ok = True
                        if ok:
                            output = {"lat": lat,
                                      "lon": lon,
                                      }
                else:
                    # We'll just have to trust it!
                    output = {"lat": lat,
                              "lon": lon,
                              }

        return output

    # -------------------------------------------------------------------------
    @staticmethod
    def geocode_r(lat, lon):
        """
            Reverse Geocode a Lat/Lon
            - used by LocationSelector
        """

        if lat is None or lon is None:
            return "Need Lat & Lon"

        results = ""
        # Check vaguely valid
        try:
            lat = float(lat)
        except ValueError:
            results = "Latitude is Invalid!"
        try:
            lon = float(lon)
        except ValueError:
            results += "Longitude is Invalid!"

        if not results:
            if lon > 180 or lon < -180:
                results = "Longitude must be between -180 & 180!"
            elif lat > 90 or lat < -90:
                results = "Latitude must be between -90 & 90!"
            else:
                table = current.s3db.gis_location
                query = (table.level != None) & \
                        (table.deleted == False)
                if current.deployment_settings.get_gis_spatialdb():
                    point = "POINT (%s %s)" % (lon, lat)
                    query &= (table.the_geom.st_intersects(point))
                    rows = current.db(query).select(table.id,
                                                    table.level,
                                                    )
                    results = {}
                    for row in rows:
                        results[row.level] = row.id
                else:
                    # Oh dear, this is going to be slow :/
                    # Filter to the BBOX initially
                    query &= (table.lat_min < lat) & \
                             (table.lat_max > lat) & \
                             (table.lon_min < lon) & \
                             (table.lon_max > lon)
                    rows = current.db(query).select(table.id,
                                                    table.level,
                                                    table.wkt,
                                                    )
                    from shapely.geometry import point
                    from shapely.wkt import loads as wkt_loads
                    test = point.Point(lon, lat)
                    results = {}
                    for row in rows:
                        shape = wkt_loads(row.wkt)
                        ok = test.intersects(shape)
                        if ok:
                            #sys.stderr.write("Level: %s, id: %s\n" % (row.level, row.id))
                            results[row.level] = row.id
        return results

    # -------------------------------------------------------------------------
    @staticmethod
    def get_bearing(lat_start, lon_start, lat_end, lon_end):
        """
            Given a Start & End set of Coordinates, return a Bearing
            Formula from: http://www.movable-type.co.uk/scripts/latlong.html
        """

        import math

        # shortcuts
        cos = math.cos
        sin = math.sin

        delta_lon = lon_start - lon_end
        bearing = math.atan2(sin(delta_lon) * cos(lat_end),
                             (cos(lat_start) * sin(lat_end)) - \
                             (sin(lat_start) * cos(lat_end) * cos(delta_lon))
                             )
        # Convert to a compass bearing
        bearing = (bearing + 360) % 360

        return bearing

    # -------------------------------------------------------------------------
    def get_bounds(self,
                   features = None,
                   bbox_min_size = None,
                   bbox_inset = None):
        """
            Calculate the Bounds of a list of Point Features, suitable for
            setting map bounds. If no features are supplied, the current map
            configuration bounds will be returned.
            e.g. When a map is displayed that focuses on a collection of points,
                 the map is zoomed to show just the region bounding the points.
            e.g. To use in GPX export for correct zooming
`
            Ensure a minimum size of bounding box, and that the points
            are inset from the border.

            Args:
                features: A list of point features
                bbox_min_size: Minimum bounding box - gives a minimum width
                               and height in degrees for the region shown.
                               Without this, a map showing a single point would
                               not show any extent around that point.
                bbox_inset: Bounding box insets - adds a small amount of
                            distance outside the points.
                            Without this, the outermost points would be on the
                            bounding box, and might not be visible.

            Returns:
                An appropriate map bounding box, as a dict:
                   {"lon_min": lon_min, "lat_min": lat_min,
                    "lon_max": lon_max, "lat_max": lat_max}

            TODO Support Polygons (separate function?)
        """

        if features:

            lon_min = 180
            lat_min = 90
            lon_max = -180
            lat_max = -90

            # Is this a simple feature set or the result of a join?
            try:
                lon = features[0].lon
                simple = True
            except (AttributeError, KeyError):
                simple = False

            # @ToDo: Optimised Geospatial routines rather than this crude hack
            for feature in features:

                try:
                    if simple:
                        lon = feature.lon
                        lat = feature.lat
                    else:
                        # A Join
                        lon = feature.gis_location.lon
                        lat = feature.gis_location.lat
                except AttributeError:
                    # Skip any rows without the necessary lat/lon fields
                    continue

                # Also skip those set to None. Note must use explicit test,
                # as zero is a legal value.
                if lon is None or lat is None:
                    continue

                lon_min = min(lon, lon_min)
                lat_min = min(lat, lat_min)
                lon_max = max(lon, lon_max)
                lat_max = max(lat, lat_max)

            # Assure a reasonable-sized box.
            settings = current.deployment_settings
            bbox_min_size = bbox_min_size or settings.get_gis_bbox_inset()
            delta_lon = (bbox_min_size - (lon_max - lon_min)) / 2.0
            if delta_lon > 0:
                lon_min -= delta_lon
                lon_max += delta_lon
            delta_lat = (bbox_min_size - (lat_max - lat_min)) / 2.0
            if delta_lat > 0:
                lat_min -= delta_lat
                lat_max += delta_lat

            # Move bounds outward by specified inset.
            bbox_inset = bbox_inset or settings.get_gis_bbox_inset()
            lon_min -= bbox_inset
            lon_max += bbox_inset
            lat_min -= bbox_inset
            lat_max += bbox_inset

        else:
            # no features
            config = GIS.get_config()
            if config.lat_min is not None:
                lat_min = config.lat_min
            else:
                lat_min = -90
            if config.lon_min is not None:
                lon_min = config.lon_min
            else:
                lon_min = -180
            if config.lat_max is not None:
                lat_max = config.lat_max
            else:
                lat_max = 90
            if config.lon_max is not None:
                lon_max = config.lon_max
            else:
                lon_max = 180

        return {"lon_min": lon_min,
                "lat_min": lat_min,
                "lon_max": lon_max,
                "lat_max": lat_max,
                }

    # -------------------------------------------------------------------------
    @staticmethod
    def get_neighbours(location_id):
        """
            Get adjacent neighbours of the same Lx as the Location (or it's parent)
        """

        table = current.s3db.gis_location
        db = current.db

        fields = [table.level,
                  table.parent,
                  table.wkt,
                  ]
        if current.deployment_settings.get_gis_spatialdb():
            SPATIAL = True
        else:
            SPATIAL = False
            fields += [table.lat_min,
                       table.lat_max,
                       table.lon_min,
                       table.lon_max,
                       ]

        feature = db(table.id == location_id).select(*fields,
                                                     limitby = (0, 1)
                                                     ).first()
        level = feature.level
        if not level:
            parent = feature.parent
            if not parent:
                # Nothing we can do: Abort
                return None
            # Use the parent
            location_id = parent
            fields.remove(table.parent)
            feature = db(table.id == parent).select(*fields,
                                                    limitby = (0, 1)
                                                    ).first()
            level = feature.level

        wkt = feature.wkt

        query = (table.level == level) & \
                (table.id != location_id)
        if SPATIAL:
            query &= (table.the_geom.st_intersects(wkt))
            rows = db(query).select(table.id)
            neighbours = [row.id for row in rows]
        else:
            current.log.warning("S3GIS.get_neighbours called without a spatial DB...this is likely to be slow!")
            # Need to use Shapely on each in turn
            from shapely.errors import ReadingError
            from shapely.wkt import loads as wkt_loads

            try:
                # Enable C-based speedups available from 1.2.10+
                from shapely import speedups
                speedups.enable()
            except:
                current.log.info("S3GIS",
                                 "Upgrade Shapely for Performance enhancements")

            try:
                polygon = wkt_loads(wkt)
            except ReadingError:
                current.log.error("Invalid Polygon!")
                return None

            # Optimise with BBOX
            query &= (table.lat_min <= feature.lat_max) & \
                     (table.lat_max >= feature.lat_min) & \
                     (table.lon_min <= feature.lon_max) & \
                     (table.lon_max >= feature.lon_min)
            rows = db(query).select(table.id,
                                    table.wkt,
                                    )
            neighbours = []
            nappend = neighbours.append
            for row in rows:
                try:
                    shape = wkt_loads(wkt)
                    if shape.intersects(polygon):
                        nappend(row.id)
                except ReadingError:
                    current.log.error("Error reading wkt of location with id",
                                      value=row.id)

        return neighbours

    # -------------------------------------------------------------------------
    @staticmethod
    def get_parent_bounds(parent):
        """
            Get bounds from the specified (parent) location and its ancestors.
            This is used to validate lat, lon, and bounds for child locations.

            Caution: This calls update_location_tree if the parent bounds are
            not set. During prepopulate, update_location_tree is disabled,
            so unless the parent contains its own bounds (i.e. they do not need
            to be propagated down from its ancestors), this will not provide a
            check on location nesting. Prepopulate data should be prepared to
            be correct. A set of candidate prepopulate data can be tested by
            importing after prepopulate is run.

            Args:
                parent: A location_id to provide bounds suitable for
                validating child locations

            Returns:
                bounding box and parent location name, as a list:
                [lat_min, lon_min, lat_max, lon_max, parent_name]

            TODO Support Polygons (separate function?)
        """

        table = current.s3db.gis_location
        db = current.db
        parent = db(table.id == parent).select(table.id,
                                               table.level,
                                               table.name,
                                               table.parent,
                                               table.path,
                                               table.lon,
                                               table.lat,
                                               table.lon_min,
                                               table.lat_min,
                                               table.lon_max,
                                               table.lat_max).first()
        if parent.lon_min is None or \
           parent.lon_max is None or \
           parent.lat_min is None or \
           parent.lat_max is None or \
           parent.lon_min == parent.lon_max or \
           parent.lat_min == parent.lat_max:
            # This is unsuitable - try higher parent
            if parent.level == "L1":
                if parent.parent:
                    # We can trust that L0 should have the data from prepop
                    L0 = db(table.id == parent.parent).select(table.name,
                                                              table.lon_min,
                                                              table.lat_min,
                                                              table.lon_max,
                                                              table.lat_max).first()
                    return L0.lat_min, L0.lon_min, L0.lat_max, L0.lon_max, L0.name
            if parent.path:
                path = parent.path
            else:
                # This will return None during prepopulate.
                path = GIS.update_location_tree({"id": parent.id,
                                                 "level": parent.level,
                                                 })
            if path:
                path_list = [int(item) for item in path.split("/")]
                rows = db(table.id.belongs(path_list)).select(table.level,
                                                              table.name,
                                                              table.lat,
                                                              table.lon,
                                                              table.lon_min,
                                                              table.lat_min,
                                                              table.lon_max,
                                                              table.lat_max,
                                                              orderby=table.level)
                row_list = rows.as_list()
                row_list.reverse()
                ok, bounds = False, None
                for row in row_list:
                    if row["lon_min"] is not None and row["lon_max"] is not None and \
                       row["lat_min"] is not None and row["lat_max"] is not None and \
                       row["lon"] != row["lon_min"] != row["lon_max"] and \
                       row["lat"] != row["lat_min"] != row["lat_max"]:
                        bounds = row["lat_min"], row["lon_min"], row["lat_max"], row["lon_max"], row["name"]
                        ok = True
                        break

                if ok:
                    # This level is suitable
                    return bounds

        else:
            # This level is suitable
            return parent.lat_min, parent.lon_min, parent.lat_max, parent.lon_max, parent.name

        # No ancestor bounds available -- use the active gis_config.
        config = GIS.get_config()
        if config:
            return config.lat_min, config.lon_min, config.lat_max, config.lon_max, None

        # Last resort -- fall back to no restriction.
        return -90, -180, 90, 180, None

    # -------------------------------------------------------------------------
    @staticmethod
    def _lookup_parent_path(feature_id):
        """
            Helper that gets parent and path for a location.
        """

        db = current.db
        table = current.s3db.gis_location
        feature = db(table.id == feature_id).select(table.id,
                                                    table.name,
                                                    table.level,
                                                    table.path,
                                                    table.parent,
                                                    limitby = (0, 1)
                                                    ).first()

        return feature

    # -------------------------------------------------------------------------
    @staticmethod
    def get_children(id, level=None):
        """
            Return a list of IDs of all GIS Features which are children of
            the requested feature, using Materialized path for retrieving
            the children

            This has been chosen over Modified Preorder Tree Traversal for
            greater efficiency:
            http://eden.sahanafoundation.org/wiki/HaitiGISToDo#HierarchicalTrees

            Args:
            :param: level - optionally filter by level

            Returns:
                Rows object containing IDs & Names

            Note:
                Return value does NOT include the parent location itself
        """

        db = current.db
        try:
            table = db.gis_location
        except:
            # Being run from CLI for debugging
            table = current.s3db.gis_location
        query = (table.deleted == False)
        if level:
            query &= (table.level == level)
        term = str(id)
        path = table.path
        query &= ((path.like(term + "/%")) | \
                  (path.like("%/" + term + "/%")))
        children = db(query).select(table.id,
                                    table.name)
        return children

    # -------------------------------------------------------------------------
    @staticmethod
    def get_parents(feature_id, feature=None, ids_only=False):
        """
            Returns a list containing ancestors of the requested feature.

            If the caller already has the location row, including path and
            parent fields, they can supply it via feature to avoid a db lookup.

            If ids_only is false, each element in the list is a gluon.sql.Row
            containing the gis_location record of an ancestor of the specified
            location.

            If ids_only is true, just returns a list of ids of the parents.
            This avoids a db lookup for the parents if the specified feature
            has a path.

            List elements are in the opposite order as the location path and
            exclude the specified location itself, i.e. element 0 is the parent
            and the last element is the most distant ancestor.

            Assists lazy update of a database without location paths by calling
            update_location_tree to get the path.

            Note that during prepopulate, update_location_tree is disabled,
            in which case this will only return the immediate parent.
        """

        if not feature or "path" not in feature or "parent" not in feature:
            feature = GIS._lookup_parent_path(feature_id)

        if feature and (feature.path or feature.parent):
            if feature.path:
                path = feature.path
            else:
                path = GIS.update_location_tree(feature)

            if path:
                path_list = [int(item) for item in path.split("/")]
                if len(path_list) == 1:
                    # No parents - path contains only this feature.
                    return None
                # Get only ancestors
                path_list = path_list[:-1]
                # Get path in the desired -- reversed -- order.
                path_list.reverse()
            elif feature.parent:
                path_list = [feature.parent]
            else:
                return None

            # If only ids are wanted, stop here.
            if ids_only:
                return path_list

            # Retrieve parents - order in which they're returned is arbitrary.
            s3db = current.s3db
            table = s3db.gis_location
            query = (table.id.belongs(path_list))
            fields = [table.id, table.name, table.level, table.lat, table.lon]
            unordered_parents = current.db(query).select(cache=s3db.cache,
                                                         *fields)

            # Reorder parents in order of reversed path.
            unordered_ids = [row.id for row in unordered_parents]
            parents = [unordered_parents[unordered_ids.index(path_id)]
                       for path_id in path_list if path_id in unordered_ids]

            return parents

        else:
            return None

    # -------------------------------------------------------------------------
    def get_parent_per_level(self, results, feature_id,
                             feature=None,
                             ids=True,
                             names=True):
        """
            Adds ancestor of requested feature for each level to supplied dict.

            If the caller already has the location row, including path and
            parent fields, they can supply it via feature to avoid a db lookup.

            If a dict is not supplied in results, one is created. The results
            dict is returned in either case.

            If ids=True and names=False (used by old S3LocationSelectorWidget):
            For each ancestor, an entry  is added to results, like
            ancestor.level : ancestor.id

            If ids=False and names=True (used by address_onvalidation):
            For each ancestor, an entry  is added to results, like
            ancestor.level : ancestor.name

            If ids=True and names=True (used by new S3LocationSelectorWidget):
            For each ancestor, an entry  is added to results, like
            ancestor.level : {name : ancestor.name, id: ancestor.id}
        """

        if not results:
            results = {}

        _id = feature_id
        # if we don't have a feature or a feature ID return the dict as-is
        if not feature_id and not feature:
            return results
        if not feature_id and "path" not in feature and "parent" in feature:
            # gis_location_onvalidation on a Create => no ID yet
            # Read the Parent's path instead
            feature = self._lookup_parent_path(feature.parent)
            _id = feature.id
        elif not feature or "path" not in feature or "parent" not in feature:
            feature = self._lookup_parent_path(feature_id)

        if feature and (feature.path or feature.parent):
            if feature.path:
                path = feature.path
            else:
                path = self.update_location_tree(feature)

            # Get ids of ancestors at each level.
            if feature.parent:
                strict = self.get_strict_hierarchy(feature.parent)
            else:
                strict = self.get_strict_hierarchy(_id)
            if path and strict and not names:
                # No need to do a db lookup for parents in this case -- we
                # know the levels of the parents from their position in path.
                # Note ids returned from db are ints, not strings, so be
                # consistent with that.
                path_ids = [int(item) for item in path.split("/")]
                # This skips the last path element, which is the supplied
                # location.
                for (i, _id) in enumerate(path_ids[:-1]):
                    results["L%i" % i] = _id
            elif path:
                ancestors = self.get_parents(_id, feature=feature)
                if ancestors:
                    for ancestor in ancestors:
                        if ancestor.level and ancestor.level in self.hierarchy_level_keys:
                            if names and ids:
                                results[ancestor.level] = Storage()
                                results[ancestor.level].name = ancestor.name
                                results[ancestor.level].id = ancestor.id
                            elif names:
                                results[ancestor.level] = ancestor.name
                            else:
                                results[ancestor.level] = ancestor.id
            if not feature_id:
                # Add the Parent in (we only need the version required for gis_location onvalidation here)
                results[feature.level] = feature.name
            if names:
                # We need to have entries for all levels
                # (both for address onvalidation & new LocationSelector)
                hierarchy_level_keys = self.hierarchy_level_keys
                for key in hierarchy_level_keys:
                    if key not in results:
                        results[key] = None

        return results

    # -------------------------------------------------------------------------
    def update_table_hierarchy_labels(self, tablename=None):
        """
            Re-set table options that depend on location_hierarchy

            Only update tables which are already defined
        """

        levels = ("L1", "L2", "L3", "L4", "L5")
        labels = self.get_location_hierarchy()

        db = current.db
        if tablename and tablename in db:
            # Update the specific table which has just been defined
            table = db[tablename]
            if tablename == "gis_location":
                labels["L0"] = current.messages.COUNTRY
                table.level.requires = \
                    IS_EMPTY_OR(IS_IN_SET(labels))
            else:
                for level in levels:
                    table[level].label = labels[level]
        else:
            # Do all Tables which are already defined

            # gis_location
            if "gis_location" in db:
                table = db.gis_location
                table.level.requires = \
                    IS_EMPTY_OR(IS_IN_SET(labels))

            # These tables store location hierarchy info for XSLT export.
            # Labels are used for PDF & XLS Reports
            tables = ["org_office",
                      #"pr_person",
                      "pr_address",
                      "cr_shelter",
                      "asset_asset",
                      #"hms_hospital",
                      ]

            for tablename in tables:
                if tablename in db:
                    table = db[tablename]
                    for level in levels:
                        table[level].label = labels[level]

    # -------------------------------------------------------------------------
    @staticmethod
    def set_config(config_id=None, force_update_cache=False):
        """
            Reads the specified GIS config from the DB, caches it in response.

            Passing in a false or non-existent id will cause the personal config,
            if any, to be used, else the site config (uuid SITE_DEFAULT), else
            their fallback values defined in this class.

            If force_update_cache is true, the config will be read and cached in
            response even if the specified config is the same as what's already
            cached. Used when the config was just written.

            The config itself will be available in response.s3.gis.config.
            Scalar fields from the gis_config record and its linked
            gis_projection record have the same names as the fields in their
            tables and can be accessed as response.s3.gis.<fieldname>.

            Returns the id of the config it actually used, if any.

            Args:
            :param: config_id. use '0' to set the SITE_DEFAULT

            @ToDo: Merge configs for Event
        """

        cache = Storage()

        _gis = current.response.s3.gis

        # If an id has been supplied, try it first. If it matches what's in
        # response, there's no work to do.
        if config_id and not force_update_cache and \
           _gis.config and \
           _gis.config.id == config_id:
            return cache

        db = current.db
        s3db = current.s3db
        ctable = s3db.gis_config
        mtable = s3db.gis_marker
        ptable = s3db.gis_projection
        stable = s3db.gis_style
        fields = (ctable.id,
                  ctable.default_location_id,
                  ctable.region_location_id,
                  ctable.geocoder,
                  ctable.lat_min,
                  ctable.lat_max,
                  ctable.lon_min,
                  ctable.lon_max,
                  ctable.zoom,
                  ctable.lat,
                  ctable.lon,
                  ctable.pe_id,
                  ctable.wmsbrowser_url,
                  ctable.wmsbrowser_name,
                  ctable.zoom_levels,
                  ctable.merge,
                  mtable.image,
                  mtable.height,
                  mtable.width,
                  ptable.epsg,
                  ptable.proj4js,
                  ptable.maxExtent,
                  ptable.units,
                  )
        # May well not be complete, so Left Join
        left = (ptable.on(ptable.id == ctable.projection_id),
                stable.on((stable.config_id == ctable.id) & \
                          (stable.layer_id == None)),
                mtable.on(mtable.id == stable.marker_id),
                )

        row = None
        rows = None
        if config_id:
            # Does config exist?
            # Should we merge it?
            row = db(ctable.id == config_id).select(ctable.merge,
                                                    ctable.uuid,
                                                    limitby= (0, 1)
                                                    ).first()
            if row:
                if row.merge and row.uuid != "SITE_DEFAULT":
                    row = None
                    # Merge this one with the Site Default
                    query = (ctable.id == config_id) | \
                            (ctable.uuid == "SITE_DEFAULT")
                    rows = db(query).select(*fields,
                                            left = left,
                                            # We want SITE_DEFAULT to be last here (after urn:xxx)
                                            orderby = ~ctable.uuid,
                                            limitby = (0, 2)
                                            )
                else:
                    # Just use this config
                    row = db(ctable.id == config_id).select(*fields,
                                                            left = left,
                                                            limitby = (0, 1)
                                                            ).first()

            else:
                # The requested config must be invalid, so just use site default
                config_id = 0

        if config_id == 0:
            # Use site default
            row = db(ctable.uuid == "SITE_DEFAULT").select(*fields,
                                                           left = left,
                                                           limitby = (0, 1)
                                                           ).first()
            if not row:
                # No configs found at all
                _gis.config = cache
                return cache

        # If no id supplied, extend the site config with any personal or OU configs
        if not rows and not row:
            auth = current.auth
            if auth.is_logged_in():
                # Read personalised config, if available.
                user = auth.user
                pe_id = user.get("pe_id")
                if pe_id:
                    # Also look for OU configs
                    pes = []
                    if user.organisation_id:
                        # Add the user account's Org to the list
                        # (Will take lower-priority than Personal)
                        otable = s3db.org_organisation
                        org = db(otable.id == user.organisation_id).select(otable.pe_id,
                                                                           limitby = (0, 1)
                                                                           ).first()
                        try:
                            pes.append(org.pe_id)
                        except:
                            current.log.warning("Unable to find Org %s" % user.organisation_id)
                        if current.deployment_settings.get_org_branches():
                            # Also look for Parent Orgs
                            ancestors = s3db.pr_get_ancestors(org.pe_id)
                            pes += ancestors

                    if user.site_id:
                        # Add the user account's Site to the list
                        # (Will take lower-priority than Org/Personal)
                        site_pe_id = s3db.pr_get_pe_id("org_site", user.site_id)
                        if site_pe_id:
                            pes.append(site_pe_id)

                    if user.org_group_id:
                        # Add the user account's Org Group to the list
                        # (Will take lower-priority than Site/Org/Personal)
                        ogtable = s3db.org_group
                        ogroup = db(ogtable.id == user.org_group_id).select(ogtable.pe_id,
                                                                            limitby = (0, 1)
                                                                            ).first()
                        pes = list(pes)
                        try:
                            pes.append(ogroup.pe_id)
                        except:
                            current.log.warning("Unable to find Org Group %s" % user.org_group_id)

                    query = (ctable.uuid == "SITE_DEFAULT") | \
                            ((ctable.pe_id == pe_id) & \
                             (ctable.pe_default != False))

                    if len(pes) == 1:
                        query |= (ctable.pe_id == pes[0])
                    else:
                        query |= (ctable.pe_id.belongs(pes))

                    # Order by pe_type (defined in gis_config)
                    # @ToDo: Sort orgs from the hierarchy?
                    # (Currently we just have branch > non-branch in pe_type)
                    rows = db(query).select(*fields,
                                            left = left,
                                            orderby = ctable.pe_type
                                            )
                    if len(rows) == 1:
                        row = rows.first()

        if rows and not row:
            # Merge Configs
            merge = True
            cache["ids"] = []
            for row in rows:
                if not merge:
                    break
                config = row["gis_config"]
                if config.merge is False: # Backwards-compatibility
                    merge = False
                if not config_id:
                    config_id = config.id
                cache["ids"].append(config.id)
                for key in config:
                    if key in ("delete_record", "gis_layer_config", "gis_menu", "update_record", "merge"):
                        continue
                    if key not in cache or cache[key] is None:
                        cache[key] = config[key]
                if "epsg" not in cache or cache["epsg"] is None:
                    projection = row["gis_projection"]
                    for key in ["epsg", "units", "maxExtent", "proj4js"]:
                        cache[key] = projection[key] if key in projection \
                                                     else None
                if "marker_image" not in cache or \
                   cache["marker_image"] is None:
                    marker = row["gis_marker"]
                    for key in ("image", "height", "width"):
                        cache["marker_%s" % key] = marker[key] if key in marker \
                                                               else None
            # Add NULL values for any that aren't defined, to avoid KeyErrors
            for key in ("epsg", "units", "proj4js", "maxExtent",
                        "marker_image", "marker_height", "marker_width",
                        ):
                if key not in cache:
                    cache[key] = None

        if not row:
            # No personal config or not logged in. Use site default.
            row = db(ctable.uuid == "SITE_DEFAULT").select(*fields,
                                                           left = left,
                                                           limitby = (0, 1)
                                                           ).first()

            if not row:
                # No configs found at all
                _gis.config = cache
                return cache

        if not cache:
            # We had a single row
            config = row["gis_config"]
            config_id = config.id
            cache["ids"] = [config_id]
            projection = row["gis_projection"]
            marker = row["gis_marker"]
            for key in config:
                cache[key] = config[key]
            for key in ("epsg", "maxExtent", "proj4js", "units"):
                cache[key] = projection[key] if key in projection else None
            for key in ("image", "height", "width"):
                cache["marker_%s" % key] = marker[key] if key in marker \
                                                       else None

        # Store the values
        _gis.config = cache
        return cache

    # -------------------------------------------------------------------------
    @staticmethod
    def get_config():
        """
            Returns the current GIS config structure.

            @ToDo: Config() class
        """

        _gis = current.response.s3.gis

        if not _gis.config:
            # Ask set_config to put the appropriate config in response.
            if current.session.s3.gis_config_id:
                GIS.set_config(current.session.s3.gis_config_id)
            else:
                GIS.set_config()

        return _gis.config

    # -------------------------------------------------------------------------
    def get_location_hierarchy(self, level=None, location=None):
        """
            Returns the location hierarchy and it's labels

            Args:
            :param: level - a specific level for which to lookup the label
            :param: location - the location_id to lookup the location for
                               currently only the actual location is supported
                               @ToDo: Do a search of parents to allow this
                                      lookup for any location
        """

        _levels = self.hierarchy_levels
        _location = location

        if not location and _levels:
            # Use cached value
            if level:
                if level in _levels:
                    return _levels[level]
                else:
                    return level
            else:
                return _levels

        COUNTRY = current.messages.COUNTRY

        if level == "L0":
            return COUNTRY

        db = current.db
        s3db = current.s3db
        table = s3db.gis_hierarchy

        fields = (table.uuid,
                  table.L1,
                  table.L2,
                  table.L3,
                  table.L4,
                  table.L5,
                  )

        query = (table.uuid == "SITE_DEFAULT")
        if not location:
            config = GIS.get_config()
            location = config.region_location_id
        if location:
            # Try the Region, but ensure we have the fallback available in a single query
            query = query | (table.location_id == location)
        rows = db(query).select(cache=s3db.cache,
                                *fields)
        if len(rows) > 1:
            # Remove the Site Default
            _filter = lambda row: row.uuid == "SITE_DEFAULT"
            rows.exclude(_filter)
        elif not rows:
            # prepop hasn't run yet
            if level:
                return level
            levels = OrderedDict()
            hierarchy_level_keys = self.hierarchy_level_keys
            for key in hierarchy_level_keys:
                if key == "L0":
                    levels[key] = COUNTRY
                else:
                    levels[key] = key
            return levels

        T = current.T
        row = rows.first()
        if level:
            label = row[level]
            return T(label) if label else level
        else:
            levels = OrderedDict()
            hierarchy_level_keys = self.hierarchy_level_keys
            for key in hierarchy_level_keys:
                if key == "L0":
                    levels[key] = COUNTRY
                elif key in row and row[key]:
                    # Only include rows with values
                    levels[key] = str(T(row[key]))
            if not _location:
                # Cache the value
                self.hierarchy_levels = levels
            if level:
                return levels[level]
            else:
                return levels

    # -------------------------------------------------------------------------
    def get_strict_hierarchy(self, location=None):
        """
            Returns the strict hierarchy value from the current config.

            Args:
            :param: location - the location_id of the record to check
        """

        s3db = current.s3db
        table = s3db.gis_hierarchy

        # Read the system default
        # @ToDo: Check for an active gis_config region?
        query = (table.uuid == "SITE_DEFAULT")
        if location:
            # Try the Location's Country, but ensure we have the fallback available in a single query
            query = query | (table.location_id == self.get_parent_country(location))
        rows = current.db(query).select(table.uuid,
                                        table.strict_hierarchy,
                                        cache=s3db.cache)
        if len(rows) > 1:
            # Remove the Site Default
            _filter = lambda row: row.uuid == "SITE_DEFAULT"
            rows.exclude(_filter)
        row = rows.first()
        if row:
            strict = row.strict_hierarchy
        else:
            # Pre-pop hasn't run yet
            return False

        return strict

    # -------------------------------------------------------------------------
    def get_max_hierarchy_level(self):
        """
            Returns the deepest level key (i.e. Ln) in the current hierarchy.
            - used by gis_location_onvalidation()
        """

        location_hierarchy = self.get_location_hierarchy()
        return max(location_hierarchy)

    # -------------------------------------------------------------------------
    def get_all_current_levels(self, level=None):
        """
            Get the current hierarchy levels plus non-hierarchy levels.
        """

        all_levels = OrderedDict()
        all_levels.update(self.get_location_hierarchy())
        #T = current.T
        #all_levels["GR"] = T("Location Group")
        #all_levels["XX"] = T("Imported")

        if level:
            try:
                return all_levels[level]
            except Exception:
                return level
        else:
            return all_levels

    # -------------------------------------------------------------------------
    def get_relevant_hierarchy_levels(self, as_dict=False):
        """
            Get current location hierarchy levels relevant for the user
        """

        levels = self.relevant_hierarchy_levels

        if not levels:
            levels = OrderedDict(self.get_location_hierarchy())
            if len(current.deployment_settings.get_gis_countries()) == 1 or \
               current.response.s3.gis.config.region_location_id:
                levels.pop("L0", None)
            self.relevant_hierarchy_levels = levels

        if not as_dict:
            return list(levels.keys())
        else:
            return levels

    # -------------------------------------------------------------------------
    @staticmethod
    def get_countries(key_type = "id"):
        """
            Returns country code or L0 location id versus name for all countries.

            The lookup is cached in the session

            If key_type is "code", these are returned as an OrderedDict with
            country code as the key.  If key_type is "id", then the location id
            is the key.  In all cases, the value is the name.
        """

        session = current.session
        if "gis" not in session:
            session.gis = Storage()
        gis = session.gis

        if gis.countries_by_id:
            cached = True
        else:
            cached = False

        if not cached:
            s3db = current.s3db
            table = s3db.gis_location
            ttable = s3db.gis_location_tag
            query = (table.level == "L0") & \
                    (ttable.tag == "ISO2") & \
                    (ttable.location_id == table.id)
            countries = current.db(query).select(table.id,
                                                 table.name,
                                                 ttable.value,
                                                 orderby = table.name
                                                 )
            if not countries:
                return []

            countries_by_id = OrderedDict()
            countries_by_code = OrderedDict()
            for row in countries:
                location = row["gis_location"]
                countries_by_id[location.id] = location.name
                countries_by_code[row["gis_location_tag"].value] = location.name

            # Cache in the session
            gis.countries_by_id = countries_by_id
            gis.countries_by_code = countries_by_code

            if key_type == "id":
                return countries_by_id
            else:
                return countries_by_code

        elif key_type == "id":
            return gis.countries_by_id
        else:
            return gis.countries_by_code

    # -------------------------------------------------------------------------
    @staticmethod
    def get_country(key, key_type="id"):
        """
            Returns country name for given code or id from L0 locations.

            The key can be either location id or country code, as specified
            by key_type.
        """

        if key:
            if current.gis.get_countries(key_type):
                if key_type == "id":
                    return current.session.gis.countries_by_id[key]
                else:
                    return current.session.gis.countries_by_code[key]

        return None

    # -------------------------------------------------------------------------
    def get_parent_country(self, location, key_type="id"):
        """
            Returns the parent country for a given record

            Args:
            :param: location: the location or id to search for
            :param: key_type: whether to return an id or code

            @ToDo: Optimise to not use try/except
        """

        if not location:
            return None
        db = current.db
        s3db = current.s3db

        # @ToDo: Avoid try/except here!
        # - separate parameters best as even isinstance is expensive
        try:
            # location is passed as integer (location_id)
            table = s3db.gis_location
            location = db(table.id == location).select(table.id,
                                                       table.path,
                                                       table.level,
                                                       limitby = (0, 1),
                                                       cache=s3db.cache).first()
        except:
            # location is passed as record
            pass

        if location.level == "L0":
            if key_type == "id":
                return location.id
            elif key_type == "code":
                ttable = s3db.gis_location_tag
                query = (ttable.tag == "ISO2") & \
                        (ttable.location_id == location.id)
                tag = db(query).select(ttable.value,
                                       limitby = (0, 1)).first()
                try:
                    return tag.value
                except:
                    return None
        else:
            parents = self.get_parents(location.id,
                                       feature=location)
            if parents:
                for row in parents:
                    if row.level == "L0":
                        if key_type == "id":
                            return row.id
                        elif key_type == "code":
                            ttable = s3db.gis_location_tag
                            query = (ttable.tag == "ISO2") & \
                                    (ttable.location_id == row.id)
                            tag = db(query).select(ttable.value,
                                                   limitby = (0, 1)).first()
                            try:
                                return tag.value
                            except:
                                return None
        return None

    # -------------------------------------------------------------------------
    def get_default_country(self, key_type="id"):
        """
            Returns the default country for the active gis_config

            Args:
            :param: key_type: whether to return an id or code
        """

        config = GIS.get_config()

        if config.default_location_id:
            return self.get_parent_country(config.default_location_id,
                                           key_type=key_type)

        return None

    # -------------------------------------------------------------------------
    def get_features_in_polygon(self, location, tablename=None, category=None):
        """
            Returns a gluon.sql.Rows of Features within a Polygon.
            The Polygon can be either a WKT string or the ID of a record in the
            gis_location table

            Currently unused.
            @ToDo: Optimise to not use try/except
        """

        from shapely.errors import ReadingError
        from shapely.wkt import loads as wkt_loads

        try:
            # Enable C-based speedups available from 1.2.10+
            from shapely import speedups
            speedups.enable()
        except:
            current.log.info("S3GIS",
                             "Upgrade Shapely for Performance enhancements")

        db = current.db
        s3db = current.s3db
        locations = s3db.gis_location

        try:
            location_id = int(location)
            # Check that the location is a polygon
            location = db(locations.id == location_id).select(locations.wkt,
                                                              locations.lon_min,
                                                              locations.lon_max,
                                                              locations.lat_min,
                                                              locations.lat_max,
                                                              limitby = (0, 1)
                                                              ).first()
            if location:
                wkt = location.wkt
                if wkt and (wkt.startswith("POLYGON") or \
                            wkt.startswith("MULTIPOLYGON")):
                    # ok
                    lon_min = location.lon_min
                    lon_max = location.lon_max
                    lat_min = location.lat_min
                    lat_max = location.lat_max

                else:
                    current.log.error("Location searched within isn't a Polygon!")
                    return None
        except: # @ToDo: need specific exception
            wkt = location
            if (wkt.startswith("POLYGON") or wkt.startswith("MULTIPOLYGON")):
                # ok
                lon_min = None
            else:
                current.log.error("This isn't a Polygon!")
                return None

        try:
            polygon = wkt_loads(wkt)
        except ReadingError:
            current.log.error("Invalid Polygon!")
            return None

        table = s3db[tablename]

        if "location_id" not in table.fields():
            # @ToDo: Add any special cases to be able to find the linked location
            current.log.error("This table doesn't have a location_id!")
            return None

        query = (table.location_id == locations.id)
        if "deleted" in table.fields:
            query &= (table.deleted == False)
        # @ToDo: Check AAA (do this as a resource filter?)

        features = db(query).select(locations.wkt,
                                    locations.lat,
                                    locations.lon,
                                    table.ALL
                                    )
        output = Rows()
        # @ToDo: provide option to use PostGIS/Spatialite
        # settings = current.deployment_settings
        # if settings.gis.spatialdb and settings.database.db_type == "postgres":
        if lon_min is None:
            # We have no BBOX so go straight to the full geometry check
            for row in features:
                _location = row.gis_location
                wkt = _location.wkt
                if wkt is None:
                    lat = _location.lat
                    lon = _location.lon
                    if lat is not None and lon is not None:
                        wkt = self.latlon_to_wkt(lat, lon)
                    else:
                        continue
                try:
                    shape = wkt_loads(wkt)
                    if shape.intersects(polygon):
                        # Save Record
                        output.records.append(row)
                except ReadingError:
                    current.log.error("Error reading wkt of location with id",
                                      value=row.id)
        else:
            # 1st check for Features included within the bbox (faster)
            def in_bbox(row):
                _location = row.gis_location
                return (_location.lon > lon_min) & \
                       (_location.lon < lon_max) & \
                       (_location.lat > lat_min) & \
                       (_location.lat < lat_max)
            for row in features.find(lambda row: in_bbox(row)):
                # Search within this subset with a full geometry check
                # Uses Shapely.
                _location = row.gis_location
                wkt = _location.wkt
                if wkt is None:
                    lat = _location.lat
                    lon = _location.lon
                    if lat is not None and lon is not None:
                        wkt = self.latlon_to_wkt(lat, lon)
                    else:
                        continue
                try:
                    shape = wkt_loads(wkt)
                    if shape.intersects(polygon):
                        # Save Record
                        output.records.append(row)
                except ReadingError:
                    current.log.error("Error reading wkt of location with id",
                                      value = row.id)
        return output

    # -------------------------------------------------------------------------
    @staticmethod
    def get_polygon_from_bounds(bbox):
        """
            Given a gis_location record or a bounding box dict with keys
            lon_min, lon_max, lat_min, lat_max, construct a WKT polygon with
            points at the corners.
        """

        lon_min = bbox["lon_min"]
        lon_max = bbox["lon_max"]
        lat_min = bbox["lat_min"]
        lat_max = bbox["lat_max"]
        # Take the points in a counterclockwise direction.
        points = [(lon_min, lat_min),
                  (lon_min, lat_max),
                  (lon_max, lat_max),
                  (lon_min, lat_max),
                  (lon_min, lat_min)]
        pairs = ["%s %s" % (p[0], p[1]) for p in points]
        wkt = "POLYGON ((%s))" % ", ".join(pairs)
        return wkt

    # -------------------------------------------------------------------------
    @staticmethod
    def get_bounds_from_radius(lat, lon, radius):
        """
            Compute a bounding box given a Radius (in km) of a LatLon Location

            Returns:
                a dict containing the bounds with keys min_lon, max_lon,
                min_lat, max_lat

            See Also:
                http://janmatuschek.de/LatitudeLongitudeBoundingCoordinates
        """

        import math

        radians = math.radians
        degrees = math.degrees

        MIN_LAT = radians(-90)     # -PI/2
        MAX_LAT = radians(90)      # PI/2
        MIN_LON = radians(-180)    # -PI
        MAX_LON = radians(180)     #  PI

        # Convert to radians for the calculation
        r = float(radius) / RADIUS_EARTH
        radLat = radians(lat)
        radLon = radians(lon)

        # Calculate the bounding box
        minLat = radLat - r
        maxLat = radLat + r

        if (minLat > MIN_LAT) and (maxLat < MAX_LAT):
            deltaLon = math.asin(math.sin(r) / math.cos(radLat))
            minLon = radLon - deltaLon
            if (minLon < MIN_LON):
                minLon += 2 * math.pi
            maxLon = radLon + deltaLon
            if (maxLon > MAX_LON):
                maxLon -= 2 * math.pi
        else:
            # Special care for Poles & 180 Meridian:
            # http://janmatuschek.de/LatitudeLongitudeBoundingCoordinates#PolesAnd180thMeridian
            minLat = max(minLat, MIN_LAT)
            maxLat = min(maxLat, MAX_LAT)
            minLon = MIN_LON
            maxLon = MAX_LON

        # Convert back to degrees
        minLat = degrees(minLat)
        minLon = degrees(minLon)
        maxLat = degrees(maxLat)
        maxLon = degrees(maxLon)

        return {"lat_min": minLat,
                "lat_max": maxLat,
                "lon_min": minLon,
                "lon_max": maxLon,
                }

    # -------------------------------------------------------------------------
    def get_features_in_radius(self, lat, lon, radius, tablename=None, category=None):
        """
            Returns Features within a Radius (in km) of a LatLon Location

            Unused
        """

        import math

        db = current.db
        settings = current.deployment_settings

        if settings.get_gis_spatialdb() and \
           settings.get_database_type() == "postgres":
            # Use PostGIS routine
            # The ST_DWithin function call will automatically include a bounding box comparison that will make use of any indexes that are available on the geometries.
            # @ToDo: Support optional Category (make this a generic filter?)

            import psycopg2
            import psycopg2.extras

            # Convert km to degrees (since we're using the_geom not the_geog)
            radius = math.degrees(float(radius) / RADIUS_EARTH)

            dbstr = "dbname=%(database)s user=%(username)s " \
                    "password=%(password)s host=%(host)s port=%(port)s" % \
                    settings.db_params
            connection = psycopg2.connect(dbstr)

            cursor = connection.cursor(cursor_factory=psycopg2.extras.DictCursor)
            info_string = "SELECT column_name, udt_name FROM information_schema.columns WHERE table_name = 'gis_location' or table_name = '%s';" % tablename
            cursor.execute(info_string)
            # @ToDo: Look at more optimal queries for just those fields we need
            if tablename:
                # Lookup the resource
                query_string = cursor.mogrify("SELECT * FROM gis_location, %s WHERE %s.location_id = gis_location.id and ST_DWithin (ST_GeomFromText ('POINT (%s %s)', 4326), the_geom, %s);" % (tablename, tablename, lon, lat, radius))
            else:
                # Lookup the raw Locations
                query_string = cursor.mogrify("SELECT * FROM gis_location WHERE ST_DWithin (ST_GeomFromText ('POINT (%s %s)', 4326), the_geom, %s);" % (lon, lat, radius))

            cursor.execute(query_string)
            # @ToDo: Export Rows?
            features = []
            for record in cursor:
                d = dict(record.items())
                row = Storage()
                # @ToDo: Optional support for Polygons
                if tablename:
                    row.gis_location = Storage()
                    row.gis_location.id = d["id"]
                    row.gis_location.lat = d["lat"]
                    row.gis_location.lon = d["lon"]
                    row.gis_location.lat_min = d["lat_min"]
                    row.gis_location.lon_min = d["lon_min"]
                    row.gis_location.lat_max = d["lat_max"]
                    row.gis_location.lon_max = d["lon_max"]
                    row[tablename] = Storage()
                    row[tablename].id = d["id"]
                    row[tablename].name = d["name"]
                else:
                    row.name = d["name"]
                    row.id = d["id"]
                    row.lat = d["lat"]
                    row.lon = d["lon"]
                    row.lat_min = d["lat_min"]
                    row.lon_min = d["lon_min"]
                    row.lat_max = d["lat_max"]
                    row.lon_max = d["lon_max"]
                features.append(row)

            return features

        #elif settings.database.db_type == "mysql":
            # Do the calculation in MySQL to pull back only the relevant rows
            # Raw MySQL Formula from: http://blog.peoplesdns.com/archives/24
            # PI = 3.141592653589793, mysql's pi() function returns 3.141593
            #pi = math.pi
            #query = """SELECT name, lat, lon, acos(SIN( PI()* 40.7383040 /180 )*SIN( PI()*lat/180 ))+(cos(PI()* 40.7383040 /180)*COS( PI()*lat/180) *COS(PI()*lon/180-PI()* -73.99319 /180))* 3963.191
            #AS distance
            #FROM gis_location
            #WHERE 1=1
            #AND 3963.191 * ACOS( (SIN(PI()* 40.7383040 /180)*SIN(PI() * lat/180)) + (COS(PI()* 40.7383040 /180)*cos(PI()*lat/180)*COS(PI() * lon/180-PI()* -73.99319 /180))) < = 1.5
            #ORDER BY 3963.191 * ACOS((SIN(PI()* 40.7383040 /180)*SIN(PI()*lat/180)) + (COS(PI()* 40.7383040 /180)*cos(PI()*lat/180)*COS(PI() * lon/180-PI()* -73.99319 /180)))"""
            # db.executesql(query)

        else:
            # Calculate in Python
            # Pull back all the rows within a square bounding box (faster than checking all features manually)
            # Then check each feature within this subset
            # http://janmatuschek.de/LatitudeLongitudeBoundingCoordinates

            # @ToDo: Support optional Category (make this a generic filter?)

            bbox = self.get_bounds_from_radius(lat, lon, radius)

            # shortcut
            locations = db.gis_location

            query = (locations.lat > bbox["lat_min"]) & \
                    (locations.lat < bbox["lat_max"]) & \
                    (locations.lon > bbox["lon_min"]) & \
                    (locations.lon < bbox["lon_max"])
            deleted = (locations.deleted == False)
            empty = (locations.lat != None) & (locations.lon != None)
            query = deleted & empty & query

            if tablename:
                # Lookup the resource
                table = current.s3db[tablename]
                query &= (table.location_id == locations.id)
                records = db(query).select(table.ALL,
                                           locations.id,
                                           locations.name,
                                           locations.level,
                                           locations.lat,
                                           locations.lon,
                                           locations.lat_min,
                                           locations.lon_min,
                                           locations.lat_max,
                                           locations.lon_max)
            else:
                # Lookup the raw Locations
                records = db(query).select(locations.id,
                                           locations.name,
                                           locations.level,
                                           locations.lat,
                                           locations.lon,
                                           locations.lat_min,
                                           locations.lon_min,
                                           locations.lat_max,
                                           locations.lon_max)
            features = Rows()
            for row in records:
                # Calculate the Great Circle distance
                if tablename:
                    distance = self.greatCircleDistance(lat,
                                                        lon,
                                                        row["gis_location.lat"],
                                                        row["gis_location.lon"])
                else:
                    distance = self.greatCircleDistance(lat,
                                                        lon,
                                                        row.lat,
                                                        row.lon)
                if distance < radius:
                    features.records.append(row)
                else:
                    # skip
                    continue

            return features

    # -------------------------------------------------------------------------
    def get_latlon(self, feature_id, filter=False):
        """
            Returns the Lat/Lon for a Feature

            used by display_feature() in gis controller

            Args:
                feature_id: the feature ID
                filter: Filter out results based on deployment_settings
        """

        db = current.db
        table = db.gis_location
        feature = db(table.id == feature_id).select(table.id,
                                                    table.lat,
                                                    table.lon,
                                                    table.parent,
                                                    table.path,
                                                    limitby = (0, 1)).first()

        # Zero is an allowed value, hence explicit test for None.
        if "lon" in feature and "lat" in feature and \
           (feature.lat is not None) and (feature.lon is not None):
            return {"lon": feature.lon,
                    "lat": feature.lat,
                    }

        else:
            # Step through ancestors to first with lon, lat.
            parents = self.get_parents(feature.id, feature=feature)
            if parents:
                for row in parents:
                    lon = row.get("lon", None)
                    lat = row.get("lat", None)
                    if (lon is not None) and (lat is not None):
                        return {"lon": lon,
                                "lat": lat,
                                }

        # Invalid feature_id
        return None

    # -------------------------------------------------------------------------
    @staticmethod
    def get_locations(table,
                      query,
                      join = True,
                      geojson = True,
                      ):
        """
            Returns the locations for an XML export
            - used by GIS.get_location_data() and S3PivotTable.geojson()

            @ToDo: Support multiple locations for a single resource
                   (e.g. a Project working in multiple Communities)
        """

        db = current.db
        tablename = table._tablename
        gtable = current.s3db.gis_location
        settings = current.deployment_settings
        tolerance = settings.get_gis_simplify_tolerance()

        output = {}

        if settings.get_gis_spatialdb():
            if geojson:
                precision = settings.get_gis_precision()
                if tolerance:
                    # Do the Simplify & GeoJSON direct from the DB
                    web2py_installed_version = parse_version(global_settings.web2py_version)
                    web2py_installed_datetime = web2py_installed_version[4] # datetime_index = 4
                    if web2py_installed_datetime >= datetime.datetime(2015, 1, 17, 0, 7, 4):
                        # Use http://www.postgis.org/docs/ST_SimplifyPreserveTopology.html
                        rows = db(query).select(table.id,
                                                gtable.the_geom.st_simplifypreservetopology(tolerance).st_asgeojson(precision=precision).with_alias("geojson"))
                    else:
                        # Use http://www.postgis.org/docs/ST_Simplify.html
                        rows = db(query).select(table.id,
                                                gtable.the_geom.st_simplify(tolerance).st_asgeojson(precision=precision).with_alias("geojson"))
                else:
                    # Do the GeoJSON direct from the DB
                    rows = db(query).select(table.id,
                                            gtable.the_geom.st_asgeojson(precision=precision).with_alias("geojson"))
                for row in rows:
                    key = row[tablename].id
                    if key in output:
                        output[key].append(row.geojson)
                    else:
                        output[key] = [row.geojson]
            else:
                if tolerance:
                    # Do the Simplify direct from the DB
                    rows = db(query).select(table.id,
                                            gtable.the_geom.st_simplify(tolerance).st_astext().with_alias("wkt"))
                else:
                    rows = db(query).select(table.id,
                                            gtable.the_geom.st_astext().with_alias("wkt"))
                for row in rows:
                    key = row[tablename].id
                    if key in output:
                        output[key].append(row.wkt)
                    else:
                        output[key] = [row.wkt]
        else:
            rows = db(query).select(table.id,
                                    gtable.wkt)
            simplify = GIS.simplify
            if geojson:
                # Simplify the polygon to reduce download size
                if join:
                    for row in rows:
                        g = simplify(row["gis_location"].wkt,
                                     tolerance=tolerance,
                                     output="geojson")
                        if g:
                            key = row[tablename].id
                            if key in output:
                                output[key].append(g)
                            else:
                                output[key] = [g]
                else:
                    # gis_location: always single
                    for row in rows:
                        g = simplify(row.wkt,
                                     tolerance=tolerance,
                                     output="geojson")
                        if g:
                            output[row.id] = g

            else:
                if join:
                    if tolerance:
                        # Simplify the polygon to reduce download size
                        # & also to work around the recursion limit in libxslt
                        # http://blog.gmane.org/gmane.comp.python.lxml.devel/day=20120309
                        for row in rows:
                            wkt = simplify(row["gis_location"].wkt)
                            if wkt:
                                key = row[tablename].id
                                if key in output:
                                    output[key].append(wkt)
                                else:
                                    output[key] = [wkt]
                    else:
                        for row in rows:
                            wkt = row["gis_location"].wkt
                            if wkt:
                                key = row[tablename].id
                                if key in output:
                                    output[key].append(wkt)
                                else:
                                    output[key] = [wkt]
                else:
                    # gis_location: always single
                    if tolerance:
                        for row in rows:
                            wkt = simplify(row.wkt)
                            if wkt:
                                output[row.id] = wkt
                    else:
                        for row in rows:
                            wkt = row.wkt
                            if wkt:
                                output[row.id] = wkt

        return output

    # -------------------------------------------------------------------------
    @staticmethod
    def get_location_data(resource, attr_fields=None, count=None):
        """
            Returns the locations, markers and popup tooltips for an XML export
            e.g. Feature Layers or Search results (Feature Resources)
            e.g. Exports in KML, GeoRSS or GPX format

            Called by S3ResourceTree
            Args:
            :param: resource - CRUDResource instance (required)
            :param: attr_fields - list of attr_fields to use instead of reading
                                  from get_vars or looking up in gis_layer_feature
            :param: count - total number of features
                           (can actually be more if features have multiple locations)
        """

        tablename = resource.tablename
        if tablename == "gis_feature_query":
            # Requires no special handling: XSLT uses normal fields
            return {}

        format = current.auth.permission.format
        geojson = format == "geojson"
        if geojson:
            if count and \
               count > current.deployment_settings.get_gis_max_features():
                headers = {"Content-Type": "application/json"}
                message = "Too Many Records"
                status = 509
                raise HTTP(status,
                           body=current.xml.json_message(success=False,
                                                         statuscode=status,
                                                         message=message),
                           web2py_error=message,
                           **headers)
            # Lookups per layer not per record
            if len(tablename) > 19 and \
               tablename.startswith("gis_layer_shapefile"):
                # GIS Shapefile Layer
                location_data = GIS.get_shapefile_geojson(resource) or {}
                return location_data
            elif tablename == "gis_theme_data":
                # GIS Theme Layer
                location_data = GIS.get_theme_geojson(resource) or {}
                return location_data
            else:
                # e.g. GIS Feature Layer
                # e.g. Search results
                # Lookup Data using this function
                pass
        elif format in ("georss", "kml", "gpx"):
            # Lookup Data using this function
            pass
        else:
            # @ToDo: Bulk lookup of LatLons for S3XML.latlon()
            return {}

        NONE = current.messages["NONE"]
        #if DEBUG:
        #    start = datetime.datetime.now()

        db = current.db
        s3db = current.s3db
        request = current.request
        get_vars = request.get_vars

        ftable = s3db.gis_layer_feature

        layer = None

        layer_id = get_vars.get("layer", None)
        if layer_id:
            # Feature Layer
            # e.g. Search results loaded as a Feature Resource layer
            layer = db(ftable.layer_id == layer_id).select(ftable.attr_fields,
                                                           # @ToDo: Deprecate
                                                           ftable.popup_fields,
                                                           ftable.individual,
                                                           ftable.points,
                                                           ftable.trackable,
                                                           limitby = (0, 1)
                                                           ).first()

        else:
            # e.g. KML, GeoRSS or GPX export
            controller = request.controller
            function = request.function
            query = (ftable.controller == controller) & \
                    (ftable.function == function)
            layers = db(query).select(ftable.layer_id,
                                      ftable.attr_fields,
                                      ftable.popup_fields,  # @ToDo: Deprecate
                                      ftable.style_default, # @ToDo: Rename as no longer really 'style'
                                      ftable.individual,
                                      ftable.points,
                                      ftable.trackable,
                                      )
            if len(layers) > 1:
                layers.exclude(lambda row: row.style_default == False)
                if len(layers) > 1:
                    # We can't provide details for the whole layer, but need to do a per-record check
                    return None
            if layers:
                layer = layers.first()
                layer_id = layer.layer_id

        if not attr_fields:
            # Try get_vars
            attr_fields = get_vars.get("attr", [])
        if attr_fields:
            attr_fields = attr_fields.split(",")
        popup_fields = get_vars.get("popup", [])
        if popup_fields:
            popup_fields = popup_fields.split(",")
        if layer:
            if not popup_fields:
                # Lookup from gis_layer_feature
                popup_fields = layer.popup_fields or []
            if not attr_fields:
                # Lookup from gis_layer_feature
                # @ToDo: Consider parsing these from style.popup_format instead
                #        - see S3Report.geojson()
                attr_fields = layer.attr_fields or []
            individual = layer.individual
            points = layer.points
            trackable = layer.trackable
        else:
            if not popup_fields:
                popup_fields = ["name"]
            individual = False
            points = False
            trackable = False

        table = resource.table
        pkey = table._id.name

        attributes = {}
        markers = {}
        styles = {}
        _pkey = table[pkey]
        # Ensure there are no ID represents to confuse things
        _pkey.represent = None
        if geojson:
            # Build the Attributes now so that representations can be
            # looked-up in bulk rather than as a separate lookup per record
            if popup_fields:
                # Old-style
                attr_fields = list(set(popup_fields + attr_fields))
            if attr_fields:
                attr = {}

                # Make a copy for the pkey insertion
                fields = list(attr_fields)

                if pkey not in fields:
                    fields.insert(0, pkey)

                data = resource.select(fields,
                                       limit = None,
                                       raw_data = True,
                                       represent = True,
                                       show_links = False)

                attr_cols = {}
                for f in data["rfields"]:
                    fname = f.fname
                    selector = f.selector
                    if fname in attr_fields or selector in attr_fields:
                        fieldname = f.colname
                        tname, fname = fieldname.split(".")
                        try:
                            ftype = db[tname][fname].type
                        except AttributeError:
                            # FieldMethod
                            ftype = None
                        except KeyError:
                            current.log.debug("SGIS: Field %s doesn't exist in table %s" % (fname, tname))
                            continue
                        attr_cols[fieldname] = (ftype, fname)

                _pkey = str(_pkey)
                for row in data["rows"]:
                    record_id = int(row[_pkey])
                    if attr_cols:
                        attribute = {}
                        for fieldname in attr_cols:
                            represent = row[fieldname]
                            if represent is not None and \
                               represent not in (NONE, ""):
                                # Skip empty fields
                                _attr = attr_cols[fieldname]
                                ftype = _attr[0]
                                if ftype == "integer":
                                    if isinstance(represent, lazyT):
                                        # Integer is just a lookup key
                                        represent = s3_str(represent)
                                    else:
                                        # Attributes should be numbers not strings
                                        # (@ToDo: Add a JS i18n formatter for the tooltips)
                                        # NB This also relies on decoding within geojson/export.xsl and S3XML.__element2json()
                                        represent = row["_row"][fieldname]
                                elif ftype in ("double", "float"):
                                    # Attributes should be numbers not strings
                                    # (@ToDo: Add a JS i18n formatter for the tooltips)
                                    represent = row["_row"][fieldname]
                                else:
                                    represent = s3_str(represent)
                                attribute[_attr[1]] = represent
                        attr[record_id] = attribute

                attributes[tablename] = attr

                #if DEBUG:
                #    end = datetime.datetime.now()
                #    duration = end - start
                #    duration = "{:.2f}".format(duration.total_seconds())
                #    if layer_id:
                #        layer_name = db(ftable.id == layer_id).select(ftable.name,
                #                                                      limitby = (0, 1)
                #                                                      ).first().name
                #    else:
                #        layer_name = "Unknown"
                #    _debug("Attributes lookup of layer %s completed in %s seconds",
                #           layer_name,
                #           duration,
                #           )

            _markers = get_vars.get("markers", None)
            if _markers:
                # Add a per-feature Marker
                marker_fn = s3db.get_config(tablename, "marker_fn")
                if marker_fn:
                    m = {}
                    for record in resource:
                        m[record[pkey]] = marker_fn(record)
                else:
                    # No configuration found so use default marker for all
                    c, f = tablename.split("_", 1)
                    m = GIS.get_marker(c, f)

                markers[tablename] = m

            if individual:
                # Add a per-feature Style
                # Optionally restrict to a specific Config?
                #config = GIS.get_config()
                stable = s3db.gis_style
                query = (stable.deleted == False) & \
                        (stable.layer_id == layer_id) & \
                        (stable.record_id.belongs(resource._ids))
                        #((stable.config_id == config.id) |
                        # (stable.config_id == None))
                rows = db(query).select(stable.record_id,
                                        stable.style)
                for row in rows:
                    styles[row.record_id] = json.dumps(row.style, separators=JSONSEPARATORS)

                styles[tablename] = styles

        else:
            # KML, GeoRSS or GPX
            marker_fn = s3db.get_config(tablename, "marker_fn")
            if marker_fn:
                # Add a per-feature Marker
                for record in resource:
                    markers[record[pkey]] = marker_fn(record)
            else:
                # No configuration found so use default marker for all
                c, f = tablename.split("_", 1)
                markers = GIS.get_marker(c, f)

            markers[tablename] = markers

        # Lookup the LatLons now so that it can be done as a single
        # query rather than per record
        #if DEBUG:
        #    start = datetime.datetime.now()
        latlons = {}
        #wkts = {}
        geojsons = {}
        gtable = s3db.gis_location
        if trackable:
            # Use S3Track
            ids = resource._ids
            # Ensure IDs in ascending order
            ids.sort()
            try:
                tracker = S3Trackable(table, record_ids=ids)
            except SyntaxError:
                # This table isn't trackable
                pass
            else:
                _latlons = tracker.get_location(_fields=[gtable.lat,
                                                         gtable.lon],
                                                empty = False,
                                                )
                index = 0
                for _id in ids:
                    _location = _latlons[index]
                    latlons[_id] = (_location.lat, _location.lon)
                    index += 1

        if not latlons:
            join = True
            #custom = False
            if "location_id" in table.fields:
                query = (table.id.belongs(resource._ids)) & \
                        (table.location_id == gtable.id)
            elif "site_id" in table.fields:
                stable = s3db.org_site
                query = (table.id.belongs(resource._ids)) & \
                        (table.site_id == stable.site_id) & \
                        (stable.location_id == gtable.id)
            elif tablename == "gis_location":
                join = False
                query = (table.id.belongs(resource._ids))
            else:
                # Look at the Context
                context = resource.get_config("context")
                if context:
                    location_context = context.get("location")
                else:
                    location_context = None
                if not location_context:
                    # Can't display this resource on the Map
                    return None
                # @ToDo: Proper system rather than this hack_which_works_for_current_usecase
                # Resolve selector (which automatically attaches any required component)
                rfield = resource.resolve_selector(location_context)
                if "." in location_context:
                    # Component
                    alias, cfield = location_context.split(".", 1)
                    try:
                        component = resource.components[alias]
                    except KeyError:
                        # Invalid alias
                        # Can't display this resource on the Map
                        return None
                    ctablename = component.tablename
                    ctable = s3db[ctablename]
                    query = (table.id.belongs(resource._ids)) & \
                            rfield.join[ctablename] & \
                            (ctable[cfield] == gtable.id)
                    #custom = True
                # @ToDo:
                #elif "$" in location_context:
                else:
                    # Can't display this resource on the Map
                    return None

            if geojson and not points:
                geojsons[tablename] = GIS.get_locations(table, query, join, geojson)
            # @ToDo: Support Polygons in KML, GPX & GeoRSS
            #else:
            #    wkts[tablename] = GIS.get_locations(table, query, join, geojson)
            else:
                # Points
                rows = db(query).select(table.id,
                                        gtable.lat,
                                        gtable.lon)
                #if custom:
                #    # Add geoJSONs
                #elif join:
                if join:
                    for row in rows:
                        # @ToDo: Support records with multiple locations
                        #        (e.g. an Org with multiple Facs)
                        _location = row["gis_location"]
                        latlons[row[tablename].id] = (_location.lat, _location.lon)
                else:
                    # gis_location: Always single
                    for row in rows:
                        latlons[row.id] = (row.lat, row.lon)

        _latlons = {}
        if latlons:
            _latlons[tablename] = latlons

        #if DEBUG:
        #    end = datetime.datetime.now()
        #    duration = end - start
        #    duration = "{:.2f}".format(duration.total_seconds())
        #    _debug("latlons lookup of layer %s completed in %s seconds",
        #           layer_name,
        #           duration,
        #           )

        # Used by S3XML's gis_encode()
        return {"geojsons": geojsons,
                "latlons": _latlons,
                #"wkts": wkts,
                "attributes": attributes,
                "markers": markers,
                "styles": styles,
                }

    # -------------------------------------------------------------------------
    @staticmethod
    def get_marker(controller=None,
                   function=None,
                   filter=None,
                   ):
        """
            Returns a Marker dict
            - called by xml.gis_encode() for non-geojson resources
            - called by S3Map.widget() if no marker_fn supplied
        """

        marker = None
        if controller and function:
            # Lookup marker in the gis_style table
            db = current.db
            s3db = current.s3db
            ftable = s3db.gis_layer_feature
            stable = s3db.gis_style
            mtable = s3db.gis_marker
            config = GIS.get_config()
            query = (ftable.controller == controller) & \
                    (ftable.function == function) & \
                    (ftable.aggregate == False)
            left = (stable.on((stable.layer_id == ftable.layer_id) & \
                              (stable.record_id == None) & \
                              ((stable.config_id == config.id) | \
                               (stable.config_id == None))),
                    mtable.on(mtable.id == stable.marker_id),
                    )
            if filter:
                query &= (ftable.filter == filter)
            if current.deployment_settings.get_database_type() == "postgres":
                # None is last
                orderby = stable.config_id
            else:
                # None is 1st
                orderby = ~stable.config_id
            layers = db(query).select(mtable.image,
                                      mtable.height,
                                      mtable.width,
                                      ftable.style_default,
                                      stable.gps_marker,
                                      left=left,
                                      orderby=orderby)
            if len(layers) > 1:
                layers.exclude(lambda row: row["gis_layer_feature.style_default"] == False)
            if len(layers) == 1:
                layer = layers.first()
            else:
                # Can't differentiate
                layer = None

            if layer:
                _marker = layer["gis_marker"]
                if _marker.image:
                    marker = {"image": _marker.image,
                              "height": _marker.height,
                              "width": _marker.width,
                              "gps_marker": layer["gis_style"].gps_marker,
                              }

        if not marker:
            # Default
            from .marker import Marker
            marker = Marker().as_dict()

        return marker

    # -------------------------------------------------------------------------
    @staticmethod
    def get_style(layer_id=None,
                  aggregate=None,
                  ):
        """
            Returns a Style dict
            - called by S3Report.geojson()
        """

        from .style import Style

        style = None
        if layer_id:
            style = Style(layer_id=layer_id,
                          aggregate=aggregate).as_dict()

        if not style:
            # Default
            style = Style().as_dict()

        return style

    # -------------------------------------------------------------------------
    @staticmethod
    def get_screenshot(config_id, temp=True, height=None, width=None):
        """
            Save a Screenshot of a saved map

            @requires:
                PhantomJS http://phantomjs.org
                Selenium https://pypi.python.org/pypi/selenium
        """

        # @ToDo: allow selection of map_id
        map_id = "default_map"

        #from selenium import webdriver
        # We include a Custom version which is patched to access native PhantomJS functions from:
        # https://github.com/watsonmw/ghostdriver/commit/d9b65ed014ed9ff8a5e852cc40e59a0fd66d0cf1
        from webdriver import WebDriver
        from selenium.common.exceptions import TimeoutException, WebDriverException
        from selenium.webdriver.support.ui import WebDriverWait

        request = current.request

        cachepath = os.path.join(request.folder, "static", "cache", "jpg")

        if not os.path.exists(cachepath):
            try:
                os.mkdir(cachepath)
            except OSError as os_error:
                error = "GIS: JPEG files cannot be saved: %s %s" % \
                                  (cachepath, os_error)
                current.log.error(error)
                current.session.error = error
                redirect(URL(c="gis", f="index", vars={"config": config_id}))

        # Copy the current working directory to revert back to later
        cwd = os.getcwd()
        # Change to the Cache folder (can't render directly there from execute_phantomjs)
        os.chdir(cachepath)

        #driver = webdriver.PhantomJS()
        # Disable Proxy for Win32 Network Latency issue
        driver = WebDriver(service_args=["--proxy-type=none"])

        # Change back for other parts
        os.chdir(cwd)

        settings = current.deployment_settings
        if height is None:
            # Set the size of the browser to match the map
            height = settings.get_gis_map_height()
        if width is None:
            width = settings.get_gis_map_width()
        # For Screenshots
        #height = 410
        #width = 820
        driver.set_window_size(width + 5, height + 20)

        # Load the homepage
        # (Cookie needs to be set on same domain as it takes effect)
        base_url = "%s/%s" % (settings.get_base_public_url(),
                              request.application)
        driver.get(base_url)

        response = current.response
        session_id = response.session_id
        if not current.auth.override:
            # Reuse current session to allow access to ACL-controlled resources
            driver.add_cookie({"name":  response.session_id_name,
                               "value": session_id,
                               "path":  "/",
                               })
            # For sync connections
            current.session._unlock(response)

        # Load the map
        url = "%s/gis/map_viewing_client?print=1&config=%s" % (base_url,
                                                               config_id)
        driver.get(url)

        # Wait for map to load (including it's layers)
        # Alternative approach: https://raw.githubusercontent.com/ariya/phantomjs/master/examples/waitfor.js
        def map_loaded(driver):
            test = '''return S3.gis.maps['%s'].s3.loaded''' % map_id
            try:
                result = driver.execute_script(test)
            except WebDriverException:
                result = False
            return result

        try:
            # Wait for up to 100s (large screenshots take a long time for layers to load)
            WebDriverWait(driver, 100).until(map_loaded)
        except TimeoutException as e:
            driver.quit()
            current.log.error("Timeout: %s" % e)
            return None

        # Save the Output
        # @ToDo: Can we use StringIO instead of cluttering filesystem?
        # @ToDo: Allow option of PDF (as well as JPG)
        # https://github.com/ariya/phantomjs/blob/master/examples/rasterize.js
        if temp:
            filename = "%s.jpg" % session_id
        else:
            filename = "config_%s.jpg" % config_id

        # Cannot control file size (no access to clipRect) or file format
        #driver.save_screenshot(os.path.join(cachepath, filename))

        #driver.page.clipRect = {"top": 10,
        #                        "left": 5,
        #                        "width": width,
        #                        "height": height
        #                        }
        #driver.page.render(filename, {"format": "jpeg", "quality": "100"})

        script = '''
var page = this;
page.clipRect = {top: 10,
                 left: 5,
                 width: %(width)s,
                 height: %(height)s
                 };
page.render('%(filename)s', {format: 'jpeg', quality: '100'});''' % \
                    {"width": width,
                     "height": height,
                     "filename": filename,
                     }
        try:
            driver.execute_phantomjs(script)
        except WebDriverException as e:
            driver.quit()
            current.log.error("WebDriver crashed: %s" % e)
            return None

        driver.quit()

        if temp:
            # This was a temporary config for creating the screenshot, then delete it now
            ctable = current.s3db.gis_config
            the_set = current.db(ctable.id == config_id)
            config = the_set.select(ctable.temp,
                                    limitby = (0, 1)
                                    ).first()
            try:
                if config.temp:
                    the_set.delete()
            except:
                # Record not found?
                pass

        # Pass the result back to the User
        return filename

    # -------------------------------------------------------------------------
    @staticmethod
    def get_shapefile_geojson(resource):
        """
            Lookup Shapefile Layer polygons once per layer and not per-record

            Called by S3ResourceTree

            @ToDo: Vary simplification level & precision by Zoom level
                   - store this in the style?
        """

        db = current.db
        #tablename = "gis_layer_shapefile_%s" % resource._ids[0]
        tablename = resource.tablename
        table = db[tablename]
        query = resource.get_query()
        fields = []
        fappend = fields.append
        for f in table.fields:
            if f not in ("layer_id", "lat", "lon"):
                fappend(f)

        attributes = {}
        geojsons = {}
        settings = current.deployment_settings
        tolerance = settings.get_gis_simplify_tolerance()
        if settings.get_gis_spatialdb():
            # Do the Simplify & GeoJSON direct from the DB
            fields.remove("the_geom")
            fields.remove("wkt")
            _fields = [table[f] for f in fields]
            rows = db(query).select(table.the_geom.st_simplify(tolerance).st_asgeojson(precision=4).with_alias("geojson"),
                                    *_fields)
            for row in rows:
                _row = row[tablename]
                _id = _row.id
                geojsons[_id] = row.geojson
                _attributes = {}
                for f in fields:
                    if f not in ("id"):
                        _attributes[f] = _row[f]
                attributes[_id] = _attributes
        else:
            _fields = [table[f] for f in fields]
            rows = db(query).select(*_fields)
            simplify = GIS.simplify
            for row in rows:
                # Simplify the polygon to reduce download size
                geojson = simplify(row.wkt, tolerance=tolerance,
                                   output="geojson")
                _id = row.id
                if geojson:
                    geojsons[_id] = geojson
                _attributes = {}
                for f in fields:
                    if f not in ("id", "wkt"):
                        _attributes[f] = row[f]
                attributes[_id] = _attributes

        _attributes = {}
        _attributes[tablename] = attributes
        _geojsons = {}
        _geojsons[tablename] = geojsons

        # return 'locations'
        return {"attributes": _attributes,
                "geojsons": _geojsons,
                }

    # -------------------------------------------------------------------------
    @staticmethod
    def get_theme_geojson(resource):
        """
            Lookup Theme Layer polygons once per layer and not per-record

            Called by S3ResourceTree

            @ToDo: Vary precision by Lx
                   - store this (& tolerance map) in the style?
        """

        s3db = current.s3db
        tablename = "gis_theme_data"
        table = s3db.gis_theme_data
        gtable = s3db.gis_location
        query = (table.id.belongs(resource._ids)) & \
                (table.location_id == gtable.id)

        geojsons = {}
        # @ToDo: How to get the tolerance to vary by level?
        #        - add Stored Procedure?
        #if current.deployment_settings.get_gis_spatialdb():
        #    # Do the Simplify & GeoJSON direct from the DB
        #    rows = current.db(query).select(table.id,
        #                                    gtable.the_geom.st_simplify(0.01).st_asgeojson(precision=4).with_alias("geojson"))
        #    for row in rows:
        #        geojsons[row["gis_theme_data.id"]] = row.geojson
        #else:
        rows = current.db(query).select(table.id,
                                        gtable.level,
                                        gtable.wkt)
        simplify = GIS.simplify
        tolerance = {"L0": 0.01,
                     "L1": 0.005,
                     "L2": 0.00125,
                     "L3": 0.000625,
                     "L4": 0.0003125,
                     "L5": 0.00015625,
                     }
        for row in rows:
            grow = row.gis_location
            # Simplify the polygon to reduce download size
            geojson = simplify(grow.wkt,
                               tolerance=tolerance[grow.level],
                               output="geojson")
            if geojson:
                geojsons[row["gis_theme_data.id"]] = geojson

        _geojsons = {}
        _geojsons[tablename] = geojsons

        # Return 'locations'
        return {"geojsons": _geojsons,
                }

    # -------------------------------------------------------------------------
    @staticmethod
    def greatCircleDistance(lat1, lon1, lat2, lon2, quick=True):
        """
            Calculate the shortest distance (in km) over the earth's sphere between 2 points
            Formulae from: http://www.movable-type.co.uk/scripts/latlong.html
            (NB We could also use PostGIS functions, where possible, instead of this query)
        """

        import math

        # shortcuts
        cos = math.cos
        sin = math.sin
        radians = math.radians

        if quick:
            # Spherical Law of Cosines (accurate down to around 1m & computationally quick)
            lat1 = radians(lat1)
            lat2 = radians(lat2)
            lon1 = radians(lon1)
            lon2 = radians(lon2)
            distance = math.acos(sin(lat1) * sin(lat2) + cos(lat1) * cos(lat2) * cos(lon2 - lon1)) * RADIUS_EARTH
            return distance

        else:
            # Haversine
            #asin = math.asin
            sqrt = math.sqrt
            pow = math.pow
            dLat = radians(lat2 - lat1)
            dLon = radians(lon2 - lon1)
            a = pow(sin(dLat / 2), 2) + cos(radians(lat1)) * cos(radians(lat2)) * pow(sin(dLon / 2), 2)
            c = 2 * math.atan2(sqrt(a), sqrt(1 - a))
            #c = 2 * asin(sqrt(a))              # Alternate version
            # Convert radians to kilometers
            distance = RADIUS_EARTH * c
            return distance

    # -------------------------------------------------------------------------
    @staticmethod
    def create_poly(feature):
        """
            Create a .poly file for OpenStreetMap exports
            http://wiki.openstreetmap.org/wiki/Osmosis/Polygon_Filter_File_Format
        """

        from shapely.wkt import loads as wkt_loads

        try:
            # Enable C-based speedups available from 1.2.10+
            from shapely import speedups
            speedups.enable()
        except:
            current.log.info("S3GIS",
                             "Upgrade Shapely for Performance enhancements")

        name = feature.name

        if "wkt" in feature:
            wkt = feature.wkt
        else:
            # WKT not included by default in feature, so retrieve this now
            table = current.s3db.gis_location
            wkt = current.db(table.id == feature.id).select(table.wkt,
                                                            limitby = (0, 1)
                                                            ).first().wkt

        try:
            shape = wkt_loads(wkt)
        except:
            error = "Invalid WKT: %s" % name
            current.log.error(error)
            return error

        geom_type = shape.geom_type
        if geom_type == "MultiPolygon":
            polygons = shape.geoms
        elif geom_type == "Polygon":
            polygons = [shape]
        else:
            error = "Unsupported Geometry: %s, %s" % (name, geom_type)
            current.log.error(error)
            return error
        if os.path.exists(os.path.join(os.getcwd(), "temp")): # use web2py/temp
            TEMP = os.path.join(os.getcwd(), "temp")
        else:
            import tempfile
            TEMP = tempfile.gettempdir()
        filename = "%s.poly" % name
        filepath = os.path.join(TEMP, filename)
        File = open(filepath, "w")
        File.write("%s\n" % filename)
        count = 1
        for polygon in polygons:
            File.write("%s\n" % count)
            points = polygon.exterior.coords
            for point in points:
                File.write("\t%s\t%s\n" % (point[0], point[1]))
            File.write("END\n")
            count += 1
        File.write("END\n")
        File.close()

        return None

    # -------------------------------------------------------------------------
    @staticmethod
    def export_admin_areas(countries=[],
                           levels=("L0", "L1", "L2", "L3"),
                           format="geojson",
                           simplify=0.01,
                           precision=4,
                           ):
        """
            Export admin areas to /static/cache for use by interactive web-mapping services
            - designed for use by the Vulnerability Mapping

            Args:
                countries: list of ISO2 country codes
                levels: list of which Lx levels to export
                format: Only GeoJSON supported for now (may add KML &/or OSM later)
                simplify: tolerance for the simplification algorithm. False to disable simplification
                precision: number of decimal points to include in the coordinates
        """

        db = current.db
        s3db = current.s3db
        table = s3db.gis_location
        ifield = table.id
        if countries:
            ttable = s3db.gis_location_tag
            cquery = (table.level == "L0") & \
                     (table.end_date == None) & \
                     (ttable.location_id == ifield) & \
                     (ttable.tag == "ISO2") & \
                     (ttable.value.belongs(countries))
        else:
            # All countries
            cquery = (table.level == "L0") & \
                     (table.end_date == None) & \
                     (table.deleted == False)

        if current.deployment_settings.get_gis_spatialdb():
            spatial = True
            _field = table.the_geom
            if simplify:
                # Do the Simplify & GeoJSON direct from the DB
                field = _field.st_simplify(simplify).st_asgeojson(precision=precision).with_alias("geojson")
            else:
                # Do the GeoJSON direct from the DB
                field = _field.st_asgeojson(precision=precision).with_alias("geojson")
        else:
            spatial = False
            field = table.wkt
            if simplify:
                _simplify = GIS.simplify
            else:
                from shapely.wkt import loads as wkt_loads
                from ...geojson import dumps
                try:
                    # Enable C-based speedups available from 1.2.10+
                    from shapely import speedups
                    speedups.enable()
                except:
                    current.log.info("S3GIS",
                                     "Upgrade Shapely for Performance enhancements")

        folder = os.path.join(current.request.folder, "static", "cache")

        features = []
        append = features.append

        if "L0" in levels:
            # Reduce the decimals in output by 1
            _decimals = precision -1
            if spatial:
                if simplify:
                    field = _field.st_simplify(simplify).st_asgeojson(precision=_decimals).with_alias("geojson")
                else:
                    field = _field.st_asgeojson(precision=_decimals).with_alias("geojson")

            countries = db(cquery).select(ifield,
                                          field)
            for row in countries:
                if spatial:
                    id = row["gis_location"].id
                    geojson = row.geojson
                elif simplify:
                    id = row.id
                    wkt = row.wkt
                    if wkt:
                        geojson = _simplify(wkt, tolerance=simplify,
                                            precision=_decimals,
                                            output="geojson")
                    else:
                        name = db(table.id == id).select(table.name,
                                                         limitby = (0, 1)).first().name
                        sys.stderr.write("No WKT: L0 %s %s\n" % (name, id))
                        continue
                else:
                    id = row.id
                    shape = wkt_loads(row.wkt)
                    # Compact Encoding
                    geojson = dumps(shape, separators=JSONSEPARATORS)
                if geojson:
                    f = {"type": "Feature",
                         "properties": {"id": id},
                         "geometry": json.loads(geojson),
                         }
                    append(f)

            if features:
                data = {"type": "FeatureCollection",
                        "features": features,
                        }
                # Output to file
                filename = os.path.join(folder, "countries.geojson")
                File = open(filename, "w")
                File.write(json.dumps(data, separators=JSONSEPARATORS))
                File.close()

        q1 = (table.level == "L1") & \
             (table.deleted == False) & \
             (table.end_date == None)
        q2 = (table.level == "L2") & \
             (table.deleted == False) & \
             (table.end_date == None)
        q3 = (table.level == "L3") & \
             (table.deleted == False) & \
             (table.end_date == None)
        q4 = (table.level == "L4") & \
             (table.deleted == False) & \
             (table.end_date == None)

        if "L1" in levels:
            if "L0" not in levels:
                countries = db(cquery).select(ifield)
            if simplify:
                # We want greater precision when zoomed-in more
                simplify = simplify / 2 # 0.005 with default setting
                if spatial:
                    field = _field.st_simplify(simplify).st_asgeojson(precision=precision).with_alias("geojson")
            for country in countries:
                if not spatial or "L0" not in levels:
                    _id = country.id
                else:
                    _id = country["gis_location"].id
                query = q1 & (table.parent == _id)
                features = []
                append = features.append
                rows = db(query).select(ifield,
                                        field)
                for row in rows:
                    if spatial:
                        id = row["gis_location"].id
                        geojson = row.geojson
                    elif simplify:
                        id = row.id
                        wkt = row.wkt
                        if wkt:
                            geojson = _simplify(wkt, tolerance=simplify,
                                                precision=precision,
                                                output="geojson")
                        else:
                            name = db(table.id == id).select(table.name,
                                                             limitby = (0, 1)).first().name
                            sys.stderr.write("No WKT: L1 %s %s\n" % (name, id))
                            continue
                    else:
                        id = row.id
                        shape = wkt_loads(row.wkt)
                        # Compact Encoding
                        geojson = dumps(shape, separators=JSONSEPARATORS)
                    if geojson:
                        f = {"type": "Feature",
                             "properties": {"id": id},
                             "geometry": json.loads(geojson)
                             }
                        append(f)

                if features:
                    data = {"type": "FeatureCollection",
                            "features": features
                            }
                    # Output to file
                    filename = os.path.join(folder, "1_%s.geojson" % _id)
                    File = open(filename, "w")
                    File.write(json.dumps(data, separators=JSONSEPARATORS))
                    File.close()
                else:
                    current.log.debug("No L1 features in %s" % _id)

        if "L2" in levels:
            if "L0" not in levels and "L1" not in levels:
                countries = db(cquery).select(ifield)
            if simplify:
                # We want greater precision when zoomed-in more
                simplify = simplify / 4 # 0.00125 with default setting
                if spatial:
                    field = _field.st_simplify(simplify).st_asgeojson(precision=precision).with_alias("geojson")
            for country in countries:
                if not spatial or "L0" not in levels:
                    id = country.id
                else:
                    id = country["gis_location"].id
                query = q1 & (table.parent == id)
                l1s = db(query).select(ifield)
                for l1 in l1s:
                    query = q2 & (table.parent == l1.id)
                    features = []
                    append = features.append
                    rows = db(query).select(ifield,
                                            field)
                    for row in rows:
                        if spatial:
                            id = row["gis_location"].id
                            geojson = row.geojson
                        elif simplify:
                            id = row.id
                            wkt = row.wkt
                            if wkt:
                                geojson = _simplify(wkt, tolerance=simplify,
                                                    precision=precision,
                                                    output="geojson")
                            else:
                                name = db(table.id == id).select(table.name,
                                                                 limitby = (0, 1)).first().name
                                sys.stderr.write("No WKT: L2 %s %s\n" % (name, id))
                                continue
                        else:
                            id = row.id
                            shape = wkt_loads(row.wkt)
                            # Compact Encoding
                            geojson = dumps(shape, separators=JSONSEPARATORS)
                        if geojson:
                            f = {"type": "Feature",
                                 "properties": {"id": id},
                                 "geometry": json.loads(geojson),
                                 }
                            append(f)

                    if features:
                        data = {"type": "FeatureCollection",
                                "features": features,
                                }
                        # Output to file
                        filename = os.path.join(folder, "2_%s.geojson" % l1.id)
                        File = open(filename, "w")
                        File.write(json.dumps(data, separators=JSONSEPARATORS))
                        File.close()
                    else:
                        current.log.debug("No L2 features in %s" % l1.id)

        if "L3" in levels:
            if "L0" not in levels and "L1" not in levels and "L2" not in levels:
                countries = db(cquery).select(ifield)
            if simplify:
                # We want greater precision when zoomed-in more
                simplify = simplify / 2 # 0.000625 with default setting
                if spatial:
                    field = _field.st_simplify(simplify).st_asgeojson(precision=precision).with_alias("geojson")
            for country in countries:
                if not spatial or "L0" not in levels:
                    id = country.id
                else:
                    id = country["gis_location"].id
                query = q1 & (table.parent == id)
                l1s = db(query).select(ifield)
                for l1 in l1s:
                    query = q2 & (table.parent == l1.id)
                    l2s = db(query).select(ifield)
                    for l2 in l2s:
                        query = q3 & (table.parent == l2.id)
                        features = []
                        append = features.append
                        rows = db(query).select(ifield,
                                                field)
                        for row in rows:
                            if spatial:
                                id = row["gis_location"].id
                                geojson = row.geojson
                            elif simplify:
                                id = row.id
                                wkt = row.wkt
                                if wkt:
                                    geojson = _simplify(wkt, tolerance=simplify,
                                                        precision=precision,
                                                        output="geojson")
                                else:
                                    name = db(table.id == id).select(table.name,
                                                                     limitby = (0, 1)).first().name
                                    sys.stderr.write("No WKT: L3 %s %s\n" % (name, id))
                                    continue
                            else:
                                id = row.id
                                shape = wkt_loads(row.wkt)
                                # Compact Encoding
                                geojson = dumps(shape, separators=JSONSEPARATORS)
                            if geojson:
                                f = {"type": "Feature",
                                     "properties": {"id": id},
                                     "geometry": json.loads(geojson),
                                     }
                                append(f)

                        if features:
                            data = {"type": "FeatureCollection",
                                    "features": features,
                                    }
                            # Output to file
                            filename = os.path.join(folder, "3_%s.geojson" % l2.id)
                            File = open(filename, "w")
                            File.write(json.dumps(data, separators=JSONSEPARATORS))
                            File.close()
                        else:
                            current.log.debug("No L3 features in %s" % l2.id)

        if "L4" in levels:
            if "L0" not in levels and "L1" not in levels and "L2" not in levels and "L3" not in levels:
                countries = db(cquery).select(ifield)
            if simplify:
                # We want greater precision when zoomed-in more
                simplify = simplify / 2 # 0.0003125 with default setting
                if spatial:
                    field = _field.st_simplify(simplify).st_asgeojson(precision=precision).with_alias("geojson")
            for country in countries:
                if not spatial or "L0" not in levels:
                    id = country.id
                else:
                    id = country["gis_location"].id
                query = q1 & (table.parent == id)
                l1s = db(query).select(ifield)
                for l1 in l1s:
                    query = q2 & (table.parent == l1.id)
                    l2s = db(query).select(ifield)
                    for l2 in l2s:
                        query = q3 & (table.parent == l2.id)
                        l3s = db(query).select(ifield)
                        for l3 in l3s:
                            query = q4 & (table.parent == l3.id)
                            features = []
                            append = features.append
                            rows = db(query).select(ifield,
                                                    field)
                            for row in rows:
                                if spatial:
                                    id = row["gis_location"].id
                                    geojson = row.geojson
                                elif simplify:
                                    id = row.id
                                    wkt = row.wkt
                                    if wkt:
                                        geojson = _simplify(wkt, tolerance=simplify,
                                                            precision=precision,
                                                            output="geojson")
                                    else:
                                        name = db(table.id == id).select(table.name,
                                                                         limitby = (0, 1)).first().name
                                        sys.stderr.write("No WKT: L4 %s %s\n" % (name, id))
                                        continue
                                else:
                                    id = row.id
                                    shape = wkt_loads(row.wkt)
                                    # Compact Encoding
                                    geojson = dumps(shape, separators=JSONSEPARATORS)
                                if geojson:
                                    f = {"type": "Feature",
                                         "properties": {"id": id},
                                         "geometry": json.loads(geojson),
                                         }
                                    append(f)

                            if features:
                                data = {"type": "FeatureCollection",
                                        "features": features,
                                        }
                                # Output to file
                                filename = os.path.join(folder, "4_%s.geojson" % l3.id)
                                File = open(filename, "w")
                                File.write(json.dumps(data, separators=JSONSEPARATORS))
                                File.close()
                            else:
                                current.log.debug("No L4 features in %s" % l3.id)

    # -------------------------------------------------------------------------
    def import_admin_areas(self,
                           source="gadmv1",
                           countries=[],
                           levels=["L0", "L1", "L2"]
                          ):
        """
            Import Admin Boundaries into the Locations table

            Args:
                source - Source to get the data from.
                         Currently only GADM is supported: http://gadm.org
                countries - List of ISO2 countrycodes to download data for
                            defaults to all countries
                levels - Which levels of the hierarchy to import, defaults to
                         all 3 supported levels
        """

        if source == "gadmv1":
            try:
                from osgeo import ogr
            except:
                current.log.error("Unable to import ogr. Please install python-gdal bindings: GDAL-1.8.1+")
                return

            if "L0" in levels:
                self.import_gadm1_L0(ogr, countries=countries)
            if "L1" in levels:
                self.import_gadm1(ogr, "L1", countries=countries)
            if "L2" in levels:
                self.import_gadm1(ogr, "L2", countries=countries)

            current.log.debug("All done!")

        elif source == "gadmv1":
            try:
                from osgeo import ogr
            except:
                current.log.error("Unable to import ogr. Please install python-gdal bindings: GDAL-1.8.1+")
                return

            if "L0" in levels:
                self.import_gadm2(ogr, "L0", countries=countries)
            if "L1" in levels:
                self.import_gadm2(ogr, "L1", countries=countries)
            if "L2" in levels:
                self.import_gadm2(ogr, "L2", countries=countries)

            current.log.debug("All done!")

        else:
            current.log.warning("Only GADM is currently supported")
            return

        return

    # -------------------------------------------------------------------------
    @staticmethod
    def import_gadm1_L0(ogr, countries=[]):
        """
            Import L0 Admin Boundaries into the Locations table from GADMv1
                - designed to be called from import_admin_areas()
                - assumes that basic prepop has been done, so that no new
                  records need to be created

            Args:
                ogr - The OGR Python module
                countries - List of ISO2 countrycodes to download data for
                            defaults to all countries
        """

        db = current.db
        s3db = current.s3db
        ttable = s3db.gis_location_tag
        table = db.gis_location

        layer = {
            "url" : "http://gadm.org/data/gadm_v1_lev0_shp.zip",
            "zipfile" : "gadm_v1_lev0_shp.zip",
            "shapefile" : "gadm1_lev0",
            "codefield" : "ISO2", # This field is used to uniquely identify the L0 for updates
            "code2field" : "ISO"  # This field is used to uniquely identify the L0 for parenting the L1s
        }

        # Copy the current working directory to revert back to later
        cwd = os.getcwd()

        # Create the working directory
        TEMP = os.path.join(cwd, "temp")
        if not os.path.exists(TEMP): # use web2py/temp/GADMv1 as a cache
            import tempfile
            TEMP = tempfile.gettempdir()
        tempPath = os.path.join(TEMP, "GADMv1")
        if not os.path.exists(tempPath):
            try:
                os.mkdir(tempPath)
            except OSError:
                current.log.error("Unable to create temp folder %s!" % tempPath)
                return

        # Set the current working directory
        os.chdir(tempPath)

        layerName = layer["shapefile"]

        # Check if file has already been downloaded
        fileName = layer["zipfile"]
        if not os.path.isfile(fileName):
            # Download the file
            from gluon.tools import fetch
            url = layer["url"]
            current.log.debug("Downloading %s" % url)
            try:
                file = fetch(url)
            except URLError as exception:
                current.log.error(exception)
                return
            fp = StringIO(file)
        else:
            current.log.debug("Using existing file %s" % fileName)
            fp = open(fileName)

        # Unzip it
        current.log.debug("Unzipping %s" % layerName)
        import zipfile
        myfile = zipfile.ZipFile(fp)
        for ext in ("dbf", "prj", "sbn", "sbx", "shp", "shx"):
            fileName = "%s.%s" % (layerName, ext)
            file = myfile.read(fileName)
            f = open(fileName, "w")
            f.write(file)
            f.close()
        myfile.close()

        # Use OGR to read Shapefile
        current.log.debug("Opening %s.shp" % layerName)
        ds = ogr.Open("%s.shp" % layerName)
        if ds is None:
            current.log.error("Open failed.\n")
            return

        lyr = ds.GetLayerByName(layerName)

        lyr.ResetReading()

        codeField = layer["codefield"]
        code2Field = layer["code2field"]
        for feat in lyr:
            code = feat.GetField(codeField)
            if not code:
                # Skip the entries which aren't countries
                continue
            if countries and code not in countries:
                # Skip the countries which we're not interested in
                continue

            geom = feat.GetGeometryRef()
            if geom is not None:
                if geom.GetGeometryType() == ogr.wkbPoint:
                    pass
                else:
                    query = (table.id == ttable.location_id) & \
                            (ttable.tag == "ISO2") & \
                            (ttable.value == code)
                    wkt = geom.ExportToWkt()
                    if wkt.startswith("LINESTRING"):
                        gis_feature_type = 2
                    elif wkt.startswith("POLYGON"):
                        gis_feature_type = 3
                    elif wkt.startswith("MULTIPOINT"):
                        gis_feature_type = 4
                    elif wkt.startswith("MULTILINESTRING"):
                        gis_feature_type = 5
                    elif wkt.startswith("MULTIPOLYGON"):
                        gis_feature_type = 6
                    elif wkt.startswith("GEOMETRYCOLLECTION"):
                        gis_feature_type = 7
                    code2 = feat.GetField(code2Field)
                    #area = feat.GetField("Shape_Area")
                    try:
                        id = db(query).select(table.id,
                                              limitby = (0, 1)).first().id
                        query = (table.id == id)
                        db(query).update(gis_feature_type=gis_feature_type,
                                         wkt=wkt)
                        ttable.insert(location_id = id,
                                      tag = "ISO3",
                                      value = code2)
                        #ttable.insert(location_id = location_id,
                        #              tag = "area",
                        #              value = area)
                    except db._adapter.driver.OperationalError:
                        current.log.error(sys.exc_info()[1])

            else:
                current.log.debug("No geometry\n")

        # Close the shapefile
        ds.Destroy()

        db.commit()

        # Revert back to the working directory as before.
        os.chdir(cwd)

        return

    # -------------------------------------------------------------------------
    def import_gadm1(self, ogr, level="L1", countries=[]):
        """
            Import L1 Admin Boundaries into the Locations table from GADMv1
            - designed to be called from import_admin_areas()
            - assumes a fresh database with just Countries imported

            Args:
                ogr - The OGR Python module
                level - "L1" or "L2"
                countries - List of ISO2 countrycodes to download data for
                            defaults to all countries
        """

        if level == "L1":
            layer = {
                "url" : "http://gadm.org/data/gadm_v1_lev1_shp.zip",
                "zipfile" : "gadm_v1_lev1_shp.zip",
                "shapefile" : "gadm1_lev1",
                "namefield" : "NAME_1",
                # Uniquely identify the L1 for updates
                "sourceCodeField" : "ID_1",
                "edenCodeField" : "GADM1",
                # Uniquely identify the L0 for parenting the L1s
                "parent" : "L0",
                "parentSourceCodeField" : "ISO",
                "parentEdenCodeField" : "ISO3",
            }
        elif level == "L2":
            layer = {
                "url" : "http://biogeo.ucdavis.edu/data/gadm/gadm_v1_lev2_shp.zip",
                "zipfile" : "gadm_v1_lev2_shp.zip",
                "shapefile" : "gadm_v1_lev2",
                "namefield" : "NAME_2",
                # Uniquely identify the L2 for updates
                "sourceCodeField" : "ID_2",
                "edenCodeField" : "GADM2",
                # Uniquely identify the L0 for parenting the L1s
                "parent" : "L1",
                "parentSourceCodeField" : "ID_1",
                "parentEdenCodeField" : "GADM1",
            }
        else:
            current.log.warning("Level %s not supported!" % level)
            return

        import csv
        import shutil
        import zipfile

        db = current.db
        s3db = current.s3db
        cache = s3db.cache
        table = s3db.gis_location
        ttable = s3db.gis_location_tag

        csv.field_size_limit(2**20 * 100)  # 100 megs

        # Not all the data is encoded like this
        # (unable to determine encoding - appears to be damaged in source):
        # Azerbaijan L1
        # Vietnam L1 & L2
        ENCODING = "cp1251"

        # from http://docs.python.org/library/csv.html#csv-examples
        # TODO rewrite for Py3
        def latin_csv_reader(unicode_csv_data, dialect=csv.excel, **kwargs):
            for row in csv.reader(unicode_csv_data):
                yield [unicode(cell, ENCODING) for cell in row]

        # TODO rewrite for Py3
        def latin_dict_reader(data, dialect=csv.excel, **kwargs):
            reader = latin_csv_reader(data, dialect=dialect, **kwargs)
            headers = reader.next()
            for r in reader:
                yield dict(zip(headers, r))

        # Copy the current working directory to revert back to later
        cwd = os.getcwd()

        # Create the working directory
        TEMP = os.path.join(cwd, "temp")
        if not os.path.exists(TEMP): # use web2py/temp/GADMv1 as a cache
            import tempfile
            TEMP = tempfile.gettempdir()
        tempPath = os.path.join(TEMP, "GADMv1")
        if not os.path.exists(tempPath):
            try:
                os.mkdir(tempPath)
            except OSError:
                current.log.error("Unable to create temp folder %s!" % tempPath)
                return

        # Set the current working directory
        os.chdir(tempPath)

        # Remove any existing CSV folder to allow the new one to be created
        try:
            shutil.rmtree("CSV")
        except OSError:
            # Folder doesn't exist, so should be creatable
            pass

        layerName = layer["shapefile"]

        # Check if file has already been downloaded
        fileName = layer["zipfile"]
        if not os.path.isfile(fileName):
            # Download the file
            from gluon.tools import fetch
            url = layer["url"]
            current.log.debug("Downloading %s" % url)
            try:
                file = fetch(url)
            except URLError as exception:
                current.log.error(exception)
                # Revert back to the working directory as before.
                os.chdir(cwd)
                return
            fp = StringIO(file)
        else:
            current.log.debug("Using existing file %s" % fileName)
            fp = open(fileName)

        # Unzip it
        current.log.debug("Unzipping %s" % layerName)
        myfile = zipfile.ZipFile(fp)
        for ext in ("dbf", "prj", "sbn", "sbx", "shp", "shx"):
            fileName = "%s.%s" % (layerName, ext)
            file = myfile.read(fileName)
            f = open(fileName, "w")
            f.write(file)
            f.close()
        myfile.close()

        # Convert to CSV
        current.log.debug("Converting %s.shp to CSV" % layerName)
        # Simplified version of generic Shapefile Importer:
        # http://svn.osgeo.org/gdal/trunk/gdal/swig/python/samples/ogr2ogr.py
        bSkipFailures = False
        nGroupTransactions = 200
        nFIDToFetch = ogr.NullFID
        inputFileName = "%s.shp" % layerName
        inputDS = ogr.Open(inputFileName, False)
        outputFileName = "CSV"
        outputDriver = ogr.GetDriverByName("CSV")
        outputDS = outputDriver.CreateDataSource(outputFileName, options=[])
        # GADM only has 1 layer/source
        inputLayer = inputDS.GetLayer(0)
        inputFDefn = inputLayer.GetLayerDefn()
        # Create the output Layer
        outputLayer = outputDS.CreateLayer(layerName)
        # Copy all Fields
        #papszFieldTypesToString = []
        inputFieldCount = inputFDefn.GetFieldCount()
        panMap = [-1] * inputFieldCount
        outputFDefn = outputLayer.GetLayerDefn()
        nDstFieldCount = 0
        if outputFDefn is not None:
            nDstFieldCount = outputFDefn.GetFieldCount()
        for iField in range(inputFieldCount):
            inputFieldDefn = inputFDefn.GetFieldDefn(iField)
            oFieldDefn = ogr.FieldDefn(inputFieldDefn.GetNameRef(),
                                       inputFieldDefn.GetType())
            oFieldDefn.SetWidth(inputFieldDefn.GetWidth())
            oFieldDefn.SetPrecision(inputFieldDefn.GetPrecision())
            # The field may have been already created at layer creation
            iDstField = -1
            if outputFDefn is not None:
                iDstField = outputFDefn.GetFieldIndex(oFieldDefn.GetNameRef())
            if iDstField >= 0:
                panMap[iField] = iDstField
            elif outputLayer.CreateField(oFieldDefn) == 0:
                # now that we've created a field, GetLayerDefn() won't return NULL
                if outputFDefn is None:
                    outputFDefn = outputLayer.GetLayerDefn()
                panMap[iField] = nDstFieldCount
                nDstFieldCount = nDstFieldCount + 1
        # Transfer features
        nFeaturesInTransaction = 0
        #iSrcZField = -1
        inputLayer.ResetReading()
        if nGroupTransactions > 0:
            outputLayer.StartTransaction()
        while True:
            poDstFeature = None
            if nFIDToFetch != ogr.NullFID:
                # Only fetch feature on first pass.
                if nFeaturesInTransaction == 0:
                    poFeature = inputLayer.GetFeature(nFIDToFetch)
                else:
                    poFeature = None
            else:
                poFeature = inputLayer.GetNextFeature()
            if poFeature is None:
                break
            nParts = 0
            nIters = 1
            for iPart in range(nIters):
                nFeaturesInTransaction = nFeaturesInTransaction + 1
                if nFeaturesInTransaction == nGroupTransactions:
                    outputLayer.CommitTransaction()
                    outputLayer.StartTransaction()
                    nFeaturesInTransaction = 0
                poDstFeature = ogr.Feature(outputLayer.GetLayerDefn())
                if poDstFeature.SetFromWithMap(poFeature, 1, panMap) != 0:
                    if nGroupTransactions > 0:
                        outputLayer.CommitTransaction()
                    current.log.error("Unable to translate feature %d from layer %s" % \
                                (poFeature.GetFID(), inputFDefn.GetName()))
                    # Revert back to the working directory as before.
                    os.chdir(cwd)
                    return
                poDstGeometry = poDstFeature.GetGeometryRef()
                if poDstGeometry is not None:
                    if nParts > 0:
                        # For -explodecollections, extract the iPart(th) of the geometry
                        poPart = poDstGeometry.GetGeometryRef(iPart).Clone()
                        poDstFeature.SetGeometryDirectly(poPart)
                        poDstGeometry = poPart
                if outputLayer.CreateFeature(poDstFeature) != 0 and \
                   not bSkipFailures:
                    if nGroupTransactions > 0:
                        outputLayer.RollbackTransaction()
                    # Revert back to the working directory as before.
                    os.chdir(cwd)
                    return
        if nGroupTransactions > 0:
            outputLayer.CommitTransaction()
        # Cleanup
        outputDS.Destroy()
        inputDS.Destroy()

        fileName = "%s.csv" % layerName
        filePath = os.path.join("CSV", fileName)
        os.rename(filePath, fileName)
        os.removedirs("CSV")

        # Use OGR to read SHP for geometry
        current.log.debug("Opening %s.shp" % layerName)
        ds = ogr.Open("%s.shp" % layerName)
        if ds is None:
            current.log.debug("Open failed.\n")
            # Revert back to the working directory as before.
            os.chdir(cwd)
            return

        lyr = ds.GetLayerByName(layerName)

        lyr.ResetReading()

        # Use CSV for Name
        current.log.debug("Opening %s.csv" % layerName)
        rows = latin_dict_reader(open("%s.csv" % layerName))

        nameField = layer["namefield"]
        sourceCodeField = layer["sourceCodeField"]
        edenCodeField = layer["edenCodeField"]
        parentSourceCodeField = layer["parentSourceCodeField"]
        parentLevel = layer["parent"]
        parentEdenCodeField = layer["parentEdenCodeField"]
        parentCodeQuery = (ttable.tag == parentEdenCodeField)
        count = 0
        for row in rows:
            # Read Attributes
            feat = lyr[count]

            parentCode = feat.GetField(parentSourceCodeField)
            query = (table.level == parentLevel) & \
                    parentCodeQuery & \
                    (ttable.value == parentCode)
            parent = db(query).select(table.id,
                                      ttable.value,
                                      limitby = (0, 1),
                                      cache=cache).first()
            if not parent:
                # Skip locations for which we don't have a valid parent
                current.log.warning("Skipping - cannot find parent with key: %s, value: %s" % \
                            (parentEdenCodeField, parentCode))
                count += 1
                continue

            if countries:
                # Skip the countries which we're not interested in
                if level == "L1":
                    if parent["gis_location_tag"].value not in countries:
                        #current.log.warning("Skipping %s as not in countries list" % parent["gis_location_tag"].value)
                        count += 1
                        continue
                else:
                    # Check grandparent
                    country = self.get_parent_country(parent.id,
                                                      key_type="code")
                    if country not in countries:
                        count += 1
                        continue

            # This is got from CSV in order to be able to handle the encoding
            name = row.pop(nameField)
            name.encode("utf8")

            code = feat.GetField(sourceCodeField)
            #area = feat.GetField("Shape_Area")

            geom = feat.GetGeometryRef()
            if geom is not None:
                if geom.GetGeometryType() == ogr.wkbPoint:
                    lat = geom.GetX()
                    lon = geom.GetY()
                    id = table.insert(name=name,
                                      level=level,
                                      gis_feature_type=1,
                                      lat=lat,
                                      lon=lon,
                                      parent=parent.id)
                    ttable.insert(location_id = id,
                                  tag = edenCodeField,
                                  value = code)
                    # ttable.insert(location_id = id,
                                  # tag = "area",
                                  # value = area)
                else:
                    wkt = geom.ExportToWkt()
                    if wkt.startswith("LINESTRING"):
                        gis_feature_type = 2
                    elif wkt.startswith("POLYGON"):
                        gis_feature_type = 3
                    elif wkt.startswith("MULTIPOINT"):
                        gis_feature_type = 4
                    elif wkt.startswith("MULTILINESTRING"):
                        gis_feature_type = 5
                    elif wkt.startswith("MULTIPOLYGON"):
                        gis_feature_type = 6
                    elif wkt.startswith("GEOMETRYCOLLECTION"):
                        gis_feature_type = 7
                    id = table.insert(name=name,
                                      level=level,
                                      gis_feature_type=gis_feature_type,
                                      wkt=wkt,
                                      parent=parent.id)
                    ttable.insert(location_id = id,
                                  tag = edenCodeField,
                                  value = code)
                    # ttable.insert(location_id = id,
                                  # tag = "area",
                                  # value = area)
            else:
                current.log.debug("No geometry\n")

            count += 1

        # Close the shapefile
        ds.Destroy()

        db.commit()

        current.log.debug("Updating Location Tree...")
        try:
            self.update_location_tree()
        except MemoryError:
            # If doing all L2s, it can break memory limits
            # @ToDo: Check now that we're doing by level
            current.log.critical("Memory error when trying to update_location_tree()!")

        db.commit()

        # Revert back to the working directory as before.
        os.chdir(cwd)

        return

    # -------------------------------------------------------------------------
    @staticmethod
    def import_gadm2(ogr, level="L0", countries=[]):
        """
            Import Admin Boundaries into the Locations table from GADMv2
            - designed to be called from import_admin_areas()
            - assumes that basic prepop has been done, so that no new L0 records need to be created

            Args:
                ogr - The OGR Python module
                level - The OGR Python module
                countries - List of ISO2 countrycodes to download data for
                               defaults to all countries

            TODO Complete this
                - not currently possible to get all data from the 1 file easily
                - no ISO2
                - needs updating for gis_location_tag model
                - only the lowest available levels accessible
                - use GADMv1 for L0, L1, L2 & GADMv2 for specific lower?
        """

        if level == "L0":
            codeField = "ISO2"   # This field is used to uniquely identify the L0 for updates
            code2Field = "ISO"   # This field is used to uniquely identify the L0 for parenting the L1s
        elif level == "L1":
            #nameField = "NAME_1"
            codeField = "ID_1"   # This field is used to uniquely identify the L1 for updates
            code2Field = "ISO"   # This field is used to uniquely identify the L0 for parenting the L1s
            #parent = "L0"
            #parentCode = "code2"
        elif level == "L2":
            #nameField = "NAME_2"
            codeField = "ID_2"   # This field is used to uniquely identify the L2 for updates
            code2Field = "ID_1"  # This field is used to uniquely identify the L1 for parenting the L2s
            #parent = "L1"
            #parentCode = "code"
        else:
            current.log.error("Level %s not supported!" % level)
            return

        db = current.db
        s3db = current.s3db
        table = s3db.gis_location

        url = "http://gadm.org/data2/gadm_v2_shp.zip"
        zipfile = "gadm_v2_shp.zip"
        shapefile = "gadm2"

        # Copy the current working directory to revert back to later
        old_working_directory = os.getcwd()

        # Create the working directory
        if os.path.exists(os.path.join(os.getcwd(), "temp")): # use web2py/temp/GADMv2 as a cache
            TEMP = os.path.join(os.getcwd(), "temp")
        else:
            import tempfile
            TEMP = tempfile.gettempdir()
        tempPath = os.path.join(TEMP, "GADMv2")
        try:
            os.mkdir(tempPath)
        except OSError:
            # Folder already exists - reuse
            pass

        # Set the current working directory
        os.chdir(tempPath)

        layerName = shapefile

        # Check if file has already been downloaded
        fileName = zipfile
        if not os.path.isfile(fileName):
            # Download the file
            from gluon.tools import fetch
            current.log.debug("Downloading %s" % url)
            try:
                file = fetch(url)
            except URLError as exception:
                current.log.error(exception)
                return
            fp = StringIO(file)
        else:
            current.log.debug("Using existing file %s" % fileName)
            fp = open(fileName)

        # Unzip it
        current.log.debug("Unzipping %s" % layerName)
        import zipfile
        myfile = zipfile.ZipFile(fp)
        for ext in ("dbf", "prj", "sbn", "sbx", "shp", "shx"):
            fileName = "%s.%s" % (layerName, ext)
            file = myfile.read(fileName)
            f = open(fileName, "w")
            f.write(file)
            f.close()
        myfile.close()

        # Use OGR to read Shapefile
        current.log.debug("Opening %s.shp" % layerName)
        ds = ogr.Open("%s.shp" % layerName)
        if ds is None:
            current.log.debug("Open failed.\n")
            return

        lyr = ds.GetLayerByName(layerName)

        lyr.ResetReading()

        for feat in lyr:
            code = feat.GetField(codeField)
            if not code:
                # Skip the entries which aren't countries
                continue
            if countries and code not in countries:
                # Skip the countries which we're not interested in
                continue

            geom = feat.GetGeometryRef()
            if geom is not None:
                if geom.GetGeometryType() == ogr.wkbPoint:
                    pass
                else:
                    ## FIXME
                    ##query = (table.code == code)
                    wkt = geom.ExportToWkt()
                    if wkt.startswith("LINESTRING"):
                        gis_feature_type = 2
                    elif wkt.startswith("POLYGON"):
                        gis_feature_type = 3
                    elif wkt.startswith("MULTIPOINT"):
                        gis_feature_type = 4
                    elif wkt.startswith("MULTILINESTRING"):
                        gis_feature_type = 5
                    elif wkt.startswith("MULTIPOLYGON"):
                        gis_feature_type = 6
                    elif wkt.startswith("GEOMETRYCOLLECTION"):
                        gis_feature_type = 7
                    #code2 = feat.GetField(code2Field)
                    #area = feat.GetField("Shape_Area")
                    try:
                        ## FIXME
                        db(query).update(gis_feature_type=gis_feature_type,
                                         wkt=wkt)
                                         #code2=code2,
                                         #area=area
                    except db._adapter.driver.OperationalError as exception:
                        current.log.error(exception)

            else:
                current.log.debug("No geometry\n")

        # Close the shapefile
        ds.Destroy()

        db.commit()

        # Revert back to the working directory as before.
        os.chdir(old_working_directory)

        return

    # -------------------------------------------------------------------------
    def import_geonames(self, country, level=None):
        """
            Import Locations from the Geonames database

            Args:
                country: the 2-letter country code
                level: the ADM level to import

            Designed to be run from the CLI
            Levels should be imported sequentially.
            It is assumed that L0 exists in the DB already
            L1-L3 may have been imported from Shapefiles with Polygon info
            Geonames can then be used to populate the lower levels of hierarchy
        """

        import codecs

        from shapely.geometry import point
        from shapely.errors import ReadingError
        from shapely.wkt import loads as wkt_loads

        try:
            # Enable C-based speedups available from 1.2.10+
            from shapely import speedups
            speedups.enable()
        except:
            current.log.info("S3GIS",
                             "Upgrade Shapely for Performance enhancements")

        db = current.db
        s3db = current.s3db
        #cache = s3db.cache
        request = current.request
        #settings = current.deployment_settings
        table = s3db.gis_location
        ttable = s3db.gis_location_tag

        url = "http://download.geonames.org/export/dump/" + country + ".zip"

        cachepath = os.path.join(request.folder, "cache")
        filename = country + ".txt"
        filepath = os.path.join(cachepath, filename)
        if os.access(filepath, os.R_OK):
            cached = True
        else:
            cached = False
            if not os.access(cachepath, os.W_OK):
                current.log.error("Folder not writable", cachepath)
                return

        if not cached:
            # Download File
            from gluon.tools import fetch
            try:
                f = fetch(url)
            except HTTPError:
                e = sys.exc_info()[1]
                current.log.error("HTTP Error", e)
                return
            except URLError:
                e = sys.exc_info()[1]
                current.log.error("URL Error", e)
                return

            # Unzip File
            if f[:2] == "PK":
                # Unzip
                fp = StringIO(f)
                import zipfile
                myfile = zipfile.ZipFile(fp)
                try:
                    # Python 2.6+ only :/
                    # For now, 2.5 users need to download/unzip manually to cache folder
                    myfile.extract(filename, cachepath)
                    myfile.close()
                except IOError:
                    current.log.error("Zipfile contents don't seem correct!")
                    myfile.close()
                    return

        f = codecs.open(filepath, encoding="utf-8")
        # Downloaded file is worth keeping
        #os.remove(filepath)

        if level == "L1":
            fc = "ADM1"
            parent_level = "L0"
        elif level == "L2":
            fc = "ADM2"
            parent_level = "L1"
        elif level == "L3":
            fc = "ADM3"
            parent_level = "L2"
        elif level == "L4":
            fc = "ADM4"
            parent_level = "L3"
        else:
            # 5 levels of hierarchy or 4?
            # @ToDo make more extensible still
            #gis_location_hierarchy = self.get_location_hierarchy()
            try:
                #label = gis_location_hierarchy["L5"]
                level = "L5"
                parent_level = "L4"
            except:
                # ADM4 data in Geonames isn't always good (e.g. PK bad)
                level = "L4"
                parent_level = "L3"
            finally:
                fc = "PPL"

        deleted = (table.deleted == False)
        query = deleted & (table.level == parent_level)
        # Do the DB query once (outside loop)
        all_parents = db(query).select(table.wkt,
                                       table.lon_min,
                                       table.lon_max,
                                       table.lat_min,
                                       table.lat_max,
                                       table.id)
        if not all_parents:
            # No locations in the parent level found
            # - use the one higher instead
            parent_level = "L" + str(int(parent_level[1:]) + 1)
            query = deleted & (table.level == parent_level)
            all_parents = db(query).select(table.wkt,
                                           table.lon_min,
                                           table.lon_max,
                                           table.lat_min,
                                           table.lat_max,
                                           table.id)

        # Parse File
        current_row = 0

        def in_bbox(row, bbox):
            return (row.lon_min < bbox[0]) & \
                   (row.lon_max > bbox[1]) & \
                   (row.lat_min < bbox[2]) & \
                   (row.lat_max > bbox[3])
        for line in f:
            current_row += 1
            # Format of file: http://download.geonames.org/export/dump/readme.txt
            # - tab-limited values, columns:
            # geonameid         : integer id of record in geonames database
            # name              : name of geographical point (utf8)
            # asciiname         : name of geographical point in plain ascii characters
            # alternatenames    : alternatenames, comma separated
            # latitude          : latitude in decimal degrees (wgs84)
            # longitude         : longitude in decimal degrees (wgs84)
            # feature class     : see http://www.geonames.org/export/codes.html
            # feature code      : see http://www.geonames.org/export/codes.html
            # country code      : ISO-3166 2-letter country code
            # cc2               : alternate country codes, comma separated, ISO-3166 2-letter country code
            # admin1 code       : fipscode (subject to change to iso code)
            # admin2 code       : code for the second administrative division
            # admin3 code       : code for third level administrative division
            # admin4 code       : code for fourth level administrative division
            # population        : bigint
            # elevation         : in meters
            # dem               : digital elevation model, srtm3 or gtopo30
            # timezone          : the iana timezone id
            # modification date : date of last modification in yyyy-MM-dd format
            #
            parsed = line.split("\t")
            geonameid = parsed[0]
            name = parsed[1]
            lat = parsed[4]
            lon = parsed[5]
            feature_code = parsed[7]

            if feature_code == fc:
                # Add WKT
                lat = float(lat)
                lon = float(lon)
                wkt = self.latlon_to_wkt(lat, lon)

                shape = point.Point(lon, lat)

                # Add Bounds
                lon_min = lon_max = lon
                lat_min = lat_max = lat

                # Locate Parent
                parent = ""
                # 1st check for Parents whose bounds include this location (faster)
                for row in all_parents.find(lambda row: in_bbox(row, [lon_min, lon_max, lat_min, lat_max])):
                    # Search within this subset with a full geometry check
                    # Uses Shapely.
                    # @ToDo provide option to use PostGIS/Spatialite
                    try:
                        parent_shape = wkt_loads(row.wkt)
                        if parent_shape.intersects(shape):
                            parent = row.id
                            # Should be just a single parent
                            break
                    except ReadingError:
                        current.log.error("Error reading wkt of location with id", row.id)

                # Add entry to database
                new_id = table.insert(name=name,
                                      level=level,
                                      parent=parent,
                                      lat=lat,
                                      lon=lon,
                                      wkt=wkt,
                                      lon_min=lon_min,
                                      lon_max=lon_max,
                                      lat_min=lat_min,
                                      lat_max=lat_max)
                ttable.insert(location_id=new_id,
                              tag="geonames",
                              value=geonameid)
            else:
                continue

        current.log.debug("All done!")
        return

    # -------------------------------------------------------------------------
    @staticmethod
    def latlon_to_wkt(lat, lon):
        """
            Convert a LatLon to a WKT string

            >>> GIS.latlon_to_wkt(6, 80)
            'POINT (80 6)'
        """
        WKT = "POINT (%f %f)" % (lon, lat)
        return WKT

    # -------------------------------------------------------------------------
    @staticmethod
    def parse_location(wkt, lon=None, lat=None):
        """
            Parses a location from wkt, returning wkt, lat, lon, bounding box and type.
            For points, wkt may be None if lat and lon are provided; wkt will be generated.
            For lines and polygons, the lat, lon returned represent the shape's centroid.
            Centroid and bounding box will be None if Shapely is not available.
        """

        if not wkt:
            if not lon is not None and lat is not None:
                raise RuntimeError("Need wkt or lon+lat to parse a location")
            wkt = "POINT (%f %f)" % (lon, lat)
            geom_type = GEOM_TYPES["point"]
            bbox = (lon, lat, lon, lat)
        else:
            try:
                from shapely.wkt import loads as wkt_loads
                SHAPELY = True
            except:
                SHAPELY = False

            if SHAPELY:
                shape = wkt_loads(wkt)
                centroid = shape.centroid
                lat = centroid.y
                lon = centroid.x
                geom_type = GEOM_TYPES[shape.geom_type.lower()]
                bbox = shape.bounds
            else:
                lat = None
                lon = None
                geom_type = GEOM_TYPES[wkt.split("(")[0].lower()]
                bbox = None

        res = {"wkt": wkt, "lat": lat, "lon": lon, "gis_feature_type": geom_type}
        if bbox:
            res["lon_min"], res["lat_min"], res["lon_max"], res["lat_max"] = bbox

        return res

    # -------------------------------------------------------------------------
    @staticmethod
    def update_location_tree(feature=None, all_locations=False, propagating=False):
        """
            Update GIS Locations' Materialized path, Lx locations, Lat/Lon & the_geom
                - called onaccept for locations (async, where-possible)

            Args:
                feature: a feature dict to update the tree for
                         - if not provided then update the whole tree
                all_locations: passed to recursive calls to indicate that this
                               is an update of the whole tree. Used to avoid
                               repeated attempts to update hierarchy locations
                               with missing data (e.g. lacking some ancestor
                               level).
                propagating: passed to recursive calls to indicate that this
                             is a propagation update. Used to avoid repeated
                             attempts to update hierarchy locations with
                             missing data (e.g. lacking some ancestor level).

            Returns:
                the path of the feature
        """

        # During prepopulate, for efficiency, we don't update the location
        # tree, but rather leave that til after prepopulate is complete.
        if GIS.disable_update_location_tree:
            return None

        db = current.db
        try:
            table = db.gis_location
        except:
            table = current.s3db.gis_location
        update_location_tree = GIS.update_location_tree
        wkt_centroid = GIS.wkt_centroid

        fields = (table.id,
                  table.name,
                  table.level,
                  table.path,
                  table.parent,
                  table.L0,
                  table.L1,
                  table.L2,
                  table.L3,
                  table.L4,
                  table.L5,
                  table.lat,
                  table.lon,
                  table.wkt,
                  table.inherited
                  )

        # ---------------------------------------------------------------------
        def fixup(feature):
            """
                Fix all the issues with a Feature, assuming that
                - the corrections are in the feature
                - or they are Bounds / Centroid / WKT / the_geom issues
            """

            form = Storage()
            form.vars = form_vars = feature
            form.errors = Storage()
            if not form_vars.get("wkt"):
                # Point
                form_vars.update(gis_feature_type="1")

            # Calculate Bounds / Centroid / WKT / the_geom
            wkt_centroid(form)

            if form.errors:
                current.log.error("S3GIS: %s" % form.errors)
            else:
                wkt = form_vars.wkt
                if wkt and not wkt.startswith("POI"):
                    # Polygons aren't inherited
                    form_vars.update(inherited = False)
                if "update_record" in form_vars:
                    # Must be a Row
                    new_vars = {}
                    table_fields = table.fields
                    for v in form_vars:
                        if v in table_fields:
                            new_vars[v] = form_vars[v]
                    form_vars = new_vars

                try:
                    db(table.id == feature.id).update(**form_vars)
                except MemoryError:
                    current.log.error("S3GIS: Unable to set bounds & centroid for feature %s: MemoryError" % feature.id)

        # ---------------------------------------------------------------------
        def propagate(parent):
            """
                Propagate Lat/Lon down to any Features which inherit from this one

                Args:
                    parent: gis_location id of parent
            """

            # No need to filter out deleted since the parent FK is None for these records
            query = (table.parent == parent) & \
                    (table.inherited == True)
            rows = db(query).select(*fields)
            for row in rows:
                try:
                    update_location_tree(row, propagating=True)
                except RuntimeError:
                    current.log.error("Cannot propagate inherited latlon to child %s of location ID %s: too much recursion" % \
                        (row.id, parent))


        if not feature:
            # We are updating all locations.
            all_locations = True
            # Do in chunks to save memory and also do in correct order
            all_fields = (table.id, table.name, table.gis_feature_type,
                          table.L0, table.L1, table.L2, table.L3, table.L4,
                          table.lat, table.lon, table.wkt, table.inherited,
                          # Handle Countries which start with Bounds set, yet are Points
                          table.lat_min, table.lon_min, table.lat_max, table.lon_max,
                          table.path, table.parent)
            for level in ("L0", "L1", "L2", "L3", "L4", "L5", None):
                query = (table.level == level) & (table.deleted == False)
                try:
                    features = db(query).select(*all_fields)
                except MemoryError:
                    current.log.error("S3GIS: Unable to update Location Tree for level %s: MemoryError" % level)
                else:
                    for feature in features:
                        feature["level"] = level
                        wkt = feature["wkt"]
                        if wkt and not wkt.startswith("POI"):
                            # Polygons aren't inherited
                            feature["inherited"] = False
                        update_location_tree(feature)  # all_locations is False here
            # All Done!
            return None


        # Single Feature
        id = str(feature["id"]) if "id" in feature else None
        if not id:
            # Nothing we can do
            raise ValueError

        feature_get = feature.get

        # L0
        level = feature_get("level", False)
        name = feature_get("name", False)
        path = feature_get("path", False)
        # If we're processing all locations, and this is a hierarchy location,
        # and has already been processed (as evidenced by having a path) do not
        # process it again. Locations with a gap in their ancestor levels will
        # be regarded as missing data and sent through update_location_tree
        # recursively, but that missing data will not be filled in after the
        # location is processed once during the all-locations call.
        if all_locations and path and level:
            # This hierarchy location is already finalized.
            return path
        lat = feature_get("lat", False)
        lon = feature_get("lon", False)
        wkt = feature_get("wkt", False)
        L0 = feature_get("L0", False)
        if level == "L0":
            if name is False or path is False or lat is False or lon is False or \
               wkt is False or L0 is False:
                # Get the whole feature
                feature = db(table.id == id).select(table.id,
                                                    table.name,
                                                    table.path,
                                                    table.lat,
                                                    table.lon,
                                                    table.wkt,
                                                    table.L0,
                                                    limitby = (0, 1)).first()
                name = feature.name
                path = feature.path
                lat = feature.lat
                lon = feature.lon
                wkt = feature.wkt
                L0 = feature.L0

            if path != id or L0 != name or not wkt or lat is None:
                # Fix everything up
                path = id
                if lat is False:
                    lat = None
                if lon is False:
                    lon = None
                fix_vars = {"inherited": False,
                            "path": path,
                            "lat": lat,
                            "lon": lon,
                            "wkt": wkt or None,
                            "L0": name,
                            "L1": None,
                            "L2": None,
                            "L3": None,
                            "L4": None,
                            "L5": None,
                            }
                feature.update(**fix_vars)
                fixup(feature)

            if not all_locations:
                # Ensure that any locations which inherit their latlon from this one get updated
                propagate(id)

            return path


        fixup_required = False

        # L1
        inherited = feature_get("inherited", None)
        parent = feature_get("parent", False)
        L1 = feature_get("L1", False)
        if level == "L1":
            if inherited is None or name is False or parent is False or path is False or \
               lat is False or lon is False or wkt is False or \
               L0 is False or L1 is False:
                # Get the whole feature
                feature = db(table.id == id).select(table.id,
                                                    table.inherited,
                                                    table.name,
                                                    table.parent,
                                                    table.path,
                                                    table.lat,
                                                    table.lon,
                                                    table.wkt,
                                                    table.L0,
                                                    table.L1,
                                                    limitby = (0, 1)).first()
                inherited = feature.inherited
                name = feature.name
                parent = feature.parent
                path = feature.path
                lat = feature.lat
                lon = feature.lon
                wkt = feature.wkt
                L0 = feature.L0
                L1 = feature.L1

            if parent:
                _path = "%s/%s" % (parent, id)
                _L0 = db(table.id == parent).select(table.name,
                                                    table.lat,
                                                    table.lon,
                                                    limitby = (0, 1)).first()
                L0_name = _L0.name
                L0_lat = _L0.lat
                L0_lon = _L0.lon
            else:
                _path = id
                L0_name = None
                L0_lat = None
                L0_lon = None

            if inherited or lat is None or lon is None:
                fixup_required = True
                inherited = True
                lat = L0_lat
                lon = L0_lon
            elif path != _path or L0 != L0_name or L1 != name or not wkt:
                fixup_required = True

            if fixup_required:
                # Fix everything up
                if lat is False:
                    lat = None
                if lon is False:
                    lon = None
                fix_vars = {"inherited": inherited,
                            "path": _path,
                            "lat": lat,
                            "lon": lon,
                            "wkt": wkt or None,
                            "L0": L0_name,
                            "L1": name,
                            "L2": None,
                            "L3": None,
                            "L4": None,
                            "L5": None,
                            }
                feature.update(**fix_vars)
                fixup(feature)

            if not all_locations:
                # Ensure that any locations which inherit their latlon from this one get updated
                propagate(id)

            return _path


        # L2
        L2 = feature_get("L2", False)
        if level == "L2":
            if inherited is None or name is False or parent is False or path is False or \
               lat is False or lon is False or wkt is False or \
               L0 is False or L1 is False or L2 is False:
                # Get the whole feature
                feature = db(table.id == id).select(table.id,
                                                    table.inherited,
                                                    table.name,
                                                    table.parent,
                                                    table.path,
                                                    table.lat,
                                                    table.lon,
                                                    table.wkt,
                                                    table.L0,
                                                    table.L1,
                                                    table.L2,
                                                    limitby = (0, 1)).first()
                inherited = feature.inherited
                name = feature.name
                parent = feature.parent
                path = feature.path
                lat = feature.lat
                lon = feature.lon
                wkt = feature.wkt
                L0 = feature.L0
                L1 = feature.L1
                L2 = feature.L2

            if parent:
                Lx = db(table.id == parent).select(table.name,
                                                   table.level,
                                                   table.parent,
                                                   table.lat,
                                                   table.lon,
                                                   limitby = (0, 1)).first()
                if Lx.level == "L1":
                    L1_name = Lx.name
                    _parent = Lx.parent
                    if _parent:
                        _path = "%s/%s/%s" % (_parent, parent, id)
                        L0_name = db(table.id == _parent).select(table.name,
                                                                 limitby = (0, 1),
                                                                 cache=current.s3db.cache
                                                                 ).first().name
                    else:
                        _path = "%s/%s" % (parent, id)
                        L0_name = None
                elif Lx.level == "L0":
                    _path = "%s/%s" % (parent, id)
                    L0_name = Lx.name
                    L1_name = None
                else:
                    current.log.error("Parent of L2 Location ID %s has invalid level: %s is %s" % \
                                (id, parent, Lx.level))
                    #raise ValueError
                    return "%s/%s" % (parent, id)
                Lx_lat = Lx.lat
                Lx_lon = Lx.lon
            else:
                _path = id
                L0_name = None
                L1_name = None
                Lx_lat = None
                Lx_lon = None

            if inherited or lat is None or lon is None:
                fixup_required = True
                inherited = True
                lat = Lx_lat
                lon = Lx_lon
                wkt = None
            elif path != _path or L0 != L0_name or L1 != L1_name or L2 != name or not wkt:
                fixup_required = True

            if fixup_required:
                # Fix everything up
                if lat is False:
                    lat = None
                if lon is False:
                    lon = None
                fix_vars = {"inherited": inherited,
                            "path": _path,
                            "lat": lat,
                            "lon": lon,
                            "wkt": wkt or None,
                            "L0": L0_name,
                            "L1": L1_name,
                            "L2": name,
                            "L3": None,
                            "L4": None,
                            "L5": None,
                            }
                feature.update(**fix_vars)
                fixup(feature)

            if not all_locations:
                # Ensure that any locations which inherit their latlon from this one get updated
                propagate(id)

            return _path


        # L3
        L3 = feature_get("L3", False)
        if level == "L3":
            if inherited is None or name is False or parent is False or path is False or \
               lat is False or lon is False or wkt is False or \
               L0 is False or L1 is False or L2 is False or L3 is False:
                # Get the whole feature
                feature = db(table.id == id).select(table.id,
                                                    table.inherited,
                                                    table.name,
                                                    table.parent,
                                                    table.path,
                                                    table.lat,
                                                    table.lon,
                                                    table.wkt,
                                                    table.L0,
                                                    table.L1,
                                                    table.L2,
                                                    table.L3,
                                                    limitby = (0, 1)).first()
                inherited = feature.inherited
                name = feature.name
                parent = feature.parent
                path = feature.path
                lat = feature.lat
                lon = feature.lon
                wkt = feature.wkt
                L0 = feature.L0
                L1 = feature.L1
                L2 = feature.L2
                L3 = feature.L3

            if parent:
                Lx = db(table.id == parent).select(table.id,
                                                   table.name,
                                                   table.level,
                                                   table.parent,
                                                   table.path,
                                                   table.lat,
                                                   table.lon,
                                                   table.L0,
                                                   table.L1,
                                                   limitby = (0, 1)).first()
                if Lx.level == "L2":
                    L0_name = Lx.L0
                    L1_name = Lx.L1
                    L2_name = Lx.name
                    _path = Lx.path
                    # Don't try to fixup ancestors when we're coming from a propagate
                    if propagating or (_path and L0_name and L1_name):
                        _path = "%s/%s" % (_path, id)
                    else:
                        # This feature needs to be updated
                        _path = update_location_tree(Lx, all_locations)
                        _path = "%s/%s" % (_path, id)
                        # Query again
                        Lx = db(table.id == parent).select(table.L0,
                                                           table.L1,
                                                           table.lat,
                                                           table.lon,
                                                           limitby = (0, 1)
                                                           ).first()
                        L0_name = Lx.L0
                        L1_name = Lx.L1
                elif Lx.level == "L1":
                    L0_name = Lx.L0
                    L1_name = Lx.name
                    L2_name = None
                    _path = Lx.path
                    # Don't try to fixup ancestors when we're coming from a propagate
                    if propagating or (_path and L0_name):
                        _path = "%s/%s" % (_path, id)
                    else:
                        # This feature needs to be updated
                        _path = update_location_tree(Lx, all_locations)
                        _path = "%s/%s" % (_path, id)
                        # Query again
                        Lx = db(table.id == parent).select(table.L0,
                                                           table.lat,
                                                           table.lon,
                                                           limitby = (0, 1)
                                                           ).first()
                        L0_name = Lx.L0
                elif Lx.level == "L0":
                    _path = "%s/%s" % (parent, id)
                    L0_name = Lx.name
                    L1_name = None
                    L2_name = None
                else:
                    current.log.error("Parent of L3 Location ID %s has invalid level: %s is %s" % \
                                (id, parent, Lx.level))
                    #raise ValueError
                    return "%s/%s" % (parent, id)
                Lx_lat = Lx.lat
                Lx_lon = Lx.lon
            else:
                _path = id
                L0_name = None
                L1_name = None
                L2_name = None
                Lx_lat = None
                Lx_lon = None

            if inherited or lat is None or lon is None:
                fixup_required = True
                inherited = True
                lat = Lx_lat
                lon = Lx_lon
                wkt = None
            elif path != _path or L0 != L0_name or L1 != L1_name or L2 != L2_name or L3 != name or not wkt:
                fixup_required = True

            if fixup_required:
                # Fix everything up
                if lat is False:
                    lat = None
                if lon is False:
                    lon = None
                fix_vars = {"inherited": inherited,
                            "path": _path,
                            "lat": lat,
                            "lon": lon,
                            "wkt": wkt or None,
                            "L0": L0_name,
                            "L1": L1_name,
                            "L2": L2_name,
                            "L3": name,
                            "L4": None,
                            "L5": None,
                            }
                feature.update(**fix_vars)
                fixup(feature)

            if not all_locations:
                # Ensure that any locations which inherit their latlon from this one get updated
                propagate(id)

            return _path


        # L4
        L4 = feature_get("L4", False)
        if level == "L4":
            if inherited is None or name is False or parent is False or path is False or \
               lat is False or lon is False or wkt is False or \
               L0 is False or L1 is False or L2 is False or L3 is False or L4 is False:
                # Get the whole feature
                feature = db(table.id == id).select(table.id,
                                                    table.inherited,
                                                    table.name,
                                                    table.parent,
                                                    table.path,
                                                    table.lat,
                                                    table.lon,
                                                    table.wkt,
                                                    table.L0,
                                                    table.L1,
                                                    table.L2,
                                                    table.L3,
                                                    table.L4,
                                                    limitby = (0, 1)).first()
                inherited = feature.inherited
                name = feature.name
                parent = feature.parent
                path = feature.path
                lat = feature.lat
                lon = feature.lon
                wkt = feature.wkt
                L0 = feature.L0
                L1 = feature.L1
                L2 = feature.L2
                L3 = feature.L3
                L4 = feature.L4

            if parent:
                Lx = db(table.id == parent).select(table.id,
                                                   table.name,
                                                   table.level,
                                                   table.parent,
                                                   table.path,
                                                   table.lat,
                                                   table.lon,
                                                   table.L0,
                                                   table.L1,
                                                   table.L2,
                                                   limitby = (0, 1)).first()
                if Lx.level == "L3":
                    L0_name = Lx.L0
                    L1_name = Lx.L1
                    L2_name = Lx.L2
                    L3_name = Lx.name
                    _path = Lx.path
                    # Don't try to fixup ancestors when we're coming from a propagate
                    if propagating or (_path and L0_name and L1_name and L2_name):
                        _path = "%s/%s" % (_path, id)
                    else:
                        # This feature needs to be updated
                        _path = update_location_tree(Lx, all_locations)
                        _path = "%s/%s" % (_path, id)
                        # Query again
                        Lx = db(table.id == parent).select(table.L0,
                                                           table.L1,
                                                           table.L2,
                                                           table.lat,
                                                           table.lon,
                                                           limitby = (0, 1)
                                                           ).first()
                        L0_name = Lx.L0
                        L1_name = Lx.L1
                        L2_name = Lx.L2
                elif Lx.level == "L2":
                    L0_name = Lx.L0
                    L1_name = Lx.L1
                    L2_name = Lx.name
                    L3_name = None
                    _path = Lx.path
                    # Don't try to fixup ancestors when we're coming from a propagate
                    if propagating or (_path and L0_name and L1_name):
                        _path = "%s/%s" % (_path, id)
                    else:
                        # This feature needs to be updated
                        _path = update_location_tree(Lx, all_locations)
                        _path = "%s/%s" % (_path, id)
                        # Query again
                        Lx = db(table.id == parent).select(table.L0,
                                                           table.L1,
                                                           table.lat,
                                                           table.lon,
                                                           limitby = (0, 1)
                                                           ).first()
                        L0_name = Lx.L0
                        L1_name = Lx.L1
                elif Lx.level == "L1":
                    L0_name = Lx.L0
                    L1_name = Lx.name
                    L2_name = None
                    L3_name = None
                    _path = Lx.path
                    # Don't try to fixup ancestors when we're coming from a propagate
                    if propagating or (_path and L0_name):
                        _path = "%s/%s" % (_path, id)
                    else:
                        # This feature needs to be updated
                        _path = update_location_tree(Lx, all_locations)
                        _path = "%s/%s" % (_path, id)
                        # Query again
                        Lx = db(table.id == parent).select(table.L0,
                                                           table.lat,
                                                           table.lon,
                                                           limitby = (0, 1)
                                                           ).first()
                        L0_name = Lx.L0
                elif Lx.level == "L0":
                    _path = "%s/%s" % (parent, id)
                    L0_name = Lx.name
                    L1_name = None
                    L2_name = None
                    L3_name = None
                else:
                    current.log.error("Parent of L3 Location ID %s has invalid level: %s is %s" % \
                                (id, parent, Lx.level))
                    #raise ValueError
                    return "%s/%s" % (parent, id)
                Lx_lat = Lx.lat
                Lx_lon = Lx.lon
            else:
                _path = id
                L0_name = None
                L1_name = None
                L2_name = None
                L3_name = None
                Lx_lat = None
                Lx_lon = None

            if inherited or lat is None or lon is None:
                fixup_required = True
                inherited = True
                lat = Lx_lat
                lon = Lx_lon
                wkt = None
            elif path != _path or L0 != L0_name or L1 != L1_name or L2 != L2_name or L3 != L3_name or L4 != name or not wkt:
                fixup_required = True

            if fixup_required:
                # Fix everything up
                if lat is False:
                    lat = None
                if lon is False:
                    lon = None
                fix_vars = {"inherited": inherited,
                            "path": _path,
                            "lat": lat,
                            "lon": lon,
                            "wkt": wkt or None,
                            "L0": L0_name,
                            "L1": L1_name,
                            "L2": L2_name,
                            "L3": L3_name,
                            "L4": name,
                            "L5": None,
                            }
                feature.update(**fix_vars)
                fixup(feature)

            if not all_locations:
                # Ensure that any locations which inherit their latlon from this one get updated
                propagate(id)

            return _path


        # L5
        L5 = feature_get("L5", False)
        if level == "L5":
            if inherited is None or name is False or parent is False or path is False or \
               lat is False or lon is False or wkt is False or \
               L0 is False or L1 is False or L2 is False or L3 is False or L4 is False or L5 is False:
                # Get the whole feature
                feature = db(table.id == id).select(table.id,
                                                    table.inherited,
                                                    table.name,
                                                    table.parent,
                                                    table.path,
                                                    table.lat,
                                                    table.lon,
                                                    table.wkt,
                                                    table.L0,
                                                    table.L1,
                                                    table.L2,
                                                    table.L3,
                                                    table.L4,
                                                    table.L5,
                                                    limitby = (0, 1)).first()
                inherited = feature.inherited
                name = feature.name
                parent = feature.parent
                path = feature.path
                lat = feature.lat
                lon = feature.lon
                wkt = feature.wkt
                L0 = feature.L0
                L1 = feature.L1
                L2 = feature.L2
                L3 = feature.L3
                L4 = feature.L4
                L5 = feature.L5

            if parent:
                Lx = db(table.id == parent).select(table.id,
                                                   table.name,
                                                   table.level,
                                                   table.parent,
                                                   table.path,
                                                   table.lat,
                                                   table.lon,
                                                   table.L0,
                                                   table.L1,
                                                   table.L2,
                                                   table.L3,
                                                   limitby = (0, 1)).first()
                if Lx.level == "L4":
                    L0_name = Lx.L0
                    L1_name = Lx.L1
                    L2_name = Lx.L2
                    L3_name = Lx.L3
                    L4_name = Lx.name
                    _path = Lx.path
                    # Don't try to fixup ancestors when we're coming from a propagate
                    if propagating or (_path and L0_name and L1_name and L2_name and L3_name):
                        _path = "%s/%s" % (_path, id)
                    else:
                        # This feature needs to be updated
                        _path = update_location_tree(Lx, all_locations)
                        _path = "%s/%s" % (_path, id)
                        # Query again
                        Lx = db(table.id == parent).select(table.L0,
                                                           table.L1,
                                                           table.L2,
                                                           table.L3,
                                                           table.lat,
                                                           table.lon,
                                                           limitby = (0, 1)
                                                           ).first()
                        L0_name = Lx.L0
                        L1_name = Lx.L1
                        L2_name = Lx.L2
                        L3_name = Lx.L3
                elif Lx.level == "L3":
                    L0_name = Lx.L0
                    L1_name = Lx.L1
                    L2_name = Lx.L2
                    L3_name = Lx.name
                    L4_name = None
                    _path = Lx.path
                    # Don't try to fixup ancestors when we're coming from a propagate
                    if propagating or (_path and L0_name and L1_name and L2_name):
                        _path = "%s/%s" % (_path, id)
                    else:
                        # This feature needs to be updated
                        _path = update_location_tree(Lx, all_locations)
                        _path = "%s/%s" % (_path, id)
                        # Query again
                        Lx = db(table.id == parent).select(table.L0,
                                                           table.L1,
                                                           table.L2,
                                                           table.lat,
                                                           table.lon,
                                                           limitby = (0, 1)
                                                           ).first()
                        L0_name = Lx.L0
                        L1_name = Lx.L1
                        L2_name = Lx.L2
                elif Lx.level == "L2":
                    L0_name = Lx.L0
                    L1_name = Lx.L1
                    L2_name = Lx.name
                    L3_name = None
                    L4_name = None
                    _path = Lx.path
                    # Don't try to fixup ancestors when we're coming from a propagate
                    if propagating or (_path and L0_name and L1_name):
                        _path = "%s/%s" % (_path, id)
                    else:
                        # This feature needs to be updated
                        _path = update_location_tree(Lx, all_locations)
                        _path = "%s/%s" % (_path, id)
                        # Query again
                        Lx = db(table.id == parent).select(table.L0,
                                                           table.L1,
                                                           table.lat,
                                                           table.lon,
                                                           limitby = (0, 1)
                                                           ).first()
                        L0_name = Lx.L0
                        L1_name = Lx.L1
                elif Lx.level == "L1":
                    L0_name = Lx.L0
                    L1_name = Lx.name
                    L2_name = None
                    L3_name = None
                    L4_name = None
                    _path = Lx.path
                    # Don't try to fixup ancestors when we're coming from a propagate
                    if propagating or (_path and L0_name):
                        _path = "%s/%s" % (_path, id)
                    else:
                        # This feature needs to be updated
                        _path = update_location_tree(Lx, all_locations)
                        _path = "%s/%s" % (_path, id)
                        # Query again
                        Lx = db(table.id == parent).select(table.L0,
                                                           table.lat,
                                                           table.lon,
                                                           limitby = (0, 1)
                                                           ).first()
                        L0_name = Lx.L0
                elif Lx.level == "L0":
                    _path = "%s/%s" % (parent, id)
                    L0_name = Lx.name
                    L1_name = None
                    L2_name = None
                    L3_name = None
                    L4_name = None
                else:
                    current.log.error("Parent of L3 Location ID %s has invalid level: %s is %s" % \
                                (id, parent, Lx.level))
                    #raise ValueError
                    return "%s/%s" % (parent, id)
                Lx_lat = Lx.lat
                Lx_lon = Lx.lon
            else:
                _path = id
                L0_name = None
                L1_name = None
                L2_name = None
                L3_name = None
                L4_name = None
                Lx_lat = None
                Lx_lon = None

            if inherited or lat is None or lon is None:
                fixup_required = True
                inherited = True
                lat = Lx_lat
                lon = Lx_lon
                wkt = None
            elif path != _path or L0 != L0_name or L1 != L1_name or L2 != L2_name or L3 != L3_name or L4 != L4_name or L5 != name or not wkt:
                fixup_required = True

            if fixup_required:
                # Fix everything up
                if lat is False:
                    lat = None
                if lon is False:
                    lon = None
                fix_vars = {"inherited": inherited,
                            "path": _path,
                            "lat": lat,
                            "lon": lon,
                            "wkt": wkt or None,
                            "L0": L0_name,
                            "L1": L1_name,
                            "L2": L2_name,
                            "L3": L3_name,
                            "L4": L4_name,
                            "L5": name,
                            }
                feature.update(**fix_vars)
                fixup(feature)

            if not all_locations:
                # Ensure that any locations which inherit their latlon from this one get updated
                propagate(id)

            return _path


        # Specific Location
        # - or unspecified (which we should avoid happening as inefficient)
        if inherited is None or level is False or name is False or parent is False or path is False or \
           lat is False or lon is False or wkt is False or \
           L0 is False or L1 is False or L2 is False or L3 is False or L4 is False or L5 is False:
            # Get the whole feature
            feature = db(table.id == id).select(table.id,
                                                table.inherited,
                                                table.level,
                                                table.name,
                                                table.parent,
                                                table.path,
                                                table.lat,
                                                table.lon,
                                                table.wkt,
                                                table.L0,
                                                table.L1,
                                                table.L2,
                                                table.L3,
                                                table.L4,
                                                table.L5,
                                                limitby = (0, 1)
                                                ).first()
            inherited = feature.inherited
            level = feature.level
            name = feature.name
            parent = feature.parent
            path = feature.path
            lat = feature.lat
            lon = feature.lon
            wkt = feature.wkt
            L0 = feature.L0
            L1 = feature.L1
            L2 = feature.L2
            L3 = feature.L3
            L4 = feature.L4
            L5 = feature.L5

        L0_name = name if level == "L0" else None
        L1_name = name if level == "L1" else None
        L2_name = name if level == "L2" else None
        L3_name = name if level == "L3" else None
        L4_name = name if level == "L4" else None
        L5_name = name if level == "L5" else None

        if parent:
            Lx = db(table.id == parent).select(table.id,
                                               table.name,
                                               table.level,
                                               table.parent,
                                               table.path,
                                               table.lat,
                                               table.lon,
                                               table.L0,
                                               table.L1,
                                               table.L2,
                                               table.L3,
                                               table.L4,
                                               limitby = (0, 1)).first()
            if Lx.level == "L5":
                L0_name = Lx.L0
                L1_name = Lx.L1
                L2_name = Lx.L2
                L3_name = Lx.L3
                L4_name = Lx.L4
                L5_name = Lx.name
                _path = Lx.path
                # Don't try to fixup ancestors when we're coming from a propagate
                if propagating or (_path and L0_name and L1_name and L2_name and L3_name and L4_name):
                    _path = "%s/%s" % (_path, id)
                else:
                    # This feature needs to be updated
                    _path = update_location_tree(Lx, all_locations)
                    _path = "%s/%s" % (_path, id)
                    # Query again
                    Lx = db(table.id == parent).select(table.L0,
                                                       table.L1,
                                                       table.L2,
                                                       table.L3,
                                                       table.L4,
                                                       table.lat,
                                                       table.lon,
                                                       limitby = (0, 1)
                                                       ).first()
                    L0_name = Lx.L0
                    L1_name = Lx.L1
                    L2_name = Lx.L2
                    L3_name = Lx.L3
                    L4_name = Lx.L4
            elif Lx.level == "L4":
                L0_name = Lx.L0
                L1_name = Lx.L1
                L2_name = Lx.L2
                L3_name = Lx.L3
                L4_name = Lx.name
                _path = Lx.path
                # Don't try to fixup ancestors when we're coming from a propagate
                if propagating or (_path and L0_name and L1_name and L2_name and L3_name):
                    _path = "%s/%s" % (_path, id)
                else:
                    # This feature needs to be updated
                    _path = update_location_tree(Lx, all_locations)
                    _path = "%s/%s" % (_path, id)
                    # Query again
                    Lx = db(table.id == parent).select(table.L0,
                                                       table.L1,
                                                       table.L2,
                                                       table.L3,
                                                       table.lat,
                                                       table.lon,
                                                       limitby = (0, 1)
                                                       ).first()
                    L0_name = Lx.L0
                    L1_name = Lx.L1
                    L2_name = Lx.L2
                    L3_name = Lx.L3
            elif Lx.level == "L3":
                L0_name = Lx.L0
                L1_name = Lx.L1
                L2_name = Lx.L2
                L3_name = Lx.name
                _path = Lx.path
                # Don't try to fixup ancestors when we're coming from a propagate
                if propagating or (_path and L0_name and L1_name and L2_name):
                    _path = "%s/%s" % (_path, id)
                else:
                    # This feature needs to be updated
                    _path = update_location_tree(Lx, all_locations)
                    _path = "%s/%s" % (_path, id)
                    # Query again
                    Lx = db(table.id == parent).select(table.L0,
                                                       table.L1,
                                                       table.L2,
                                                       table.lat,
                                                       table.lon,
                                                       limitby = (0, 1)
                                                       ).first()
                    L0_name = Lx.L0
                    L1_name = Lx.L1
                    L2_name = Lx.L2
            elif Lx.level == "L2":
                L0_name = Lx.L0
                L1_name = Lx.L1
                L2_name = Lx.name
                _path = Lx.path
                # Don't try to fixup ancestors when we're coming from a propagate
                if propagating or (_path and L0_name and L1_name):
                    _path = "%s/%s" % (_path, id)
                else:
                    # This feature needs to be updated
                    _path = update_location_tree(Lx, all_locations)
                    _path = "%s/%s" % (_path, id)
                    # Query again
                    Lx = db(table.id == parent).select(table.L0,
                                                       table.L1,
                                                       table.lat,
                                                       table.lon,
                                                       limitby = (0, 1)
                                                       ).first()
                    L0_name = Lx.L0
                    L1_name = Lx.L1
            elif Lx.level == "L1":
                L0_name = Lx.L0
                L1_name = Lx.name
                _path = Lx.path
                # Don't try to fixup ancestors when we're coming from a propagate
                if propagating or (_path and L0_name):
                    _path = "%s/%s" % (_path, id)
                else:
                    # This feature needs to be updated
                    _path = update_location_tree(Lx, all_locations)
                    _path = "%s/%s" % (_path, id)
                    # Query again
                    Lx = db(table.id == parent).select(table.L0,
                                                       table.lat,
                                                       table.lon,
                                                       limitby = (0, 1)
                                                       ).first()
                    L0_name = Lx.L0
            elif Lx.level == "L0":
                _path = "%s/%s" % (parent, id)
                L0_name = Lx.name
            else:
                current.log.error("Parent of L3 Location ID %s has invalid level: %s is %s" % \
                            (id, parent, Lx.level))
                #raise ValueError
                return "%s/%s" % (parent, id)
            Lx_lat = Lx.lat
            Lx_lon = Lx.lon
        else:
            _path = id
            Lx_lat = None
            Lx_lon = None

        if inherited or lat is None or lon is None:
            fixup_required = True
            inherited = True
            lat = Lx_lat
            lon = Lx_lon
            wkt = None
        elif path != _path or L0 != L0_name or L1 != L1_name or L2 != L2_name or L3 != L3_name or L4 != L4_name or L5 != L5_name or not wkt:
            fixup_required = True

        if fixup_required:
            # Fix everything up
            if lat is False:
                lat = None
            if lon is False:
                lon = None
            fix_vars = {"inherited": inherited,
                        "path": _path,
                        "lat": lat,
                        "lon": lon,
                        "wkt": wkt or None,
                        "L0": L0_name,
                        "L1": L1_name,
                        "L2": L2_name,
                        "L3": L3_name,
                        "L4": L4_name,
                        "L5": L5_name,
                        }
            feature.update(**fix_vars)
            fixup(feature)

        if not all_locations:
            # Ensure that any locations which inherit their latlon from this one get updated
            propagate(id)

        return _path

    # -------------------------------------------------------------------------
    @staticmethod
    def wkt_centroid(form):
        """
            OnValidation callback:
            If a WKT is defined: validate the format,
                calculate the LonLat of the Centroid, and set bounds
            Else if a LonLat is defined: calculate the WKT for the Point.
        """

        form_vars = form.vars

        if form_vars.get("gis_feature_type", None) == "1":
            # Point
            lat = form_vars.get("lat", None)
            lon = form_vars.get("lon", None)
            if (lon is None and lat is None) or \
               (lon == "" and lat == ""):
                # No Geometry available
                # Don't clobber existing records (e.g. in Prepop)
                #form_vars.gis_feature_type = "0"
                # Cannot create WKT, so Skip
                return
            elif lat is None or lat == "":
                # Can't just have lon without lat
                form.errors["lat"] = current.messages.lat_empty
            elif lon is None or lon == "":
                form.errors["lon"] = current.messages.lon_empty
            else:
                form_vars.wkt = "POINT (%(lon)s %(lat)s)" % form_vars
                radius = form_vars.get("radius", None)
                if radius:
                    bbox = GIS.get_bounds_from_radius(lat, lon, radius)
                    form_vars.lat_min = bbox["lat_min"]
                    form_vars.lon_min = bbox["lon_min"]
                    form_vars.lat_max = bbox["lat_max"]
                    form_vars.lon_max = bbox["lon_max"]
                else:
                    if "lon_min" not in form_vars or form_vars.lon_min is None:
                        form_vars.lon_min = lon
                    if "lon_max" not in form_vars or form_vars.lon_max is None:
                        form_vars.lon_max = lon
                    if "lat_min" not in form_vars or form_vars.lat_min is None:
                        form_vars.lat_min = lat
                    if "lat_max" not in form_vars or form_vars.lat_max is None:
                        form_vars.lat_max = lat

        else:
            wkt = form_vars.get("wkt", None)
            if wkt:
                if wkt[0] == "{":
                    # This is a GeoJSON geometry
                    from shapely.geometry import shape as shape_loads
                    try:
                        js = json.load(wkt)
                        shape = shape_loads(js)
                    except:
                        form.errors["wkt"] = current.messages.invalid_wkt
                        return
                    else:
                        form_vars.wkt = shape.wkt
                else:
                    # Assume WKT
                    warning = None
                    from shapely.wkt import loads as wkt_loads
                    try:
                        shape = wkt_loads(wkt)
                    except:
                        # Perhaps this is really a LINESTRING (e.g. OSM import of an unclosed Way, some CAP areas)
                        linestring = "LINESTRING%s" % wkt[8:-1]
                        try:
                            shape = wkt_loads(linestring)
                        except:
                            form.errors["wkt"] = current.messages.invalid_wkt
                            return
                        else:
                            warning = s3_str(current.T("Source WKT has been converted from POLYGON to LINESTRING"))
                            current.log.warning(warning)
                            form_vars.wkt = linestring
                    else:
                        if shape.wkt != form_vars.wkt: # If this is too heavy a check for some deployments, add a deployment_setting to disable the check & just do it silently
                            # Use Shapely to clean up the defective WKT (e.g. trailing chars)
                            warning = s3_str(current.T("Source WKT has been cleaned by Shapely"))
                            form_vars.wkt = shape.wkt

                    if shape.has_z:
                        # Shapely export of WKT is 2D only
                        if warning:
                            warning = "%s, %s" % s3_str(current.T("Only 2D geometry stored as PostGIS cannot handle 3D geometries"))
                        else:
                            warning = s3_str(current.T("Only 2D geometry stored as PostGIS cannot handle 3D geometries"))

                    if warning:
                        current.session.warning = warning

                gis_feature_type = shape.geom_type
                if gis_feature_type == "Point":
                    form_vars.gis_feature_type = 1
                elif gis_feature_type == "LineString":
                    form_vars.gis_feature_type = 2
                elif gis_feature_type == "Polygon":
                    form_vars.gis_feature_type = 3
                elif gis_feature_type == "MultiPoint":
                    form_vars.gis_feature_type = 4
                elif gis_feature_type == "MultiLineString":
                    form_vars.gis_feature_type = 5
                elif gis_feature_type == "MultiPolygon":
                    form_vars.gis_feature_type = 6
                elif gis_feature_type == "GeometryCollection":
                    form_vars.gis_feature_type = 7
                try:
                    centroid_point = shape.centroid
                    form_vars.lon = centroid_point.x
                    form_vars.lat = centroid_point.y
                    bounds = shape.bounds
                    if gis_feature_type != "Point" or \
                       "lon_min" not in form_vars or form_vars.lon_min is None or \
                       form_vars.lon_min == form_vars.lon_max:
                        # Update bounds unless we have a 'Point' which has already got wider Bounds specified (such as a country)
                        form_vars.lon_min = bounds[0]
                        form_vars.lat_min = bounds[1]
                        form_vars.lon_max = bounds[2]
                        form_vars.lat_max = bounds[3]
                except:
                    form.errors.gis_feature_type = current.messages.centroid_error

            else:
                lat = form_vars.get("lat", None)
                lon = form_vars.get("lon", None)
                if (lon is None and lat is None) or \
                   (lon == "" and lat == ""):
                    # No Geometry available
                    # Don't clobber existing records (e.g. in Prepop)
                    #form_vars.gis_feature_type = "0"
                    # Cannot create WKT, so Skip
                    return
                else:
                    # Point
                    form_vars.gis_feature_type = "1"
                    if lat is None or lat == "":
                        form.errors["lat"] = current.messages.lat_empty
                    elif lon is None or lon == "":
                        form.errors["lon"] = current.messages.lon_empty
                    else:
                        form_vars.wkt = "POINT (%(lon)s %(lat)s)" % form_vars
                        if "lon_min" not in form_vars or form_vars.lon_min is None:
                            form_vars.lon_min = lon
                        if "lon_max" not in form_vars or form_vars.lon_max is None:
                            form_vars.lon_max = lon
                        if "lat_min" not in form_vars or form_vars.lat_min is None:
                            form_vars.lat_min = lat
                        if "lat_max" not in form_vars or form_vars.lat_max is None:
                            form_vars.lat_max = lat

        if current.deployment_settings.get_gis_spatialdb():
            # Also populate the spatial field
            form_vars.the_geom = form_vars.wkt

    # -------------------------------------------------------------------------
    @staticmethod
    def query_features_by_bbox(lon_min, lat_min, lon_max, lat_max):
        """
            Returns a query of all Locations inside the given bounding box
        """

        table = current.s3db.gis_location
        query = (table.lat_min <= lat_max) & \
                (table.lat_max >= lat_min) & \
                (table.lon_min <= lon_max) & \
                (table.lon_max >= lon_min)
        return query

    # -------------------------------------------------------------------------
    @staticmethod
    def get_features_by_bbox(lon_min, lat_min, lon_max, lat_max):
        """
            Returns Rows of Locations whose shape intersects the given bbox.
        """

        query = current.gis.query_features_by_bbox(lon_min,
                                                   lat_min,
                                                   lon_max,
                                                   lat_max)
        return current.db(query).select()

    # -------------------------------------------------------------------------
    @staticmethod
    def get_features_by_shape(shape):
        """
            Returns Rows of locations which intersect the given shape.

            Relies on Shapely for wkt parsing and intersection.
            @ToDo: provide an option to use PostGIS/Spatialite
        """

        from shapely.errors import ReadingError
        from shapely.wkt import loads as wkt_loads

        try:
            # Enable C-based speedups available from 1.2.10+
            from shapely import speedups
            speedups.enable()
        except:
            current.log.info("S3GIS",
                             "Upgrade Shapely for Performance enhancements")

        table = current.s3db.gis_location
        in_bbox = current.gis.query_features_by_bbox(*shape.bounds)
        has_wkt = (table.wkt != None) & (table.wkt != "")

        for loc in current.db(in_bbox & has_wkt).select():
            try:
                location_shape = wkt_loads(loc.wkt)
                if location_shape.intersects(shape):
                    yield loc
            except ReadingError:
                current.log.error("Error reading wkt of location with id", loc.id)

    # -------------------------------------------------------------------------
    @staticmethod
    def get_features_by_latlon(lat, lon):
        """
            Returns a generator of locations whose shape intersects the given LatLon.

            Relies on Shapely.
            @todo: provide an option to use PostGIS/Spatialite
        """

        from shapely.geometry import point

        return current.gis.get_features_by_shape(point.Point(lon, lat))

    # -------------------------------------------------------------------------
    @staticmethod
    def get_features_by_feature(feature):
        """
            Returns all Locations whose geometry intersects the given feature.

            Relies on Shapely.
            @ToDo: provide an option to use PostGIS/Spatialite
        """

        from shapely.wkt import loads as wkt_loads

        shape = wkt_loads(feature.wkt)
        return current.gis.get_features_by_shape(shape)

    # -------------------------------------------------------------------------
    @staticmethod
    def set_all_bounds():
        """
            Sets bounds for all locations without them.

            If shapely is present, and a location has wkt, bounds of the geometry
            are used.  Otherwise, the (lat, lon) are used as bounds.
        """

        try:
            from shapely.wkt import loads as wkt_loads
            SHAPELY = True
        except:
            SHAPELY = False

        db = current.db
        table = current.s3db.gis_location

        # Query to find all locations without bounds set
        no_bounds = (table.lon_min == None) & \
                    (table.lat_min == None) & \
                    (table.lon_max == None) & \
                    (table.lat_max == None) & \
                    (table.lat != None) & \
                    (table.lon != None)
        if SHAPELY:
            # Refine to those locations with a WKT field
            wkt_no_bounds = no_bounds & (table.wkt != None) & (table.wkt != "")
            for location in db(wkt_no_bounds).select(table.wkt):
                try :
                    shape = wkt_loads(location.wkt)
                except:
                    current.log.error("Error reading WKT", location.wkt)
                    continue
                bounds = shape.bounds
                table[location.id] = {"lon_min": bounds[0],
                                      "lat_min": bounds[1],
                                      "lon_max": bounds[2],
                                      "lat_max": bounds[3],
                                      }

        # Anything left, we assume is a Point, so set the bounds to be the same
        db(no_bounds).update(lon_min=table.lon,
                             lat_min=table.lat,
                             lon_max=table.lon,
                             lat_max=table.lat)

    # -------------------------------------------------------------------------
    @staticmethod
    def simplify(wkt,
                 tolerance=None,
                 preserve_topology=True,
                 output="wkt",
                 precision=None
                 ):
        """
            Simplify a complex Polygon using the Douglas-Peucker algorithm
            - NB This uses Python, better performance will be gained by doing
                 this direct from the database if you are using PostGIS:
            ST_Simplify() is available as
            db(query).select(table.the_geom.st_simplify(tolerance).st_astext().with_alias('wkt')).first().wkt
            db(query).select(table.the_geom.st_simplify(tolerance).st_asgeojson().with_alias('geojson')).first().geojson

            Args:
                wkt: the WKT string to be simplified (usually coming from a gis_location record)
                tolerance: how aggressive a simplification to perform
                preserve_topology: whether the simplified geometry should be maintained
                output: whether to output as WKT or GeoJSON format
                precision: the number of decimal places to include in the output
        """

        from shapely.geometry import Point, LineString, Polygon, MultiPolygon
        from shapely.wkt import loads as wkt_loads

        try:
            # Enable C-based speedups available from 1.2.10+
            from shapely import speedups
            speedups.enable()
        except:
            current.log.info("S3GIS",
                             "Upgrade Shapely for Performance enhancements")

        try:
            shape = wkt_loads(wkt)
        except:
            wkt = wkt[10] if wkt else wkt
            current.log.error("Invalid Shape: %s" % wkt)
            return None

        settings = current.deployment_settings

        if not precision:
            precision = settings.get_gis_precision()

        if tolerance is None:
            tolerance = settings.get_gis_simplify_tolerance()

        if tolerance:
            shape = shape.simplify(tolerance, preserve_topology)

        # Limit the number of decimal places
        formatter = ".%sf" % precision
        def shrink_polygon(shape):
            """ Helper Function """
            points = shape.exterior.coords
            coords = []
            cappend = coords.append
            for point in points:
                x = float(format(point[0], formatter))
                y = float(format(point[1], formatter))
                cappend((x, y))
            return Polygon(LineString(coords))

        geom_type = shape.geom_type
        if geom_type == "MultiPolygon":
            polygons = shape.geoms
            p = []
            pappend = p.append
            for polygon in polygons:
                pappend(shrink_polygon(polygon))
            shape = MultiPolygon([s for s in p])
        elif geom_type == "Polygon":
            shape = shrink_polygon(shape)
        elif geom_type == "LineString":
            points = shape.coords
            coords = []
            cappend = coords.append
            for point in points:
                x = float(format(point[0], formatter))
                y = float(format(point[1], formatter))
                cappend((x, y))
            shape = LineString(coords)
        elif geom_type == "Point":
            x = float(format(shape.x, formatter))
            y = float(format(shape.y, formatter))
            shape = Point(x, y)
        else:
            current.log.info("Cannot yet shrink Geometry: %s" % geom_type)

        # Output
        if output == "wkt":
            output = shape.to_wkt()
        elif output == "geojson":
            from ...geojson import dumps
            # Compact Encoding
            output = dumps(shape, separators=JSONSEPARATORS)

        return output

    # -------------------------------------------------------------------------
    @staticmethod
    def show_map(id = "default_map",
                 height = None,
                 width = None,
                 bbox = DEFAULT,
                 lat = None,
                 lon = None,
                 zoom = None,
                 projection = None,
                 add_feature = False,
                 add_feature_active = False,
                 add_line = False,
                 add_line_active = False,
                 add_polygon = False,
                 add_polygon_active = False,
                 add_circle = False,
                 add_circle_active = False,
                 features = None,
                 feature_queries = None,
                 feature_resources = None,
                 wms_browser = DEFAULT,
                 catalogue_layers = False,
                 legend = False,
                 toolbar = False,
                 area = False,
                 clear_layers = None,
                 nav = None,
                 print_control = None,
                 print_mode = False,
                 save = False,
                 search = False,
                 mouse_position = None,
                 overview = None,
                 permalink = None,
                 scaleline = None,
                 zoomcontrol = None,
                 zoomWheelEnabled = True,
                 mgrs = DEFAULT,
                 window = False,
                 window_hide = False,
                 closable = True,
                 maximizable = True,
                 collapsed = False,
                 callback = "DEFAULT",
                 plugins = None,
                 ):
        """
            Returns the HTML to display a map

            Normally called in the controller as: map = gis.show_map()
            In the view, put: {{=XML(map)}}

            Args:
                id: ID to uniquely identify this map if there are several
                    on a page
                height: Height of viewport (if not provided then the default
                        deployment setting is used)
                width: Width of viewport (if not provided then the default
                       deployment setting is used)
                bbox: default Bounding Box of viewport (if not provided then
                       the Lat/Lon/Zoom are used), a dict:
                            {"lon_min" : float,
                             "lat_min" : float,
                             "lon_max" : float,
                             "lat_max" : float,
                             }
                lat: default Latitude of viewport (if not provided then the
                     default setting from the Map Service Catalogue is used)
                lon: default Longitude of viewport (if not provided then the
                     default setting from the Map Service Catalogue is used)
                zoom: default Zoom level of viewport (if not provided then
                      the default setting from the Map Service Catalogue is used)
                projection: EPSG code for the Projection to use (if not provided
                            then the default setting from the Map Service Catalogue
                            is used)
                add_feature: Whether to include a DrawFeature control to allow
                             adding a marker to the map
                add_feature_active: Whether the DrawFeature control should be
                                    active by default
                add_polygon: Whether to include a DrawFeature control to allow
                             drawing a polygon over the map
                add_polygon_active: Whether the DrawFeature control should be
                                    active by default
                add_circle: Whether to include a DrawFeature control to allow
                            drawing a circle over the map
                add_circle_active: Whether the DrawFeature control should be
                                   active by default
                features: Simple Features to overlay on Map (no control over
                          appearance & not interactive) [wkt]
                feature_queries: Feature Queries to overlay onto the map and
                                 their options (List of Dicts):
                        [{"name"   : T("MyLabel"), # A string: the label for the layer
                          "query"  : query,        # A gluon.sql.Rows of gis_locations, which can be from
                                                   # a simple query or a Join.
                                                   # Extra fields can be added for 'popup_url', 'popup_label' & either
                                                   # 'marker' (url/height/width) or 'shape' (with optional 'colour' & 'size')
                          "active" : True,         # Is the feed displayed upon load or needs ticking to load afterwards?
                          "marker" : None,         # Optional: A per-Layer marker query or marker_id for the icon used to display the feature
                          "opacity" : 1,           # Optional
                          "cluster_attribute",     # Optional
                          "cluster_distance",      # Optional
                          "cluster_threshold"      # Optional
                          }]
                feature_resources: REST URLs for (filtered) resources to overlay
                                   onto the map & their options (List of Dicts):
                        [{"name"      : T("MyLabel"), # A string: the label for the layer
                          "id"        : "search",     # A string: the id for the layer (for manipulation by JavaScript)
                          "active"    : True,         # Is the feed displayed upon load or needs ticking to load afterwards?

                        EITHER:
                          "layer_id"  : 1,            # An integer: the layer_id to load (optional alternative to
                                                      # specifying URL/tablename/marker)
                          "filter"    : "filter",     # A string: an optional URL filter which *replaces* any in the layer
                        OR:
                          "tablename" : "module_resource", # A string: the tablename (used to determine whether to locate via location_id or site_id)
                          "url"       : "/eden/module/resource.geojson?filter", # A URL to load the resource

                          "marker"    : None,         # Optional: A per-Layer marker dict for the icon used to display the feature (overrides layer_id if-set)
                          "opacity"   : 1,            # Optional (overrides layer_id if-set)
                          "cluster_attribute",        # Optional (overrides layer_id if-set)
                          "cluster_distance",         # Optional (overrides layer_id if-set)
                          "cluster_threshold",        # Optional (overrides layer_id if-set)
                          "dir",                      # Optional (overrides layer_id if-set)
                          "style",                    # Optional (overrides layer_id if-set)
                          }]
                wms_browser: WMS Server's GetCapabilities & options (dict)
                             {"name": T("MyLabel"),     # Name for the Folder in LayerTree
                              "url": string             # URL of GetCapabilities
                              }
                catalogue_layers: Show all the enabled Layers from the
                                  GIS Catalogue, defaults to False: Just
                                  show the default Base layer
                legend: True: Show the GeoExt Legend panel,
                        False: No Panel, "float": New floating Legend Panel
                toolbar: Show the Icon Toolbar of Controls
                area: Show the Area tool on the Toolbar
                nav: Show the Navigation controls on the Toolbar
                save: Show the Save tool on the Toolbar
                search: Show the Geonames search box (requires a username to be
                        configured)
                mouse_position: Show the current coordinates in the bottom-right
                                of the map. 3 Options: 'normal', 'mgrs', False
                                (defaults to checking deployment_settings, which
                                defaults to 'normal')
                overview: Show the Overview Map (defaults to checking
                          deployment_settings, which defaults to True)
                permalink: Show the Permalink control (defaults to checking
                           deployment_settings, which defaults to True)
                scaleline: Show the ScaleLine control (defaults to checking
                           deployment_settings, which defaults to True)
                zoomcontrol: Show the Zoom control (defaults to checking
                             deployment_settings, which defaults to True)
                mgrs: Use the MGRS Control to select PDFs
                        {"name": string,   # Name for the Control
                         "url": string     # URL of PDF server
                         }
                      TODO Also add MGRS Search support: http://gxp.opengeo.org/master/examples/mgrs.html
                window: Have viewport pop out of page into a resizable window
                window_hide: Have the window hidden by default, ready to
                             appear (e.g. on clicking a button)
                closable: In Window mode, whether the window is closable or not
                collapsed: Start the Tools panel (West region) collapsed
                callback: Code to run once the Map JavaScript has loaded
                plugins: an iterable of objects which support the following
                         methods:
                            .extend_gis_map(map)
                         Client-side portion supports the following methods:
                            .addToMapWindow(items)
                            .setup(map)
        """

        if bbox is DEFAULT:
            bbox = {}
        if wms_browser is DEFAULT:
            wms_browser = {}
        if mgrs is DEFAULT:
            mgrs = {}

        from .widgets import MAP
        return MAP(id = id,
                   height = height,
                   width = width,
                   bbox = bbox,
                   lat = lat,
                   lon = lon,
                   zoom = zoom,
                   projection = projection,
                   add_feature = add_feature,
                   add_feature_active = add_feature_active,
                   add_line = add_line,
                   add_line_active = add_line_active,
                   add_polygon = add_polygon,
                   add_polygon_active = add_polygon_active,
                   add_circle = add_circle,
                   add_circle_active = add_circle_active,
                   features = features,
                   feature_queries = feature_queries,
                   feature_resources = feature_resources,
                   wms_browser = wms_browser,
                   catalogue_layers = catalogue_layers,
                   legend = legend,
                   toolbar = toolbar,
                   area = area,
                   clear_layers = clear_layers,
                   nav = nav,
                   print_control = print_control,
                   print_mode = print_mode,
                   save = save,
                   search = search,
                   mouse_position = mouse_position,
                   overview = overview,
                   permalink = permalink,
                   scaleline = scaleline,
                   zoomcontrol = zoomcontrol,
                   zoomWheelEnabled = zoomWheelEnabled,
                   mgrs = mgrs,
                   window = window,
                   window_hide = window_hide,
                   closable = closable,
                   maximizable = maximizable,
                   collapsed = collapsed,
                   callback = callback,
                   plugins = plugins,
                   )

# END =========================================================================
