"""
    Common JS/CSS includes

    Copyright: (c) 2010-2022 Sahana Software Foundation

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

import os

from gluon import current, HTTP, URL, XML

# =============================================================================
def include_debug_css():
    """
        Generates html to include the css listed in
            /modules/templates/<theme>/css.cfg
    """

    request = current.request

    location = current.response.s3.theme_config
    filename = "%s/modules/templates/%s/css.cfg" % (request.folder, location)
    if not os.path.isfile(filename):
        raise HTTP(500, "Theme configuration file missing: modules/templates/%s/css.cfg" % location)

    link_template = '<link href="/%s/static/styles/%%s" rel="stylesheet" type="text/css" />' % \
                    request.application
    links = ""

    with open(filename, "r") as css_cfg:
        links = "\n".join(link_template % cssname.rstrip()
                          for cssname in css_cfg if cssname[0] != "#")

    return XML(links)

# -----------------------------------------------------------------------------
def include_debug_js():
    """
        Generates html to include the js scripts listed in
            /static/scripts/tools/sahana.js.cfg
    """

    request = current.request

    scripts_dir = os.path.join(request.folder, "static", "scripts")

    import mergejsmf

    config_dict = {
        ".": scripts_dir,
        "ui": scripts_dir,
        "web2py": scripts_dir,
        "S3":     scripts_dir
    }
    config_filename = "%s/tools/sahana.js.cfg"  % scripts_dir
    files = mergejsmf.getFiles(config_dict, config_filename)[1]

    script_template = '<script src="/%s/static/scripts/%%s"></script>' % \
                      request.application

    scripts = "\n".join(script_template % scriptname for scriptname in files)
    return XML(scripts)

# -----------------------------------------------------------------------------
def include_datatable_js():
    """
        Add dataTable JS into the page; uses response.s3.datatable_opts
        for optional scripts (responsive, variable columns etc.)
    """

    s3 = current.response.s3

    scripts = s3.scripts
    options = s3.datatable_opts

    appname = current.request.application
    append = lambda s: scripts.append("/%s/static/scripts/%s" % (appname, s))

    if s3.debug:
        append("jquery.dataTables.js")
        if options:
            if options.get("responsive"):
                append("jquery.dataTables.responsive.js")
            if options.get("variable_columns"):
                append("S3/s3.ui.columns.js")
        append("S3/s3.ui.datatable.js")
    else:
        append("jquery.dataTables.min.js")
        if options:
            if options.get("responsive"):
                append("jquery.dataTables.responsive.min.js")
            if options.get("variable_columns"):
                append("S3/s3.ui.columns.min.js")
        append("S3/s3.ui.datatable.min.js")

# -----------------------------------------------------------------------------
def include_ext_js():
    """
        Add ExtJS CSS & JS into a page for a Map
        - since this is normally run from MAP.xml() it is too late to insert into
          s3.[external_]stylesheets, so must inject sheets into correct order
    """

    s3 = current.response.s3
    if s3.ext_included:
        # Ext already included
        return
    request = current.request
    appname = request.application

    xtheme = current.deployment_settings.get_base_xtheme()
    if xtheme:
        xtheme = "%smin.css" % xtheme[:-3]
        xtheme = "<link href='/%s/static/themes/%s' rel='stylesheet' type='text/css' />" % (appname, xtheme)

    if s3.cdn:
        # For Sites Hosted on the Public Internet, using a CDN may provide better performance
        PATH = "//cdn.sencha.com/ext/gpl/3.4.1.1"
    else:
        PATH = "/%s/static/scripts/ext" % appname

    if s3.debug:
        # Provide debug versions of CSS / JS
        adapter = "%s/adapter/jquery/ext-jquery-adapter-debug.js" % PATH
        main_js = "%s/ext-all-debug.js" % PATH
        main_css = "<link href='%s/resources/css/ext-all-notheme.css' rel='stylesheet' type='text/css' />" % PATH
        if not xtheme:
            xtheme = "<link href='%s/resources/css/xtheme-gray.css' rel='stylesheet' type='text/css' />" % PATH
    else:
        adapter = "%s/adapter/jquery/ext-jquery-adapter.js" % PATH
        main_js = "%s/ext-all.js" % PATH
        if xtheme:
            main_css = "<link href='/%s/static/scripts/ext/resources/css/ext-notheme.min.css' rel='stylesheet' type='text/css' />" % appname
        else:
            main_css = "<link href='/%s/static/scripts/ext/resources/css/ext-gray.min.css' rel='stylesheet' type='text/css' />" % appname

    scripts = s3.scripts
    scripts_append = scripts.append
    scripts_append(adapter)
    scripts_append(main_js)

    langfile = "ext-lang-%s.js" % s3.language
    if os.path.exists(os.path.join(request.folder, "static", "scripts", "ext", "src", "locale", langfile)):
        locale = "%s/src/locale/%s" % (PATH, langfile)
        scripts_append(locale)

    if xtheme:
        s3.jquery_ready.append('''$('#ext-styles').after("%s").after("%s").remove()''' % (xtheme, main_css))
    else:
        s3.jquery_ready.append('''$('#ext-styles').after("%s").remove()''' % main_css)

    s3.ext_included = True

# -----------------------------------------------------------------------------
def include_underscore_js():
    """
        Add Undercore JS into a page
        - for Map templates
        - for templates in GroupedOptsWidget comment
    """

    s3 = current.response.s3
    debug = s3.debug
    scripts = s3.scripts
    if s3.cdn:
        if debug:
            script = \
"//cdnjs.cloudflare.com/ajax/libs/underscore.js/1.6.0/underscore.js"
        else:
            script = \
"//cdnjs.cloudflare.com/ajax/libs/underscore.js/1.6.0/underscore-min.js"
    else:
        if debug:
            script = URL(c="static", f="scripts/underscore.js")
        else:
            script = URL(c="static", f="scripts/underscore-min.js")
    if script not in scripts:
        scripts.append(script)

# END =========================================================================
