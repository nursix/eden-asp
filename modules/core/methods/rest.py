"""
    Default REST API

    Copyright: 2009-2022 (c) Sahana Software Foundation

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

__all__ = ("RESTful",)

import json
import sys

from urllib.request import urlopen

from gluon import current
from gluon.storage import Storage

from ..tools import s3_parse_datetime

from .base import CRUDMethod

# =============================================================================
class RESTful(CRUDMethod):
    """ REST API """

    # -------------------------------------------------------------------------
    def apply_method(self, r, **attr):
        """
            Apply methods

            Args:
                r: the CRUDRequest
                attr: controller parameters
        """

        # With restricted REST API, generic XML/S3JSON exports are only allowed for ADMINs
        if r.representation in ("xml", "s3json") and \
           current.deployment_settings.get_security_restapi_restricted() and \
           not current.auth.s3_has_role("ADMIN"):
            r.unauthorised()

        output = {}

        http, method = r.http, r.method
        if not method:
            if http == "GET":
                output = self.get_tree(r, **attr)
            elif r.http in ("PUT", "POST"):
                output = self.put_tree(r, **attr)
            # TODO support DELETE
            #elif r.http == "DELETE"
            #    output = self.delete(r, **attr)
            else:
                r.error(405, current.ERROR.BAD_METHOD)

        elif method == "fields":
            if http == "GET":
                output = self.get_fields(r, **attr)
            else:
                r.error(405, current.ERROR.BAD_METHOD)

        elif method == "options":
            if http == "GET":
                output = self.get_options(r, **attr)
            else:
                r.error(405, current.ERROR.BAD_METHOD)

        else:
            r.error(404, current.ERROR.BAD_ENDPOINT)

        return output

    # -------------------------------------------------------------------------
    # Built-in method handlers
    # -------------------------------------------------------------------------
    @staticmethod
    def get_tree(r, **attr):
        """
            XML Element tree export method

            Args:
                r: the CRUDRequest instance
                attr: controller attributes
        """

        get_vars = r.get_vars
        args = Storage()

        # Slicing
        start = get_vars.get("start")
        if start is not None:
            try:
                start = int(start)
            except ValueError:
                start = None
        limit = get_vars.get("limit")
        if limit is not None:
            try:
                limit = int(limit)
            except ValueError:
                limit = None

        # msince
        msince = get_vars.get("msince")
        if msince is not None:
            msince = s3_parse_datetime(msince)

        # Show IDs (default: False)
        if "show_ids" in get_vars:
            if get_vars["show_ids"].lower() == "true":
                current.xml.show_ids = True

        # Show URLs (default: True)
        if "show_urls" in get_vars:
            if get_vars["show_urls"].lower() == "false":
                current.xml.show_urls = False

        # Mobile data export (default: False)
        mdata = get_vars.get("mdata") == "1"

        # Maxbounds (default: False)
        maxbounds = False
        if "maxbounds" in get_vars:
            if get_vars["maxbounds"].lower() == "true":
                maxbounds = True
        if r.representation in ("gpx", "osm"):
            maxbounds = True

        # Components of the master resource (tablenames)
        if "mcomponents" in get_vars:
            mcomponents = get_vars["mcomponents"]
            if str(mcomponents).lower() == "none":
                mcomponents = None
            elif not isinstance(mcomponents, list):
                mcomponents = mcomponents.split(",")
        else:
            mcomponents = [] # all

        # Components of referenced resources (tablenames)
        if "rcomponents" in get_vars:
            rcomponents = get_vars["rcomponents"]
            if str(rcomponents).lower() == "none":
                rcomponents = None
            elif not isinstance(rcomponents, list):
                rcomponents = rcomponents.split(",")
        else:
            rcomponents = None

        # Maximum reference resolution depth
        if "maxdepth" in get_vars:
            try:
                args["maxdepth"] = int(get_vars["maxdepth"])
            except ValueError:
                pass

        # References to resolve (field names)
        if "references" in get_vars:
            references = get_vars["references"]
            if str(references).lower() == "none":
                references = []
            elif not isinstance(references, list):
                references = references.split(",")
        else:
            references = None # all

        # Export field selection
        if "fields" in get_vars:
            fields = get_vars["fields"]
            if str(fields).lower() == "none":
                fields = []
            elif not isinstance(fields, list):
                fields = fields.split(",")
        else:
            fields = None # all

        # Find XSLT stylesheet
        stylesheet = r.stylesheet()

        # Add stylesheet parameters
        if stylesheet is not None:
            if r.component:
                args["id"] = r.id
                args["component"] = r.component.tablename
                if r.component.alias:
                    args["alias"] = r.component.alias
            mode = get_vars.get("xsltmode")
            if mode is not None:
                args["mode"] = mode

        # Set response headers
        response = current.response
        s3 = response.s3
        headers = response.headers
        representation = r.representation
        if representation in s3.json_formats:
            as_json = True
            default = "application/json"
        else:
            as_json = False
            default = "text/xml"
        headers["Content-Type"] = s3.content_type.get(representation,
                                                      default)

        # Export the resource
        resource = r.resource
        target = r.target()[3]
        if target == resource.tablename:
            # Master resource targetted
            target = None
        output = resource.export_xml(start = start,
                                     limit = limit,
                                     msince = msince,
                                     fields = fields,
                                     dereference = True,
                                     # maxdepth in args
                                     references = references,
                                     mdata = mdata,
                                     mcomponents = mcomponents,
                                     rcomponents = rcomponents,
                                     stylesheet = stylesheet,
                                     as_json = as_json,
                                     maxbounds = maxbounds,
                                     target = target,
                                     **args)
        # Transformation error?
        if not output:
            r.error(400, "XSLT Transformation Error: %s " % current.xml.error)

        return output

    # -------------------------------------------------------------------------
    @staticmethod
    def put_tree(r, **attr):
        """
            XML Element tree import method

            Args:
                r: the CRUDRequest method
                attr: controller attributes
        """

        get_vars = r.get_vars

        # Skip invalid records?
        ignore_errors = "ignore_errors" in get_vars

        # Find all source names in the URL vars
        def findnames(get_vars, name):
            nlist = []
            if name in get_vars:
                names = get_vars[name]
                if isinstance(names, (list, tuple)):
                    names = ",".join(names)
                names = names.split(",")
                for n in names:
                    if n[0] == "(" and ")" in n[1:]:
                        nlist.append(n[1:].split(")", 1))
                    else:
                        nlist.append([None, n])
            return nlist
        filenames = findnames(get_vars, "filename")
        fetchurls = findnames(get_vars, "fetchurl")
        source_url = None

        # Get the source(s)
        s3 = current.response.s3
        json_formats = s3.json_formats
        csv_formats = s3.csv_formats
        source = []
        representation = r.representation
        if representation in json_formats or representation in csv_formats:
            if filenames:
                try:
                    for f in filenames:
                        source.append((f[0], open(f[1], "rb")))
                except:
                    source = []
            elif fetchurls:
                try:
                    for u in fetchurls:
                        source.append((u[0], urlopen(u[1])))
                except:
                    source = []
            elif r.http != "GET":
                source = r.read_body()
        else:
            if filenames:
                source = filenames
            elif fetchurls:
                source = fetchurls
                # Assume only 1 URL for GeoRSS feed caching
                source_url = fetchurls[0][1]
            elif r.http != "GET":
                source = r.read_body()
        if not source:
            if filenames or fetchurls:
                # Error: source not found
                r.error(400, current.ERROR.BAD_SOURCE)
            else:
                # No source specified => return resource structure
                return r.get_struct(r, **attr)

        # Find XSLT stylesheet
        stylesheet = r.stylesheet(method="import")
        # Target IDs
        if r.method == "create":
            record_id = None
        else:
            record_id = r.id

        # Transformation mode?
        if "xsltmode" in get_vars:
            args = {"xsltmode": get_vars["xsltmode"]}
        else:
            args = {}

        # These 3 options are called by gis.show_map() & read by the
        # GeoRSS Import stylesheet to populate the gis_cache table
        # Source URL: For GeoRSS/KML Feed caching
        if source_url:
            args["source_url"] = source_url
        # Data Field: For GeoRSS/KML Feed popups
        if "data_field" in get_vars:
            args["data_field"] = get_vars["data_field"]
        # Image Field: For GeoRSS/KML Feed popups
        if "image_field" in get_vars:
            args["image_field"] = get_vars["image_field"]

        # Format type?
        if representation in json_formats:
            representation = "json"
        elif representation in csv_formats:
            representation = "csv"
        else:
            representation = "xml"

        try:
            result = r.resource.import_xml(source,
                                           record_id = record_id,
                                           source_type = representation,
                                           files = r.files,
                                           stylesheet = stylesheet,
                                           ignore_errors = ignore_errors,
                                           **args)
        except IOError:
            current.auth.permission.fail()
        except SyntaxError:
            e = sys.exc_info()[1]
            if hasattr(e, "message"):
                e = e.message
            r.error(400, e)

        if representation == "json":
            current.response.headers["Content-Type"] = "application/json"
        return result.json_message()

    # -------------------------------------------------------------------------
    @staticmethod
    def get_struct(r, **attr):
        """
            Resource structure introspection method

            Args:
                r: the CRUDRequest instance
                attr: controller attributes
        """

        response = current.response

        json_formats = response.s3.json_formats
        if r.representation in json_formats:
            as_json = True
            content_type = "application/json"
        else:
            as_json = False
            content_type = "text/xml"

        get_vars = r.get_vars
        meta = str(get_vars.get("meta", False)).lower() == "true"
        opts = str(get_vars.get("options", False)).lower() == "true"
        refs = str(get_vars.get("references", False)).lower() == "true"

        stylesheet = r.stylesheet()
        output = r.resource.export_struct(meta = meta,
                                          options = opts,
                                          references = refs,
                                          stylesheet = stylesheet,
                                          as_json = as_json,
                                          )
        if output is None:
            # Transformation error
            r.error(400, current.xml.error)

        response.headers["Content-Type"] = content_type

        return output

    # -------------------------------------------------------------------------
    @staticmethod
    def get_fields(r, **attr):
        """
            Resource structure introspection method (single table)

            Args:
                r: the CRUDRequest instance
                attr: controller attributes
        """

        output = content_type = None

        representation = r.representation
        if representation == "xml":
            output = r.resource.export_fields(component=r.component_name)
            content_type = "text/xml"
        elif representation == "s3json":
            output = r.resource.export_fields(component=r.component_name,
                                              as_json=True)
            content_type = "application/json"
        else:
            r.error(415, current.ERROR.BAD_FORMAT)

        response = current.response
        response.headers["Content-Type"] = content_type

        return output

    # -------------------------------------------------------------------------
    @staticmethod
    def get_options(r, **attr):
        """
            Export field options for the table

            Args:
                r: the CRUDRequest instance
                attr: controller attributes
        """

        get_vars = r.get_vars

        items = get_vars.get("field")
        if items:
            if not isinstance(items, (list, tuple)):
                items = [items]
            fields = []
            add_fields = fields.extend
            for item in items:
                f = item.split(",")
                if f:
                    add_fields(f)
        else:
            fields = None

        if "hierarchy" in get_vars:
            hierarchy = get_vars["hierarchy"].lower() not in ("false", "0")
        else:
            hierarchy = False

        representation = r.representation

        if representation != "xml" and "only_last" in get_vars:
            only_last = get_vars["only_last"].lower() not in ("false", "0")
        else:
            only_last = False

        if representation == "xml" and "show_uids" in get_vars:
            show_uids = get_vars["show_uids"].lower() not in ("false", "0")
        else:
            show_uids = False

        content_type, as_json = "application/json", True
        flat = False

        if representation == "xml":
            content_type, as_json = "text/xml", False
        elif representation == "s3json":
            pass
        elif representation == "json" and fields and len(fields) == 1:
            # JSON option supported for flat data structures only
            # e.g. for use by jquery.jeditable
            flat = True
        else:
            r.error(415, current.ERROR.BAD_FORMAT)

        output = r.resource.export_options(component = r.component_name,
                                           fields = fields,
                                           show_uids = show_uids,
                                           only_last = only_last,
                                           hierarchy = hierarchy,
                                           as_json = as_json,
                                           )

        if flat:
            s3json = json.loads(output)
            output = {}
            options = s3json.get("option")
            if options:
                for item in options:
                    output[item.get("@value")] = item.get("$", "")
            output = json.dumps(output)

        current.response.headers["Content-Type"] = content_type

        return output

# END =========================================================================
