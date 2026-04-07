"""
    Infection test result reporting for RLPPTM

    License: MIT
"""

import base64
import datetime
import hashlib
import json
import requests
import secrets
import sys
import uuid

from gluon import current, Field, IS_EMPTY_OR, IS_IN_SET, SQLFORM, URL, \
                  BUTTON, DIV, FORM, H5, INPUT, TABLE, TD, TR

from core import ConsentTracking, DateField, IS_ONE_OF, CustomController, CRUDMethod, \
                 s3_mark_required, s3_qrcode_represent, s3_str, \
                 JSONERRORS

from .dcc import DCC
from .vouchers import RLPCardLayout

CWA = {"system": "RKI / Corona-Warn-App",
       "app": "Corona-Warn-App",
       }

# =============================================================================
class TestResultRegistration(CRUDMethod):
    """ REST Method to Register Test Results """

    # -------------------------------------------------------------------------
    def apply_method(self, r, **attr):
        """
            Page-render entry point for REST interface.

            Args:
                r: the CRUDRequest instance
                attr: controller attributes
        """

        output = {}
        if r.method == "register":
            output = self.register(r, **attr)
        elif r.method == "certify":
            output = self.certify(r, **attr)
        elif r.method == "cwaretry":
            output = self.cwaretry(r, **attr)
        else:
            r.error(405, current.ERROR.BAD_METHOD)
        return output

    # -------------------------------------------------------------------------
    def register(self, r, **attr):
        """
            Register a test result

            Args:
                r: the CRUDRequest instance
                attr: controller attributes
        """

        if r.http not in ("GET", "POST"):
            r.error(405, current.ERROR.BAD_METHOD)
        if not r.interactive:
            r.error(415, current.ERROR.BAD_FORMAT)

        T = current.T
        db = current.db
        s3db = current.s3db
        auth = current.auth

        request = current.request
        response = current.response
        s3 = response.s3

        settings = current.deployment_settings

        # Instantiate Consent Tracker
        consent = ConsentTracking(processing_types=["CWA_ANONYMOUS", "CWA_PERSONAL"])

        table = s3db.disease_case_diagnostics

        # Configure disease_id
        field = table.disease_id
        if field.writable:
            default_disease = None
            offset = 1
        else:
            default_disease = field.default
            field.readable = False
            offset = 0

        # Probe date is mandatory
        field = table.probe_date
        requires = field.requires
        if isinstance(requires, IS_EMPTY_OR):
            field.requires = requires.other

        # Configure demographic_id
        if settings.get_disease_testing_report_by_demographic():
            field = table.demographic_id
            field.readable = field.writable = True
            requires = field.requires
            if isinstance(requires, IS_EMPTY_OR):
                field.requires = requires.other
            offset += 1

        # Configure device_id
        field = table.device_id
        field.readable = field.writable = True

        dtable = s3db.disease_testing_device
        query = (dtable.device_class == "RAT") & \
                (dtable.approved == True) & \
                (dtable.available == True)
        if default_disease:
            query = (dtable.disease_id == default_disease) & query
        field.requires = IS_EMPTY_OR(
                            IS_ONE_OF(db(query), "disease_testing_device.id",
                                      field.represent,
                                      ))

        cwa_options = (("NO", T("Do not report")),
                       ("ANONYMOUS", T("Issue anonymous contact tracing code")),
                       ("PERSONAL", T("Issue personal test certificate")),
                       )
        formfields = [# -- Test Result --
                      table.site_id,
                      table.disease_id,
                      table.probe_date,
                      table.demographic_id,
                      table.result,

                      # -- Report to CWA --
                      Field("report_to_cwa", "string",
                            requires = IS_IN_SET(cwa_options, sort=False, zero=""),
                            default = "NO",
                            label = T("Report test result to %(system)s") % CWA,
                            ),
                      Field("last_name",
                            label = T("Last Name"),
                            ),
                      Field("first_name",
                            label = T("First Name"),
                            ),
                      DateField("date_of_birth",
                                label = T("Date of Birth"),
                                month_selector = True,
                                ),
                      Field("dcc_option", "boolean",
                            default = False,
                            label = T("Provide Digital %(title)s Certificate") % {"title": "COVID-19 Test"},
                            ),
                      table.device_id,
                      Field("consent",
                            label = "",
                            widget = consent.widget,
                            ),
                      ]

        # Required fields
        required_fields = ["device_id"]

        # Subheadings
        subheadings = ((0, T("Test Result")),
                       (3 + offset, CWA["system"]),
                       )

        # Generate labels (and mark required fields in the process)
        labels, has_required = s3_mark_required(formfields,
                                                mark_required = required_fields,
                                                )
        s3.has_required = has_required

        # Form buttons
        REGISTER = T("Submit")
        buttons = [INPUT(_type = "submit",
                         _value = REGISTER,
                         ),
                   ]

        # Construct the form
        response.form_label_separator = ""
        form = SQLFORM.factory(table_name = "test_result",
                               record = None,
                               hidden = {"_next": auth.get_vars_next()},
                               labels = labels,
                               separator = "",
                               showid = False,
                               submit_button = REGISTER,
                               delete_label = auth.messages.delete_label,
                               formstyle = settings.get_ui_formstyle(),
                               buttons = buttons,
                               *formfields)

        # Identify form for CSS & JS Validation
        form.add_class("result-register")

        # Add Subheadings
        if subheadings:
            for pos, heading in subheadings[::-1]:
                form[0].insert(pos, DIV(heading, _class="subheading"))

        # Inject scripts
        script = "/%s/static/themes/RLP/js/testresult.js" % r.application
        if script not in s3.scripts:
            s3.scripts.append(script)
        s3.jquery_ready.append("S3EnableNavigateAwayConfirm()")

        if form.accepts(request.vars,
                        current.session,
                        formname = "register",
                        onvalidation = self.validate,
                        ):

            return self.accept(r, form)

        elif form.errors:
            current.response.error = T("There are errors in the form, please check your input")

        # Custom View
        CustomController._view("RLPPTM", "testresult.html")

        # Page title and CMS intro text
        title = T("Register Test Result")
        intro = s3db.cms_get_content("TestResultRegistrationIntro",
                                     module = "disease",
                                     resource = "case_diagnostics",
                                     )

        return {"title": title,
                "intro": intro,
                "form": form,
                }

    # -------------------------------------------------------------------------
    @staticmethod
    def validate(form):
        """
            Validate the test result registration form
            - personal details are required for reporting to CWA by name
            - make sure the required consent option is checked
            - make sure the selected device matches the selected disease
        """

        T = current.T

        formvars = form.vars

        response = ConsentTracking.parse(formvars.get("consent"))

        # Verify that we have the data and consent required
        cwa = formvars.get("report_to_cwa")
        if cwa == "PERSONAL":
            # Personal data required
            for fn in ("first_name", "last_name", "date_of_birth"):
                if not formvars.get(fn):
                    form.errors[fn] = T("Enter a value")
            # CWA_PERSONAL consent required
            c = response.get("CWA_PERSONAL")
            if not c or not c[1]:
                form.errors.consent = T("Consent required")
        elif cwa == "ANONYMOUS":
            # CWA_ANONYMOUS consent required
            c = response.get("CWA_ANONYMOUS")
            if not c or not c[1]:
                form.errors.consent = T("Consent required")

        # Verify that device ID is specified if DCC option is selected
        dcc = formvars.get("dcc_option")
        if dcc:
            if not formvars.get("device_id"):
                form.errors.device_id = T("Enter a value")

        # Verify that the selected testing device matches the selected
        # disease (only if disease is selectable - otherwise, the device
        # list is pre-filtered anyway):
        if "disease_id" in formvars:
            disease_id = formvars["disease_id"]
            device_id = formvars.get("device_id")
            if device_id:
                table = current.s3db.disease_testing_device
                query = (table.id == device_id) & \
                        (table.disease_id == disease_id) & \
                        (table.deleted == False)
                row = current.db(query).select(table.id,
                                               limitby = (0, 1),
                                               ).first()
                if not row:
                    form.errors.device_id = T("Device not applicable for selected disease")

    # -------------------------------------------------------------------------
    def accept(self, r, form):
        """
            Accept the test result form, and report to CWA if selected

            Args:
                r: the CRUDRequest
                form: the test result form

            Returns:
                output dict for view, or None when redirecting
        """

        T = current.T
        auth = current.auth
        s3db = current.s3db
        response = current.response

        formvars = form.vars

        # Create disease_case_diagnostics record
        testresult = {"result": formvars.get("result"),
                      }
        for fn in ("site_id",
                   "disease_id",
                   "probe_date",
                   "device_id",
                   "demographic_id",
                   ):
            if fn in formvars:
                testresult[fn] = formvars[fn]

        table = s3db.disease_case_diagnostics

        testresult["id"] = record_id = table.insert(**testresult)
        if not record_id:
            raise RuntimeError("Could not create testresult record")

        auth.s3_set_record_owner(table, record_id)
        auth.s3_make_session_owner(table, record_id)
        s3db.onaccept(table, testresult, method="create")

        response.confirmation = T("Test Result registered")

        # Report to CWA?
        report_to_cwa = formvars.get("report_to_cwa")
        dcc_option = False
        if report_to_cwa == "ANONYMOUS":
            processing_type = "CWA_ANONYMOUS"
            cwa_report = CWAReport(record_id)

        elif report_to_cwa == "PERSONAL":
            dcc_option = formvars.get("dcc_option")
            processing_type = "CWA_PERSONAL"
            cwa_report = CWAReport(record_id,
                                   anonymous = False,
                                   first_name = formvars.get("first_name"),
                                   last_name = formvars.get("last_name"),
                                   dob = formvars.get("date_of_birth"),
                                   dcc = dcc_option,
                                   )
        else:
            processing_type = cwa_report = None

        if cwa_report:
            # Register consent
            cwa_report.register_consent(processing_type,
                                        formvars.get("consent"),
                                        )
            # Send to CWA
            if cwa_report.send():
                response.information = T("Result reported to %(system)s") % CWA
                retry = False
            else:
                response.error = T("Report to %(system)s failed") % CWA
                retry = True

            # Store DCC data
            if dcc_option:
                cwa_data = cwa_report.data
                try:
                    hcert = DCC.from_result(cwa_data.get("hash"),
                                            record_id,
                                            cwa_data.get("fn"),
                                            cwa_data.get("ln"),
                                            cwa_data.get("dob"),
                                            )
                except ValueError as e:
                    hcert = None
                    response.warning = str(e)
                if hcert:
                    hcert.save()
                else:
                    # Remove DCC flag if hcert could not be generated
                    cwa_report.dcc = False

            CustomController._view("RLPPTM", "certificate.html")

            # Title
            field = table.disease_id
            if cwa_report.disease_id and field.represent:
                disease = field.represent(cwa_report.disease_id)
                title = "%s %s" % (disease, T("Test Result"))
            else:
                title = T("Test Result")

            output = {"title": title,
                      "intro": None,
                      "form": cwa_report.formatted(retry=retry),
                      }
        else:
            self.next = r.url(id=record_id, method="read")
            output = None

        return output

    # -------------------------------------------------------------------------
    @classmethod
    def certify(cls, r, **attr):
        """
            Generate a test certificate (PDF) for download

            Args:
                r: the CRUDRequest instance
                attr: controller attributes
        """

        record = r.record
        if not record:
            r.error(400, current.ERROR.BAD_REQUEST)
        if r.representation != "pdf":
            r.error(415, current.ERROR.BAD_FORMAT)

        testid = record.uuid
        site_id = record.site_id
        probe_date = record.probe_date
        result = record.result
        disease_id = record.disease_id

        item = {"testid": testid,
                "result_raw": result,
                }

        if r.http == "POST":

            post_vars = r.post_vars

            # Extract and check formkey from post data
            formkey = post_vars.get("_formkey")
            keyname = "_formkey[testresult/%s]" % r.id
            if not formkey or formkey not in current.session.get(keyname, []):
                r.error(403, current.ERROR.NOT_PERMITTED)

            # Extract cwadata
            cwadata = post_vars.get("cwadata")
            if not cwadata:
                r.error(400, current.ERROR.BAD_REQUEST)
            try:
                cwadata = json.loads(cwadata)
            except JSONERRORS:
                r.error(400, current.ERROR.BAD_REQUEST)

            # Generate the CWAReport (implicitly validates the hash)
            anonymous = "fn" not in cwadata
            try:
                cwareport = CWAReport(r.id,
                                      anonymous = anonymous,
                                      first_name = cwadata.get("fn"),
                                      last_name = cwadata.get("ln"),
                                      dob = cwadata.get("dob"),
                                      dcc = post_vars.get("dcc") == "1",
                                      salt = cwadata.get("salt"),
                                      dhash = cwadata.get("hash"),
                                      )
            except ValueError:
                r.error(400, current.ERROR.BAD_RECORD)

            # Generate the data item
            item["link"] = cwareport.get_link()
            if not anonymous:
                for k in ("ln", "fn", "dob"):
                    value = cwadata.get(k)
                    if k == "dob":
                        value = CWAReport.to_local_dtfmt(value)
                    item[k] = value

        else:
            cwareport = None

        s3db = current.s3db

        # Test Station
        table = s3db.disease_case_diagnostics
        field = table.site_id
        if field.represent:
            item["site_name"] = field.represent(site_id)
        if site_id:
            item.update(cls.get_site_details(site_id))

        # Probe date and test result
        field = table.probe_date
        if field.represent:
            item["test_date"] = field.represent(probe_date)
        field = table.result
        if field.represent:
            item["result"] = field.represent(result)

        # Title
        T = current.T
        field = table.disease_id
        if disease_id and field.represent:
            disease = field.represent(disease_id)
            title = "%s %s" % (disease, T("Test Result"))
        else:
            title = T("Test Result")
        item["title"] = pdf_title = title

        from core import DataExporter
        from gluon.contenttype import contenttype

        # Export PDF
        output = DataExporter.pdfcard([item],
                                      layout = CWACardLayout,
                                      title = pdf_title,
                                      )

        response = current.response
        disposition = "attachment; filename=\"certificate.pdf\""
        response.headers["Content-Type"] = contenttype(".pdf")
        response.headers["Content-disposition"] = disposition

        return output

    # -------------------------------------------------------------------------
    @staticmethod
    def cwaretry(r, **attr):
        """
            Retry sending test result to CWA result server

            Args:
                r: the CRUDRequest instance
                attr: controller attributes
        """

        if not r.record:
            r.error(400, current.ERROR.BAD_REQUEST)
        if r.http != "POST":
            r.error(405, current.ERROR.BAD_METHOD)
        if r.representation != "json":
            r.error(415, current.ERROR.BAD_FORMAT)

        T = current.T

        # Parse JSON body
        s = r.body
        s.seek(0)
        try:
            options = json.load(s)
        except JSONERRORS:
            options = None
        if not isinstance(options, dict):
            r.error(400, "Invalid request options")

        # Verify formkey
        formkey = options.get("formkey")
        keyname = "_formkey[testresult/%s]" % r.id
        if not formkey or formkey not in current.session.get(keyname, []):
            r.error(403, current.ERROR.NOT_PERMITTED)

        # Instantiate CWAReport
        cwadata = options.get("cwadata", {})
        anonymous = "fn" not in cwadata
        try:
            cwareport = CWAReport(r.id,
                                  anonymous = anonymous,
                                  first_name = cwadata.get("fn"),
                                  last_name = cwadata.get("ln"),
                                  dob = cwadata.get("dob"),
                                  dcc = options.get("dcc") == "1",
                                  salt = cwadata.get("salt"),
                                  dhash = cwadata.get("hash"),
                                  )
        except ValueError:
            r.error(400, current.ERROR.BAD_RECORD)

        success = cwareport.send()
        if success:
            message = T("Result reported to %(system)s") % CWA
            output = current.xml.json_message(message=message)
        else:
            r.error(503, T("Report to %(system)s failed") % CWA)
        return output

    # -------------------------------------------------------------------------
    @staticmethod
    def get_site_details(site_id):
        """
            Get details of the test station (address, email, phone number)

            Args:
                site_id: the site ID of the facility

            Returns:
                a dict {site_email, site_phone, site_address, site_place}

            Note:
                The dict items are only added when data are available.
        """

        details = {}

        s3db = current.s3db
        ftable = s3db.org_facility
        ltable = s3db.gis_location

        left = ltable.on(ltable.id == ftable.location_id)
        query = (ftable.site_id == site_id) & \
                (ftable.deleted == False)
        row = current.db(query).select(ftable.phone1,
                                       ftable.email,
                                       ltable.id,
                                       ltable.addr_street,
                                       ltable.addr_postcode,
                                       ltable.L4,
                                       ltable.L3,
                                       left = left,
                                       limitby = (0, 1),
                                       ).first()
        if row:
            facility = row.org_facility
            if facility.email:
                details["site_email"] = facility.email
            if facility.phone1:
                details["site_phone"] = facility.phone1

            location = row.gis_location
            if location.id:
                if location.addr_street:
                    details["site_address"] = location.addr_street
                place = []
                if location.addr_postcode:
                    place.append(location.addr_postcode)
                if location.L4:
                    place.append(location.L4)
                elif location.L3:
                    place.append(location.L3)
                else:
                    place = None
                if place:
                    details["site_place"] = " ".join(place)

        return details

