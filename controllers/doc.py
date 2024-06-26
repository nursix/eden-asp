"""
    Document Library - Controllers
"""

module = request.controller

if not settings.has_module(module):
    raise HTTP(404, body="Module disabled: %s" % module)

# =============================================================================
def index():
    "Module's Home Page"

    module_name = settings.modules[module].get("name_nice")
    response.title = module_name
    return dict(module_name=module_name)

# =============================================================================
def document():
    """ RESTful CRUD controller """

    # Pre-processor
    def prep(r):
        # Location Filter
        s3db.gis_location_filter(r)

        if r.method in ("create", "create.popup"):
            doc_id = get_vars.get("~.doc_id", None)
            if doc_id:
                # Coming from Profile page
                s3db.doc_document.doc_id.default = doc_id

        return True
    s3.prep = prep

    return crud_controller(rheader=s3db.doc_rheader)

# -----------------------------------------------------------------------------
def document_tabs(r):
    """
        Display the number of Components in the tabs
        - currently unused as we don't have these tabs off documents
    """

    tab_opts = [{"tablename": "irs_ireport",
                 "resource": "ireport",
                 "one_title": "1 Incident Report",
                 "num_title": " Incident Reports",
                },
                {"tablename": "cr_shelter",
                 "resource": "shelter",
                 "one_title": "1 Shelter",
                 "num_title": " Shelters",
                },
                {"tablename": "req_req",
                 "resource": "req",
                 "one_title": "1 Request",
                 "num_title": " Requests",
                },
                ]
    tabs = [(T("Details"), None)]
    crud_string = s3base.BasicCRUD.crud_string
    for tab_opt in tab_opts:
        tablename = tab_opt["tablename"]
        if tablename in db and document_id in db[tablename]:
            table = db[tablename]
            query = (table.deleted == False) & \
                    (table.document_id == r.id)
            tab_count = db(query).count()
            if tab_count == 0:
                label = crud_string(tablename, "label_create")
            elif tab_count == 1:
                label = tab_opt["one_title"]
            else:
                label = T(str(tab_count) + tab_opt["num_title"] )
            tabs.append( (label, tab_opt["resource"] ) )

    return tabs

# =============================================================================
def image():
    """ RESTful CRUD controller """

    # Pre-processor
    def prep(r):
        # Location Filter
        s3db.gis_location_filter(r)

        if r.method in ("create", "create.popup"):
            doc_id = get_vars.get("~.doc_id", None)
            if doc_id:
                # Coming from Profile page
                s3db.doc_image.doc_id.default = doc_id

        return True
    s3.prep = prep

    return crud_controller(rheader=s3db.doc_rheader)

# =============================================================================
def ck_upload():
    """
        Controller to handle uploads to CKEditor

        Based on https://github.com/timrichardson/web2py_ckeditor4
    """

    upload = request.vars.upload

    if upload is None:
        raise HTTP(401, "Missing required upload.")

    if not hasattr(upload, "file"):
        raise HTTP(401, "Upload is not proper type.")

    path = os.path.join(request.folder, "uploads")

    # Load Model
    table = s3db.doc_ckeditor

    form = SQLFORM.factory(Field("upload", "upload",
                                 requires = IS_NOT_EMPTY(),
                                 #uploadfs = self.settings.uploadfs,
                                 uploadfolder = path,
                                 ),
                           table_name = "doc_ckeditor",
                           )

    old_filename = upload.filename
    new_filename = table.upload.store(upload.file,
                                      upload.filename)
    #if self.settings.uploadfs:
    #    length = self.settings.uploadfs.getsize(new_filename)
    #else:
    length = os.path.getsize(os.path.join(path, new_filename))

    mime_type = upload.headers["content-type"]

    title = os.path.splitext(old_filename)[0]

    result = table.validate_and_insert(title = title,
                                       filename = old_filename,
                                       upload = new_filename,
                                       flength = length,
                                       mime_type = mime_type,
                                       )

    if result.id:
        text = ""
    else:
        text = result.errors

    url = URL(c="default", f="download",
              args = [new_filename])

    return {"text": text,
            "cknum": request.vars.CKEditorFuncNum,
            "url": url,
            }

# -----------------------------------------------------------------------------
def ck_browse():
    """
        Controller to handle uploads to CKEditor
    """

    table = s3db.doc_ckeditor
    #browse_filter = {}
    set = db(table.id > 0)
    #for key, val in browse_filter.items():
    #    if value[0] == "<":
    #        set = set(table[key] < value[1:])
    #    elif value[0] == ">":
    #        set = set(table[key] > value[1:])
    #    elif value[0] == "!":
    #        set = set(table[key] != value[1:])
    #    else:
    #        set = set(table[key] == value)

    rows = set.select(orderby = table.title)

    return {"rows": rows,
            "cknum": request.vars.CKEditorFuncNum,
            }

# -----------------------------------------------------------------------------
def ck_delete():
    """
        Controller to handle deletes in CKEditor
    """

    try:
        filename = request.args[0]
    except:
        raise HTTP(401, "Required argument filename missing.")

    table = s3db.doc_ckeditor
    db(table.upload == filename).delete()

    # Delete the file from storage
    #if self.settings.uploadfs:
    #    self.settings.uploadfs.remove(filename)
    #else:
    filepath = os.path.join(request.folder, "uploads", filename)
    os.unlink(filepath)

# -----------------------------------------------------------------------------
def card_config():

    return crud_controller()

# END =========================================================================