# =============================================================================
class CWAReport:
    """
        CWA Report Generator
        @see: https://github.com/corona-warn-app/cwa-quicktest-onboarding/wiki/Anbindung-der-Partnersysteme
    """

    def __init__(self,
                 result_id,
                 anonymous=True,
                 first_name=None,
                 last_name=None,
                 dob=None,
                 dcc=False,
                 salt=None,
                 dhash=None,
                 ):
        """
            Args:
                result_id: the disease_case_diagnostics record ID
                anonymous: generate anonymous report
                first_name: first name
                last_name: last name
                dob: date of birth (str in isoformat, or datetime.date)
                dcc: whether to provide a digital test certificate
                salt: previously used salt (for retry)
                dhash: previously generated hash (for retry)

            Note:
                - if not anonymous, personal data are required
        """

        db = current.db
        s3db = current.s3db

        # Lookup the result
        if result_id:
            table = s3db.disease_case_diagnostics
            query = (table.id == result_id) & \
                    (table.deleted == False)
            result = db(query).select(table.uuid,
                                      table.modified_on,
                                      table.site_id,
                                      table.disease_id,
                                      table.probe_date,
                                      table.result_date,
                                      table.result,
                                      limitby = (0, 1),
                                      ).first()
            if not result:
                raise ValueError("Test result #%s not found" % result_id)
        else:
            raise ValueError("Test result ID is required")

        # Store the test result
        self.result_id = result_id
        self.site_id = result.site_id
        self.disease_id = result.disease_id
        self.probe_date = result.probe_date
        self.result_date = result.result_date
        self.result = result.result
        self.dcc = False

        # Determine the testid and timestamp
        testid = result.uuid
        timestamp = int(DCC.utc_timestamp(result.probe_date))

        if not anonymous:
            if not all(value for value in (first_name, last_name, dob)):
                raise ValueError("Incomplete person data for personal report")
            data = {"fn": first_name,
                    "ln": last_name,
                    "dob": dob.isoformat() if isinstance(dob, datetime.date) else dob,
                    "timestamp": timestamp,
                    "testid": testid,
                    }
            if dcc:
                # Indicate whether we can issue a DCC (Digital COVID Certificate)
                self.dcc = bool(dcc) and self.result in ("POS", "NEG")
        else:
            data = {"timestamp": timestamp,
                    }

        # Add salt and hash
        data["salt"] = salt if salt else self.get_salt()
        if dhash:
            # Verify the hash
            if dhash != self.get_hash(data, anonymous=anonymous):
                raise ValueError("Invalid hash")
            data["hash"] = dhash
        else:
            data["hash"] = self.get_hash(data, anonymous=anonymous)

        self.data = data

    # -------------------------------------------------------------------------
    @staticmethod
    def get_salt():
        """
            Produce a secure 128-bit (=16 bytes) random hex token

            Returns:
                the token as str
        """
        return secrets.token_hex(16).upper()

    # -------------------------------------------------------------------------
    @staticmethod
    def get_hash(data, anonymous=True):
        """
            Generate a SHA256 hash from report data string
            String formats:
            - personal : [dob]#[fn]#[ln]#[timestamp]#[testid]#[salt]
            - anonymous: [timestamp]#[salt]

            Returns:
                the hash as str
        """

        hashable = lambda fields: "#".join(str(data[k]) for k in fields)
        if not anonymous:
            dstr = hashable(["dob", "fn", "ln", "timestamp", "testid", "salt"])
        else:
            dstr = hashable(["timestamp", "salt"])

        return hashlib.sha256(dstr.encode("utf-8")).hexdigest().lower()

    # -------------------------------------------------------------------------
    def get_link(self):
        """
            Construct the link for QR code generation

            Returns:
                the link as str
        """

        # Template for CWA-link
        template = current.deployment_settings.get_custom(key="cwa_link_template")

        # Add "dgc" parameter if DCC option enabled
        data = dict(self.data)
        if self.dcc:
            data["dgc"] = True

        # Convert data to JSON
        from core import JSONSEPARATORS
        data_json = json.dumps(data, separators=JSONSEPARATORS)

        # Base64-encode the data JSON
        data_str = base64.urlsafe_b64encode(data_json.encode("utf-8")).decode("utf-8")

        # Generate the link
        link = template % {"data": data_str}

        return link

    # -------------------------------------------------------------------------
    @staticmethod
    def to_local_dtfmt(dtstr):
        """
            Helper to convert an ISO-formatted date to local format

            Args:
                dtstr: the ISO-formatted date as string

            Returns:
                the date in local format as string
        """

        c = current.calendar
        dt = c.parse_date(dtstr)
        return c.format_date(dt, local=True) if dt else dtstr

    # -------------------------------------------------------------------------
    def formatted(self, retry=False):
        """
            Formatted version of this report

            Args:
                retry: add retry-action for sending to CWA

            Returns:
                a FORM containing
                    - the QR-code
                    - human-readable report details
                    - actions to download PDF, or retry sending to CWA
        """

        T = current.T
        table = current.s3db.disease_case_diagnostics

        # Personal Details
        data_repr = TABLE()
        data = self.data
        if not any(k in data for k in ("fn", "ln", "dob")):
            data_repr.append(TR(TD(T("Person Tested")),
                                TD(T("anonymous"), _class="cwa-data"),
                                ))
        else:
            labels = {"fn": T("First Name"),
                      "ln": T("Last Name"),
                      "dob": T("Date of Birth"),
                      }
            for k in ("ln", "fn", "dob"):
                value = data[k]
                if k == "dob":
                    value = self.to_local_dtfmt(value)
                data_repr.append(TR(TD(labels.get(k)),
                                    TD(value, _class="cwa-data"),
                                    ))

        # Test Station, date and result
        field = table.site_id
        if field.represent:
            data_repr.append(TR(TD(field.label),
                                TD(field.represent(self.site_id),
                                   _class="cwa-data",
                                   ),
                                ))
        field = table.probe_date
        if field.represent:
            data_repr.append(TR(TD(field.label),
                                TD(field.represent(self.probe_date),
                                   _class="cwa-data",
                                   ),
                                ))
        field = table.result
        if field.represent:
            data_repr.append(TR(TD(field.label),
                                TD(field.represent(self.result),
                                   _class="cwa-data",
                                   ),
                                ))

        # Details
        details = DIV(H5(T("Details")),
                      data_repr,
                      _class = "cwa-details",
                      )

        # QR Code
        title = T("Code for %(app)s") % CWA
        qrcode = DIV(s3_qrcode_represent(self.get_link(), show_value=False),
                     DIV(title, _class="cwa-qrcode-title"),
                     _class="cwa-qrcode",
                     )
        if retry:
            qrcode.add_class("hide")

        # Form buttons
        buttons = [
            BUTTON(T("Download PDF"),
                   _class = "tiny primary button cwa-pdf",
                   _type = "button",
                   ),
            ]
        if retry:
            buttons[0].add_class("hide")
            buttons.append(BUTTON(T("Retry sending to %(app)s") % CWA,
                                  _class = "tiny alert button cwa-retry",
                                  _type = "button",
                                  ))

        # Generate form key
        formurl = URL(c = "disease",
                      f = "case_diagnostics",
                      args = [self.result_id],
                      )
        formkey = uuid.uuid4().hex

        # Store form key in session
        session = current.session
        keyname = "_formkey[testresult/%s]" % self.result_id
        session[keyname] = session.get(keyname, [])[-9:] + [formkey]

        form = FORM(DIV(DIV(details,
                            qrcode,
                            _class="small-12 columns",
                            ),
                        _class="row form-row",
                        ),
                    DIV(DIV(buttons,
                            _class="small-12 columns",
                            ),
                        _class="row form-row",
                        ),
                    hidden = {"formurl": formurl,
                              "cwadata": json.dumps(self.data),
                              "dcc": "1" if self.dcc else "0",
                              "_formkey": formkey,
                              },
                    )

        return form

    # -------------------------------------------------------------------------
    def register_consent(self, processing_type, response):
        """
            Register consent assertion using the current hash as reference

            Args:
                processing type: the data processing type for which
                                 consent is required
                response: the consent response
        """

        data = self.data

        dhash = data.get("hash")
        if not dhash:
            raise ValueError("Missing context hash")

        ConsentTracking.assert_consent(dhash, processing_type, response)

    # -------------------------------------------------------------------------
    def send(self):
        """
            Send the CWA Report to the server;
            see also: https://github.com/corona-warn-app/cwa-quicktest-onboarding/blob/master/api/quicktest-openapi.json

            Returns:
                True|False whether successful
        """

        # Encode the result
        results = {"NEG": 6, "POS": 7, "INC": 8}
        result = results.get(self.result)
        if not result:
            current.log.error("CWAReport: invalid test result %s" % self.result)
            return False

        # Build the QuickTestResult JSON structure
        data = self.data
        testresult = {"id": data.get("hash"),
                      "sc": data.get("timestamp"),
                      "result": result,
                      }

        # The CWA server URL
        settings = current.deployment_settings
        server_url = settings.get_custom("cwa_server_url")
        if not server_url:
            raise RuntimeError("No CWA server URL configured")

        # The client credentials to access the server
        folder = current.request.folder
        cert = settings.get_custom("cwa_client_certificate")
        key = settings.get_custom("cwa_certificate_key")
        if not cert or not key:
            raise RuntimeError("No CWA client credentials configured")
        cert = "%s/%s" % (folder, cert)
        key = "%s/%s" % (folder, key)

        # The certificate chain to verify the server identity
        verify = settings.get_custom("cwa_server_ca")
        if verify:
            # Use the specified CA Certificate to verify server identity
            verify = "%s/%s" % (current.request.folder, verify)
        else:
            # Use python-certifi (=> make sure the latest version is installed)
            verify = True

        # Build the result_list
        result_list = {"testResults": [testresult]}
        if self.dcc:
            # Look up the LabID
            lab_id = DCC.get_issuer_id(self.site_id)
            if not lab_id:
                raise RuntimeError("Point-of-Care ID for test station not found")
            else:
                result_list["labId"] = lab_id

        # POST to server
        try:
            sr = requests.post(server_url,
                               # Send the QuickTestResultList
                               json = result_list,
                               cert = (cert, key),
                               verify = verify,
                               )
        except Exception:
            # Local error
            error = sys.exc_info()[1]
            current.log.error("CWAReport: transmission to CWA server failed (local error: %s)" % error)
            return False

        # Check return code (should be 204, but 202/200 would also be good news)
        if sr.status_code not in (204, 202, 200):
            # Remote error
            current.log.error("CWAReport: transmission to CWA server failed, status code %s" % sr.status_code)
            return False

        # Success
        return True

# =============================================================================
class CWACardLayout(RLPCardLayout):
    """
        Layout for printable vouchers
    """

    # -------------------------------------------------------------------------
    def draw(self):
        """
            Draw the card (one side)

            Instance attributes (NB draw-function should not modify them):
            - self.canv...............the canvas (provides the drawing methods)
            - self.resource...........the resource
            - self.item...............the data item (dict)
            - self.labels.............the field labels (dict)
            - self.backside...........this instance should render the backside
                                      of a card
            - self.multiple...........there are multiple cards per page
            - self.width..............the width of the card (in points)
            - self.height.............the height of the card (in points)

            NB Canvas coordinates are relative to the lower left corner of the
               card's frame, drawing must not overshoot self.width/self.height
        """

        c = self.canv
        #w = self.width
        h = self.height

        item = self.item

        draw_string = self.draw_string
        draw_box_with_label = self.draw_box_with_label
        draw_line_with_label = self.draw_line_with_label

        if not self.backside:

            from reportlab.lib.units import cm

            LEFT = 2.5 * cm
            RIGHT = 11.0 * cm

            # Tested Person Details
            draw_box_with_label(LEFT, h-3.1*cm, 5*cm, 1.2*cm, label="Name, Vorname")
            draw_box_with_label(LEFT + 5.0 * cm, h-3.1*cm, 3*cm, 1.2*cm, label="geb. am:")
            draw_box_with_label(LEFT, h-4.3*cm, 8*cm, 1.2*cm, label="Straße, Hausnummer:")
            draw_box_with_label(LEFT, h-5.8*cm, 8*cm, 1.5*cm, label="Postleitzahl, Wohnort:")

            if "fn" in item:
                names = [item.get(key) for key in ("ln", "fn") if item.get(key)]
                if names:
                    draw_string(2.7*cm, h-2.8*cm, ", ".join(names),
                                width=4.6*cm, height=0.8*cm, size=8, bold=False)

                dob = item.get("dob")
                if dob:
                    draw_string(7.7*cm, h-2.8*cm, dob,
                                width=2.6*cm, height=0.8*cm, size=8, bold=False)

            # CWA QR-Code
            link = item.get("link")
            if link:
                self.draw_qrcode(link,
                                 15.0*cm,
                                 h - 1.5*cm,
                                 size = 5.5*cm,
                                 halign = "center",
                                 valign = "top",
                                 level = "M",
                                 )
                desc = "Code zum Abrufen des Testergebnisses mit %(app)s" % CWA
                draw_string(11.5*cm, h-7.2*cm, "%s<super rise=1>*</super>" % desc,
                            width=7*cm, height=0.5*cm, size=6, bold=False, halign="center")

            # Test ID
            draw_string(LEFT, h-8.6*cm, "Test ID:",
                        width=7.75*cm, height=0.5*cm, size=12, bold=True)
            testid = item.get("testid")
            if testid:
                try:
                    testid = uuid.UUID(testid)
                except ValueError:
                    testid = None
            if testid:
                draw_box_with_label(LEFT, h-10.0*cm, 7.75*cm, 1.0*cm, label="LSJV Reg.Nr.")
                draw_string(LEFT + 0.8*cm, h-9.8*cm, str(testid).upper(),
                            width=7.5*cm, height=0.5*cm, size=8, bold=False)
            else:
                draw_box_with_label(LEFT, h-10.0*cm, 7.75*cm, 1.0*cm, label="Fortlaufende Nummer")

            # Test Station Details
            draw_string(RIGHT, h-8.6*cm, "Teststelle:",
                        width=7.75*cm, height=0.5*cm, size=12, bold=True)
            draw_box_with_label(RIGHT, h-10.0*cm, 7.75*cm, 1.0*cm, label="Straße, Hausnummer")
            draw_box_with_label(RIGHT, h-11.0*cm, 7.75*cm, 1.0*cm, label="Postleitzahl, Ort")
            draw_box_with_label(RIGHT, h-12.0*cm, 7.75*cm, 1.0*cm, label="Telefonnummer:")
            draw_box_with_label(RIGHT, h-13.0*cm, 7.75*cm, 1.0*cm, label="E-Mail Adresse")

            site_place = item.get("site_place")
            if site_place:
                draw_string(11.2*cm, h-10.8*cm, site_place,
                            width=7.2*cm, height=0.5*cm, size=8, bold=False)
                site_address = item.get("site_address")
                if site_address:
                    draw_string(11.2*cm, h-9.8*cm, site_address,
                                width=7.2*cm, height=0.5*cm, size=8, bold=False)
            site_phone = item.get("site_phone")
            if site_phone:
                draw_string(11.2*cm, h-11.8*cm, site_phone,
                            width=7.2*cm, height=0.5*cm, size=8, bold=False)
            site_email = item.get("site_email")
            if site_email:
                draw_string(11.2*cm, h-12.8*cm, site_email,
                            width=7.2*cm, height=0.5*cm, size=8, bold=False)

            # Test Date and Result
            draw_string(LEFT, h-14.7*cm, "<u>Bescheinigung über das Ergebnis des PoC-Antigen-Tests:</u>",
                        width=10*cm, height=0.5*cm, size=10, bold=True)
            draw_string(LEFT, h-15.9*cm, "Datum des PoC-Antigen-Tests:",
                        width=10*cm, height=0.5*cm, size=9, bold=True)
            draw_string(2.5*cm, h-16.9*cm, "Testergebnis:",
                        width=2.5*cm, height=0.5*cm, size=9, bold=True)

            test_date = item.get("test_date")
            if test_date:
                draw_string(7.5*cm, h-15.9*cm, test_date,
                            width=7.75*cm, height=0.5*cm, size=8, bold=False)
            else:
                draw_line_with_label(7.5*cm, h-15.9*cm)

            # Test Result
            result = item.get("result_raw")
            if result == "NEG":
                result_text = "Coronavirus SARS-CoV-2 NICHT nachgewiesen (negativ)"
            elif result == "POS":
                result_text = "Coronavirus SARS-CoV-2 nachgewiesen (positiv)"
            else:
                result_text = None
            if result_text:
                draw_string(7.5*cm, h-16.9*cm, result_text,
                            width=8*cm, height=0.5*cm, size=9, bold=False)
            else:
                draw_line_with_label(7.5*cm, h-16.9*cm)

            # Test Device
            draw_string(LEFT, h-19.3*cm, "<u>Angaben zum verwendeten PoC-Antigen-Test:</u>",
                        width=10*cm, height=0.5*cm, size=9, bold=True)
            draw_string(LEFT, h-19.9*cm, "Hersteller:",
                        width=10*cm, height=0.5*cm, size=9, bold=True)
            draw_string(LEFT, h-20.5*cm, "PZN:",
                        width=10*cm, height=0.5*cm, size=9, bold=True)

            # Signature
            draw_line_with_label(LEFT, h-21.7*cm, 7.5*cm, label="Ort, Datum, Uhrzeit")
            draw_line_with_label(LEFT, h-23.3*cm, 7.5*cm, label="Unterschrift der/des Verantwortlichen der Teststelle")
            draw_box_with_label(RIGHT + 0.5*cm, h-23.3*cm, 7*cm, 4*cm, label="Stempel der Teststelle")

            # Legal Information
            draw_string(LEFT, h-27*cm, "Wer dieses Dokument fälscht, einen nicht erfolgten Test bescheinigt, einen positiven Test fälschlicherweise als negativ bescheinigt oder wer ein falsches Dokument verwendet, um Zugang zu einer Einrichtung oder einem Angebot zu erhalten, begeht eine Ordnungswidrigkeit, die mit einer Geldbuße geahndet wird.",
                        width=16*cm, height=2*cm, size=8, bold=False, box=True)

            # Hint for QR-Code
            if link:
                hint = "Dieser QR-Code dient ausschließlich dem Abruf des Testergebnisses mit der Corona Warn App und kann nicht als Testnachweis mit anderen Apps (z.B. CovPass App) gelesen werden."
                draw_string(LEFT, h-28.3*cm, "<super rise=1>*</super>%s" % hint,
                            width=16*cm, height=2*cm, size=7, bold=False)

            # Add a cutting line with multiple cards per page
            if self.multiple:
                c.setDash(1, 2)
                self.draw_outline()
        else:
            # No backside
            pass

    # -------------------------------------------------------------------------
    def draw_box_with_label(self, x, y, width=120, height=20, label=None):
        """
            Draw a box with a label inside (paper form element)

            Args:
                x: the horizontal position (from left)
                y: the vertical position (from bottom)
                width: the width of the box
                height: the height of the box
                label: the label
        """

        label_size = 7

        c = self.canv

        c.saveState()

        c.setLineWidth(0.5)
        c.rect(x, y, width, height)

        if label:
            c.setFont("Helvetica", label_size)
            c.setFillGray(0.3)
            c.drawString(x + 4, y + height - label_size - 1, s3_str(label))

        c.restoreState()

    # -------------------------------------------------------------------------
    def draw_line_with_label(self, x, y, width=120, label=None):
        """
            Draw a placeholder line with label underneath (paper form element)

            Args:
                x: the horizontal position (from left)
                y: the vertical position (from bottom)
                width: the horizontal length of the line
                label: the label
        """

        label_size = 7

        c = self.canv

        c.saveState()

        c.setLineWidth(0.5)
        c.line(x, y, x + width, y)

        if label:
            c.setFont("Helvetica", label_size)
            c.setFillGray(0.3)
            c.drawString(x, y - label_size - 1, s3_str(label))

        c.restoreState()

    # -------------------------------------------------------------------------
    def draw_string(self, x, y, value, width=120, height=40, size=7, bold=False, halign=None, box=False):
        """
            Draw a string (label, value)

            Args:
                x: the horizontal position (from left)
                y: the vertical position (from bottom)
                value: the string to render
                width: the width of the text box
                height: the height of the text box
                size: the font size
                bold: use boldface font
                halign: horizonal alignment, "left" (or None, the default)|"right"|"center"
                box: render the box (with border and grey background)

            Returns:
                the actual height of the box
        """

        return self.draw_value(x + width/2.0,
                               y,
                               value,
                               width = width,
                               height = height,
                               size = size,
                               bold = bold,
                               halign = halign,
                               box = box,
                               )

# END =========================================================================
