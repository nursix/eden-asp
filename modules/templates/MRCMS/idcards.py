"""
    ID Card Generator and Layout for MRCMS

    License: MIT
"""

import hashlib
import os
import secrets
import uuid

#from dateutil.relativedelta import relativedelta

from reportlab.lib.pagesizes import A4
from reportlab.lib.colors import Color, HexColor
from reportlab.platypus import Paragraph
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT

from gluon import current, A, BUTTON, DIV, H5, SQLFORM, IS_IN_SET
from gluon.contenttype import contenttype

from s3dal import Field
from core import CRUDMethod, DateField, ICON, PDFCardLayout, \
                 s3_format_fullname, s3_mark_required, s3_str

from core.formats.card import CREDITCARD

# Fonts we use in this layout
NORMAL = "Helvetica"
BOLD = "Helvetica-Bold"

CCLS = CREDITCARD[::-1]
# =============================================================================
class GenerateIDCard(CRUDMethod):
    """
        Method to generate registration cards for residents/staff
    """

    def apply_method(self, r, **attr):
        """
            Entry point for the CRUDController

            Args:
                r: the CRUDRequest
                attr: controller parameters
        """

        # Must be person+identity
        resource, component = r.resource, r.component
        if resource.tablename != "pr_person" or \
           not component or component.tablename != "pr_identity":
            r.error(400, current.ERROR.BAD_METHOD)

        # Context (person) record is required
        if not r.record:
            r.error(400, current.ERROR.BAD_METHOD)

        output = None
        if r.interactive:
            # ID document generation
            if r.http in ("GET", "POST"):
                output = self.generate(r, **attr)
            else:
                r.error(405, current.ERROR.BAD_METHOD)
        elif r.representation == "pdf":
            # ID document download
            if r.http == "GET":
                output = self.download(r, **attr)
            else:
                r.error(405, current.ERROR.BAD_METHOD)
        else:
            r.error(415, current.ERROR.BAD_FORMAT)

        return output

    # -------------------------------------------------------------------------
    def generate(self, r, **attr):
        """
            Dialog to create a new registration card

            Args:
                r: the CRUDRequest
                attr: controller parameters
        """

        # User must have permission to create identity records
        if not current.auth.s3_has_permission("create", "pr_identity"):
            r.unauthorised()

        T = current.T

        s3db = current.s3db

        resource = r.resource
        record = r.record
        person_id = record.id

        request = current.request
        response = current.response
        s3 = response.s3

        # Available Formats
        card_formats = (("A4", T("A4")),
                        ("CCL", "%s (%s)" % (T("Credit Card"), T("Landscape##format"))),
                        ("CCP", "%s (%s)" % (T("Credit Card"), T("Portrait##format"))),
                        )

        # Form fields
        #now = request.utcnow.date()
        formfields = [Field("fmt",
                            requires = IS_IN_SET(card_formats, zero=None),
                            default = "A4",
                            label = T("Format"),
                            ),
                      DateField("valid_until",
                                label = T("Valid Until"),
                                #default = now + relativedelta(months=1, day=31),
                                month_selector = True,
                                past = 0,
                                #empty = False,
                                ),
                      Field("confirm", "boolean",
                            requires = lambda v: (v, None) if v else (v, T("You must confirm the action")),
                            default = False,
                            label = T("Yes, generate a new registration card"),
                            ),
                      ]

        if r.controller == "dvr" and person_id:
            case = s3db.dvr_get_case(person_id, archived=None)
            tag_value_default = case.reference if case else None
            formfields[1:1] = [Field('tag_option', 'boolean',
                                     default = False,
                                     label = T("Print Ref.No.##fileref"),
                                     ),
                               Field('tag_value',
                                     default = tag_value_default,
                                     label = T("Ref.No.##fileref"),
                                     ),
                               ]

        # Generate labels (and mark required fields in the process)
        labels, has_required = s3_mark_required(formfields)
        s3.has_required = has_required

        # Form buttons
        REGISTER = T("Generate registration card")
        buttons = [BUTTON(REGISTER,
                          _type = "submit",
                          _class = "small primary button",
                          ),
                   A(T("Cancel"),
                     _href = r.url(method=""),
                     _class = "cancel-form-btn action-lnk",
                     ),
                   ]

        # Construct the form
        settings = current.deployment_settings
        auth = current.auth
        response.form_label_separator = ""
        form = SQLFORM.factory(table_name = "generate_id",
                               record = None,
                               hidden = {"_next": request.vars._next},
                               labels = labels,
                               separator = "",
                               showid = False,
                               submit_button = REGISTER,
                               delete_label = auth.messages.delete_label,
                               formstyle = settings.get_ui_formstyle(),
                               buttons = buttons,
                               *formfields)

        if form.accepts(r.post_vars,
                        current.session,
                        formname = "generate_id_card[%s]" % person_id,
                        keepvalues = False,
                        hideerror = False
                        ):

            form_vars = form.vars

            # Choose layout depending on controller and format selection
            fmt = form_vars.get("fmt")
            if r.controller == "hrm":
                if fmt == "CCL":
                    layout = StaffIDCardLayoutL
                elif fmt == "CCP":
                    layout = StaffIDCardLayoutP
                else:
                    layout = StaffIDCardLayoutA4
            else:
                if fmt == "CCL":
                    layout = IDCardLayoutL
                elif fmt == "CCP":
                    layout = IDCardLayoutP
                else:
                    layout = IDCardLayoutA4

            # Print tag?
            tag = form_vars.get("tag_value") if form_vars.get("tag_option") else None

            # Initialize ID card
            valid_until = form_vars.get("valid_until")
            idcard = IDCard(person_id,
                            valid_until = valid_until if valid_until else None,
                            extra_data = {"tag": tag.strip() if tag else None},
                            )

            # Generate PDF document (with registration callback)
            resource.configure(id_card_callback = idcard.register)
            from core import DataExporter
            document = DataExporter.pdfcard(resource, layout=layout)
            resource.clear_config("id_card_callback")

            identity_id = idcard.identity_id
            if not identity_id:
                r.error(503, "ID Registration failed", next=r.url())

            # Store the PDF document
            dtable = s3db.pr_identity_document
            entry = {"identity_id": idcard.identity_id,
                     "file": dtable.file.store(document, filename="%s_card_%s.pdf" % (resource.name, person_id)),
                     }
            entry_id = dtable.insert(**entry) # TODO postprocess create?

            # Invalidate previously generated IDs
            if entry_id:
                IDCard.invalidate_ids(person_id, keep=idcard.identity_id)

            current.response.confirmation = T("New registration card registered")
            form = self.card_details(r, idcard)
        else:
            itable = s3db.pr_image
            query = (itable.pe_id == record.pe_id) & \
                    (itable.profile == True) & \
                    (itable.deleted == False)
            rows = current.db(query).select(itable.id, limitby=(0, 1)).first()
            if not rows:
                current.response.warning = T("No profile picture available for this person")

            warning = T("All previous registration cards for this person will become invalid by this action!")
            form = DIV(DIV(warning, _class="id-card-warning"), form)

        output = {"form": form,
                  "title": T("Registration Cards"),
                  "subtitle": T("Generate registration card"),
                  }
        current.response.view = self._view(r, "update.html")

        return output

    # -------------------------------------------------------------------------
    @staticmethod
    def card_details(r, idcard):
        """
            Displays the details of the new registration card, and offers
            a button to download the PDF

            Args:
                r: the CRUDRequest
                idcard: the IDCard

            Returns:
                a DIV with contents
        """

        T = current.T

        db = current.db
        s3db = current.s3db

        # Look up the identity record
        itable = s3db.pr_identity
        identity_id = idcard.identity_id
        identity = db(itable.id == identity_id).select(itable.value,
                                                       limitby = (0, 1),
                                                       ).first()

        # Download button
        download = A(ICON("file-pdf"), T("Download PDF"),
                     data = {"url": r.url(component_id = idcard.identity_id,
                                          method = "generate",
                                          representation = "pdf",
                                          ),
                             },
                     _class = "small primary button s3-download-button",
                     )

        # Link to list
        to_list = A(T("List Identity Documents"),
                    _href = r.url(method=""),
                    _class = "action-lnk",
                    )

        return DIV(DIV(H5(identity.value), download, _class="id-card-data"),
                   DIV(to_list),
                   )

    # -------------------------------------------------------------------------
    @staticmethod
    def download(r, **attr):
        """
            Downloads the PDF for an ID card

            Args:
                r: the CRUDRequest
                attr: controller parameters
        """

        # Request must specify a particular identity record
        component_id = r.component_id
        if not component_id:
            r.error(400, current.ERROR.BAD_METHOD)

        # User must have permission to read this particular identity record
        if not current.auth.s3_has_permission("read", "pr_identity", record_id=component_id):
            r.unauthorised()

        output = None

        db = current.db
        s3db = current.s3db

        itable = s3db.pr_identity
        dtable = s3db.pr_identity_document

        join = itable.on((itable.id == dtable.identity_id) & \
                         (itable.person_id == r.record.id) & \
                         (itable.id == r.component_id) & \
                         (itable.deleted == False))
        query = (dtable.file != None) & (dtable.deleted == False)
        row = db(query).select(dtable.id,
                               dtable.file,
                               join = join,
                               limitby = (0, 1),
                               orderby = ~dtable.id,
                               ).first()

        if row:
            filename, stream = dtable.file.retrieve(row.file)

            # Add file name and content headers
            response = current.response
            disposition = "attachment; filename=\"%s\"" % filename
            response.headers["Content-Type"] = contenttype(".pdf")
            response.headers["Content-disposition"] = disposition

            output = stream
        else:
            r.error(404, current.ERROR.BAD_RECORD)

        return output

# =============================================================================
class IDCard:
    """ Toolkit for registered, system-generated ID cards """

    def __init__(self, person_id, valid_until=None, extra_data=None):
        # TODO docstring

        self.person_id = person_id
        self.valid_until = valid_until
        self.extra_data = extra_data

        # Will be set during register()
        self.identity_id = None

    # -------------------------------------------------------------------------
    def register(self, item):
        """
            Registers a system-generated ID card; as draw-callback for
            IDCardLayout (i.e. called per ID)

            Args:
                item: the data item (a dict containing the person details)

            Returns:
                the item updated with an additional attribute "_req":
                a dict {"token": the document verification token,
                        "vhash": the record verification hash,
                        "vcode": a human-readable verification signature of the hash,
                        }
                - these data are to be embedded in the PDF (e.g. the QRCode)
        """

        db = current.db

        s3db = current.s3db
        auth = current.auth

        # Check for existing registration details
        registration = item.get("_reg")
        if registration and \
           all(registration.get(k) for k in ("token", "vhash", "vcode")):
            # Already processed
            return item

        # Validate the person ID in the item
        person_id = item["_row"]["pr_person.id"]
        if person_id != self.person_id:
            return item

        # Look up the PE label and the person record UID
        ptable = s3db.pr_person
        query = (ptable.id == person_id)
        person = db(query).select(ptable.id,
                                  ptable.uuid,
                                  ptable.pe_label,
                                  ptable.pe_id,
                                  limitby = (0, 1),
                                  ).first()
        if not person:
            return item

        # Get the hex representation of the person UID
        person_uuid = person.uuid
        try:
            # Decode the person UID
            person_uuid = uuid.UUID(person_uuid).hex.upper()
        except ValueError:
            pass

        # Get the pe_label
        pe_label = person.pe_label

        # Produce the ID card token to uniquely identify the PDF
        # - will be embedded in the PDF, but not stored anywhere else
        token = secrets.token_hex(16).upper()

        # Produce the verification hash for the ID record
        # - from pe_label, ID card token and person UID
        # - matches only the PDF with the correct label and token
        record_vhash = self.generate_vhash(pe_label, person_uuid, token)

        # Produce the UID for the ID record
        record_uid = uuid.uuid4()

        # Generate the verification hash for the ID card
        # - from pe_label, identity record UUID, and record verification hash
        # - matches only this particular identity record
        card_vhash = self.generate_chash(pe_label, record_uid.hex.upper(), record_vhash)

        # Generate the card hash signature
        # - a human-readable signature for reverse verification
        # - useful in situations where the QR-code cannot be scanned
        check = self._signature(card_vhash)

        # Generate or update ID record (=register the ID card)
        itable = s3db.pr_identity
        id_data = {"uuid": record_uid.urn,
                   "person_id": person.id,
                   "value": "%s-%s" % (pe_label, check),
                   "type": 98,
                   "system": True,
                   "invalid": False,
                   "valid_from": current.request.utcnow.date(),
                   "valid_until": self.valid_until,
                   "vhash": record_vhash,
                   }
        self.identity_id = id_data["id"] = itable.insert(**id_data)

        # Postprocess create
        s3db.update_super(itable, id_data)
        auth.s3_set_record_owner(itable, id_data)
        s3db.onaccept(itable, id_data, method="create")

        # Update and return the item
        item["_reg"] = {"token": token,
                        "vhash": card_vhash,
                        "vcode": check,
                        }
        item["_ext"] = self.extra_data

        return item

    # -------------------------------------------------------------------------
    @staticmethod
    def invalidate_ids(person_id, keep=None, expire_only=False):
        """
            Invalidates all system-generated IDs for a person

            Args:
                person_id: the person record ID
                keep: the ID of one identity record to keep
        """

        db = current.db
        s3db = current.s3db

        itable = s3db.pr_identity
        dtable = s3db.pr_identity_document

        query = (itable.person_id == person_id)
        if keep:
            query &= (itable.id != keep)
        query &= (itable.system == True) & \
                 (itable.invalid == False) & \
                 (itable.deleted == False)
        rows = db(query).select(itable.id, itable.valid_until)
        today = current.request.utcnow.date()
        for row in rows:
            # Remove all stored PDF documents for this identity
            db(dtable.identity_id == row.id).update(file=None)

            # Mark the identity record as invalid
            update = {} if expire_only else {"invalid": True}
            if not row.valid_until or row.valid_until > today:
                update["valid_until"] = today
            if update:
                row.update_record(**update)
                s3db.onaccept(itable, row, method="update")

    # -------------------------------------------------------------------------
    @staticmethod
    def generate_vhash(label, uid, token):
        """
            Generates the server-side verification hash for the ID Card; to
            be stored in the identity record

            Args:
                label: the PE label
                uid: the UUID (hex) of the person record
                token: a random token embedded in the PDF (and only there)

            Returns:
                the hash as uppercase hexadecimal
        """

        s = "##".join((label, token, uid))
        return hashlib.sha512(s.encode("ascii")).hexdigest().upper()

    # -------------------------------------------------------------------------
    @staticmethod
    def generate_chash(label, uid, vhash):
        """
            Generates the document-side verification hash for the ID Card; to
            be embedded in the PDF

            Args:
                label: the PE label
                uid: the UUID (hex) of the identity record
                vhash: the server-side verification hash

            Returns:
                the hash as uppercase hexadecimal
        """

        s = "##".join((label, uid, vhash))
        return hashlib.sha256(s.encode("ascii")).hexdigest().upper()

    # -------------------------------------------------------------------------
    @classmethod
    def get_id_signature(cls, pe_label):
        """
            Produces a human-readable signature for the card hash of the
            currently valid registration card of a person; for reverse
            verification in situations where the QR code cannot be scanned

            Args:
                pe_label: the ID label of the person

            Returns:
                the signature (hex code)
        """

        db = current.db
        s3db = current.s3db

        # Find the relevant identity record
        itable = s3db.pr_identity
        ptable = s3db.pr_person

        today = current.request.utcnow.date()
        join = ptable.on((ptable.id == itable.person_id) & \
                         (ptable.pe_label == pe_label) & \
                         (ptable.deleted == False))
        query = (itable.system == True) & \
                (itable.invalid == False) & \
                ((itable.valid_until == None) | (itable.valid_until >= today)) & \
                (itable.vhash != None)
        row = db(query).select(ptable.pe_label,
                               itable.type,
                               itable.uuid,
                               itable.vhash,
                               join = join,
                               limitby = (0, 1),
                               ).first()

        # Compute the card hash
        card_hash = None
        pick = False
        if row:
            pe_label = row.pr_person.pe_label
            record = row.pr_identity
            try:
                uid = uuid.UUID(record.uuid).hex.upper()
            except ValueError:
                pass
            else:
                card_hash = cls.generate_chash(pe_label, uid, record.vhash)
            if record.type == 999:
                pick = True

        # TODO consider pair-formatting:
        # " ".join([s[i:i+2] for i in range(0, len(s), 2)])
        return cls._signature(card_hash, pick=pick) if card_hash else None

    # -------------------------------------------------------------------------
    @staticmethod
    def _signature(vhash, pick=False):
        """
            Generates a signature for a verification hash

            Args:
                vhash: the verification hash (hex)
                pick: pick pairs from the original hash (recoverable)

            Returns:
                the signature (hex code)
        """

        if pick:
            # Pick pairs from the original hash
            d = len(vhash) // 8
            marks = [vhash[d*i:d*i+2] for i in range(d)]
            return "".join(vhash[int(m, 16) % len(vhash)] for m in marks)

        # Use MD5 hash of the verification hash as fingerprint
        return hashlib.md5(vhash.encode("utf-8")).hexdigest().upper()[:8]

    # -------------------------------------------------------------------------
    @classmethod
    def identify(cls, label, verify=True):
        """
            Identifies the person from any of the registration codes
            on an ID card (=ID label, barcode or QR code)

            Args:
                label: the registration code from the ID card
                verify: verify the label, if possible

            Returns:
                a tuple (person_id, verify)
                - verify-flag indicates whether the code has been verified

            Raises:
                - SyntaxError if the code is malformed
                - ValueError if the verification failed
        """

        db = current.db
        s3db = current.s3db

        data = label.strip().split("##") if label else None
        if not data:
            raise SyntaxError("No data for identification")
        if len(data) == 3:
            label, token, chash = data
        else:
            label, token, chash = data[0], None, None
            verify = False

        # Find the person record
        ptable = s3db.pr_person
        query = (ptable.pe_label == label) & (ptable.deleted == False)
        person = db(query).select(ptable.id,
                                  ptable.uuid,
                                  ptable.pe_label,
                                  limitby = (0, 1),
                                  ).first()
        if not person:
            # Label does not match any registered person
            return None, False

        if verify:
            cls._verify(person, token, chash)

        return person.id, verify

    # -------------------------------------------------------------------------
    @classmethod
    def _verify(cls, person, token, chash):
        """
            Verifies the registration code (Qr code) from an ID card

            Args:
                person: the person identified by the code
                token: the verification token from the code
                hash: the verification hash from the code

            Raises:
                - SyntaxError if token or hash are missing
                - ValueError if the code is invalid
        """

        db = current.db
        s3db = current.s3db

        if not token or not hash:
            raise SyntaxError("Insufficient data for ID verification")

        # Compute ID record verification hash
        try:
            uid = uuid.UUID(person.uuid).hex.upper()
        except ValueError:
            uid = person.uuid
        vhash = cls.generate_vhash(person.pe_label, uid, token)

        # Find a valid system ID record for this person that matches the vhash
        today = current.request.utcnow.date()
        itable = s3db.pr_identity
        query = (itable.person_id == person.id) & \
                (itable.vhash == vhash) & \
                (itable.system == True) & \
                (itable.invalid == False) & \
                ((itable.valid_until == None) | (itable.valid_until >= today)) & \
                (itable.deleted == False)
        rows = db(query).select(itable.id,
                                itable.uuid,
                                itable.vhash,
                                limitby = (0, 2),
                                )
        if len(rows) != 1:
            raise ValueError("ID record not found")
        record = rows.first()

        # Compute the ID card verification hash
        try:
            uid = uuid.UUID(record.uuid).hex.upper()
        except ValueError as e:
            # Malformed ID record UID (invalid ID record)
            raise ValueError("Invalid ID record") from e
        chash_v = cls.generate_chash(person.pe_label, uid, vhash)

        if chash_v != chash:
            # ID card verification hash does not match the ID record
            raise ValueError("Verification hash mismatch")

        return person.id

    # -------------------------------------------------------------------------
    def auto_expire(self):
        """
            Auto-expires all ID cards unless holder is still registered
            at a shelter, or an active staff member
        """

        db = current.db
        s3db = current.s3db

        person_id = self.person_id

        rtable = s3db.cr_shelter_registration
        query = (rtable.person_id == person_id) & \
                (rtable.shelter_id != None) & \
                (rtable.registration_status != 3) & \
                (rtable.deleted == False)
        row = db(query).select(rtable.id, limitby=(0, 1)).first()
        if row:
            # ...still planned or checked-in to a shelter
            return

        htable = s3db.hrm_human_resource
        query = (htable.person_id == person_id) & \
                (htable.organisation_id != None) & \
                (htable.status == 1) & \
                (htable.deleted == False)
        row = db(query).select(htable.id, limitby=(0, 1)).first()
        if row:
            # ...still an active staff member
            return

        self.invalidate_ids(person_id, expire_only=True)

# =============================================================================
class IDCardLayoutL(PDFCardLayout):
    """
        Layout for printable beneficiary ID cards
    """

    cardsize = CCLS
    orientation = "Landscape"
    doublesided = True

    border_color = HexColor(0x6084bf)

    # -------------------------------------------------------------------------
    @classmethod
    def fields(cls, resource):
        """
            The layout-specific list of fields to look up from the resource

            Args:
                resource: the resource

            Returns:
                list of field selectors
        """

        return ["id",
                "pe_id",
                "pe_label",
                "first_name",
                #"middle_name",
                "last_name",
                "date_of_birth",
                "dvr_case.organisation_id$root_organisation",
                "shelter_registration.shelter_id",
                "shelter_registration.shelter_unit_id",
                "shelter_registration.shelter_id$location_id$L2",
                "shelter_registration.shelter_id$location_id$L3",
                "shelter_registration.shelter_id$location_id$L4",
                "shelter_registration.shelter_id$location_id$addr_postcode",
                "shelter_registration.shelter_id$location_id$addr_street",
                ]

    # -------------------------------------------------------------------------
    @classmethod
    def lookup(cls, resource, items):
        """
            Looks up layout-specific common data for all cards

            Args:
                resource: the resource
                items: the items

            Returns:
                a dict with common data
        """

        db = current.db
        s3db = current.s3db

        defaultpath = os.path.join(current.request.folder, 'uploads')

        # Get all root organisations
        root_orgs = set(item["_row"]["org_organisation.root_organisation"] for item in items)

        # Look up all logos
        otable = s3db.org_organisation
        query = (otable.id.belongs(root_orgs))
        rows = db(query).select(otable.id, otable.name, otable.logo)

        field = otable.logo
        path = field.uploadfolder if field.uploadfolder else defaultpath
        logos = {row.id: os.path.join(path, row.logo) for row in rows if row.logo}

        # Get root organisation names
        ctable = s3db.dvr_case
        represent = ctable.organisation_id.represent
        if represent.bulk:
            root_org_names = represent.bulk(list(root_orgs), show_link=False)
        else:
            root_org_names = None

        # Get all PE IDs
        pe_ids = set(item["_row"]["pr_person.pe_id"] for item in items)

        # Look up all profile pictures
        itable = s3db.pr_image
        query = (itable.pe_id.belongs(pe_ids)) & \
                (itable.profile == True) & \
                (itable.deleted == False)
        rows = db(query).select(itable.pe_id, itable.image)

        field = itable.image
        path = field.uploadfolder if field.uploadfolder else defaultpath
        pictures = {row.pe_id: os.path.join(path, row.image) for row in rows if row.image}

        return {"pictures": pictures,
                "root_org_names": root_org_names,
                "logos": logos,
                }

    # -------------------------------------------------------------------------
    def draw(self):
        """
            Draws the card (one side), to be implemented by subclass

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

            Note:
                Canvas coordinates are relative to the lower left corner of the
                card's frame, drawing must not overshoot self.width/self.height
        """

        item = self.item

        # Invoke draw callback
        callback = self.resource.get_config("id_card_callback")
        if callable(callback):
            callback(item)

        # Enforce current default language
        T = current.T
        default_language = current.deployment_settings.get_L10n_default_language()
        if default_language:
            translate = lambda s: T(s, language=default_language)
        else:
            translate = T

        # Draw contents
        self.draw_base_layout(item, translate)
        if self.backside:
            self.draw_shelter_details(item, translate)
        else:
            self.draw_organisation_details(item, translate)
            self.draw_person_details(item, translate)
        self.draw_registration_details(item, translate)

    # -------------------------------------------------------------------------
    def draw_base_layout(self, item, t_):
        """
            Draws the basic layout elements:
                - document title
                - border decorations
                - validity advice

            Args:
                item: the data item
                t_: the translator
        """

        w = self.width
        h = self.height

        draw_string = self.draw_string
        if self.backside:
            # Advice
            advice = "Kein Identitätsnachweis! Nur gültig in Verbindung mit dem digitalen Register."
            draw_string(4, 12, advice, width=w-8, size=6.5, halign="center")
        else:
            # Document Title
            title = "Registrierungskarte"
            draw_string(60, h-40, title, width=w-68, height=10, size=10, bold=True, halign="center")

        # Border
        self.draw_border()

    # -------------------------------------------------------------------------
    def draw_organisation_details(self, item, t_):
        """
            Draws the organisation details:
                - logo
                - organisation name

            Args:
                item: the data item
                t_: the translator
        """

        w = self.width
        h = self.height

        raw = item["_row"]
        common = self.common

        # Get the root organisation ID
        root_org = raw["org_organisation.root_organisation"]

        # Get the organisation logo
        logos = common.get("logos")
        logo = logos.get(root_org) if logos else None
        if not logo:
            logo = self.get_default_org_logo()

        # Get the localized root org name
        org_names = common.get("root_org_names")
        root_org_name = org_names.get(root_org) if org_names else None

        # Logo
        if logo:
            self.draw_image(logo, 30, h-30, width=40, height=40, halign="center", valign="middle")

        # Organisation Name
        if root_org_name:
            self.draw_string(60, h-25, root_org_name, width=w-70, height=14, size=8, bold=True, halign="center")

    # -------------------------------------------------------------------------
    def draw_shelter_details(self, item, t_):
        """
            Draws the shelter details:
                - shelter name
                - shelter address

            Args:
                item: the data item
                t_: the translator
        """

        w = self.width
        h = self.height

        raw = item["_row"]

        draw_string = self.draw_string

        # Start position
        x, y = 10, h-16
        wt = w - x*2 # text width

        # Shelter
        shelter_id = raw["cr_shelter_registration.shelter_id"]
        if shelter_id:

            # Shelter Name
            shelter = item["cr_shelter_registration.shelter_id"]
            draw_string(x, y, shelter, width=wt, height=12, size=9, halign="center")

            # Shelter address
            address = None
            location = raw["gis_location.L4"] or raw["gis_location.L3"]
            if location:
                address = item["gis_location.addr_street"]
                postcode = item["gis_location.addr_postcode"]
                place = "%s %s" % (postcode, location) if postcode else location
                if address and place:
                    address = ", ".join((address, place))
                elif place:
                    address = place

            if address:
                draw_string(x, y-9, address, width=wt, height=8, size=7, halign="center")

    # -------------------------------------------------------------------------
    def draw_person_details(self, item, t_):
        """
            Draws the person details:
                - full name
                - date of birth
                - shelter unit name, if available
                - picture

            Args:
                item: the data item
                t_: the translator
        """

        w = self.width

        raw = item["_row"]
        common = self.common
        extra_data = item.get("_ext")

        draw_string = self.draw_string

        # Start position
        x, y = 12, 82
        wt = w - (x + 70) # text width

        # Name
        name = s3_format_fullname(fname = raw["pr_person.first_name"],
                                  lname = raw["pr_person.last_name"],
                                  truncate = False,
                                  )
        draw_string(x, y, name, width=wt, height=12, size=12)

        # Date of birth
        y = y - 18
        dob = raw["pr_person.date_of_birth"]
        if dob:
            dob = item["pr_person.date_of_birth"]
            draw_string(x, y + 8, t_("Date of Birth"), size=5)
            draw_string(x, y, dob, width=wt, height=9, size=8)

        # Reference Number (=tag)
        y = y - 17
        tag = extra_data.get("tag") if extra_data else None
        if tag:
            draw_string(x, y + 8, t_("Ref.No.##fileref"), size=5)
            draw_string(x, y, tag, width=wt, height=9, size=8)

        # Shelter Unit
        # TODO do not draw if transitory unit?
        y = y - 17
        unit = raw["cr_shelter_registration.shelter_unit_id"]
        if unit:
            unit = item["cr_shelter_registration.shelter_unit_id"]
            draw_string(x, y + 8, t_("Housing Unit"), size=5)
            draw_string(x, y, unit, width=wt, height=9, size=8)

        # Profile picture
        pictures = common.get("pictures")
        picture = pictures.get(raw["pr_person.pe_id"]) if pictures else None
        if picture:
            self.draw_image(picture,
                            w - 16, 32, height=60, width=60,
                            halign = "right",
                            valign = "bottom",
                            )

    # -------------------------------------------------------------------------
    def draw_registration_details(self, item, t_):
        """
            Draws the registration details:
                - ID label and barcode
                - QR code and signature

            Args:
                item: the data item
                t_: the translator
        """

        h = self.height
        w = self.width

        raw = item["_row"]

        code = raw["pr_person.pe_label"]
        if not code:
            code = "XXXXXXX"

        if self.backside:
            # QR-Code and Hash Signature
            registration = item.get("_reg")
            if not registration or \
               not all(registration.get(d) for d in ("token", "vhash", "vcode")):
                vcode = "%s##UNVERIFIED##UNREGISTERED" % code
                signature = None
            else:
                vcode = "##".join(map(s3_str, (code, registration["token"], registration["vhash"])))
                signature = registration["vcode"]

            if vcode:
                self.draw_qrcode(vcode,
                                 w * 1/2,
                                 h * 1/2 + 5,
                                 size = 96,
                                 halign = "center",
                                 valign = "middle",
                                 level = "M",
                                 )
            if signature:
                self.draw_string(20, h * 1/2 - 50, signature,
                                 size = 6.5,
                                 bold = False,
                                 width = w-40,
                                 halign = "center",
                                 )

        else:
            # ID Number and barcode
            self.draw_string(12, 12, s3_str(code), width=w/2-16, size=12, bold=True)
            self.draw_barcode(s3_str(code), w-6, 12, height=12, halign="right", maxwidth=w/2-16)

    # -------------------------------------------------------------------------
    def draw_border(self):
        """
            Draws the border decorations
        """

        c = self.canv
        c.saveState()

        w = self.width
        h = self.height

        c.setFillColor(self.border_color)

        # Horizontal bar bottom
        c.rect(0, 0, w, 8, fill=1, stroke=0)

        # Vertical bar right
        if not self.backside:
            c.rect(w-8, 8, w, h, fill=1, stroke=0)

        c.restoreState()

    # -------------------------------------------------------------------------
    def draw_string(self, x, y, value, *, width=120, height=40, size=7, bold=False, halign=None, box=False):
        """
            Draws a string

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

    # -------------------------------------------------------------------------
    def draw_vertical_string(self, x, y, value, *, width=120, height=40, size=7, bold=False, halign=None, box=False):
        """
            Draws a vertical string

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

        c = self.canv
        c.saveState()
        c.rotate(90)

        result = self.draw_value(x + width/2.0,
                                 y - self.width,
                                 value,
                                 width = width,
                                 height = height,
                                 size = size,
                                 bold = bold,
                                 halign = halign,
                                 box = box,
                                 )

        c.restoreState()
        return result

    # -------------------------------------------------------------------------
    def draw_value(self, x, y, value, *, width=120, height=40, size=7, bold=True, valign=None, halign=None, box=False):
        """
            Helper function to draw a centered text above position (x, y);
            allows the text to wrap if it would otherwise exceed the given
            width

            Args:
                x: drawing position
                y: drawing position
                value: the text to render
                width: the maximum available width (points)
                height: the maximum available height (points)
                size: the font size (points)
                bold: use bold font
                valign: vertical alignment ("top"|"middle"|"bottom"),
                        default "bottom"
                halign: horizontal alignment ("left"|"center")

            Returns:
                the actual height of the text element drawn
        """

        # Preserve line breaks by replacing them with <br/> tags
        value = s3_str(value).strip("\n").replace('\n','<br />\n')

        stylesheet = getSampleStyleSheet()
        style = stylesheet["Normal"]
        style.fontName = BOLD if bold else NORMAL
        style.fontSize = size
        style.leading = size + 2
        style.splitLongWords = False
        style.alignment = TA_CENTER if halign=="center" else \
                          TA_RIGHT if halign == "right" else TA_LEFT

        if box:
            style.borderWidth = 0.5
            style.borderPadding = 3
            style.borderColor = Color(0, 0, 0)
            style.backColor = Color(0.7, 0.7, 0.7)

        para = Paragraph(value, style)
        aw, ah = para.wrap(width, height)

        while((ah > height or aw > width) and style.fontSize > 4):
            # Reduce font size to make fit
            style.fontSize -= 1
            style.leading = style.fontSize + 2
            para = Paragraph(value, style)
            aw, ah = para.wrap(width, height)

        v = value
        while((ah > height or aw > width) and len(v) > 4):
            # Truncate to make fit
            v = v[:-1]
            para = Paragraph(v, style)
            aw, ah = para.wrap(width, height)

        if valign == "top":
            vshift = ah
        elif valign == "middle":
            vshift = ah / 2.0
        else:
            vshift = 0

        para.drawOn(self.canv, x - para.width / 2, y - vshift)

        return ah

    # -------------------------------------------------------------------------
    @staticmethod
    def get_default_org_logo():
        """
            Returns the default organisation logo for ID cards
        """

        path = current.deployment_settings.get_custom("idcard_default_logo")

        return os.path.join(current.request.folder, "static", "themes", *path) \
               if path else None

# =============================================================================
class IDCardLayoutP(IDCardLayoutL):
    """
        Layout for printable beneficiary ID cards
    """

    cardsize = CREDITCARD
    orientation = "Portrait"
    doublesided = True

    border_color = HexColor(0x6084bf)

    # -------------------------------------------------------------------------
    def draw_base_layout(self, item, t_):
        """
            Draws the basic layout elements:
                - document title
                - border decorations
                - validity advice

            Args:
                item: the data item
                t_: the translator
        """

        w = self.width
        h = self.height

        if self.backside:
            # Advice
            advice = "Kein Identitätsnachweis! Nur gültig in Verbindung mit dem digitalen Register."
            self.draw_string(8, 12, advice, width=w-16, height=20, size=6, halign="center")
        else:
            # Document Title
            title = "Registrierungskarte"
            self.draw_string(12, h-80, title, width=w-24, height=10, size=10, bold=True, halign="center")

        # Border
        self.draw_border()

    # -------------------------------------------------------------------------
    def draw_organisation_details(self, item, t_):
        """
            Draws the organisation details:
                - logo
                - organisation name

            Args:
                item: the data item
                t_: the translator
        """

        w = self.width
        h = self.height

        raw = item["_row"]
        common = self.common

        # Get the root organisation ID
        root_org = raw["org_organisation.root_organisation"]

        # Get the organisation logo
        logos = common.get("logos")
        logo = logos.get(root_org) if logos else None
        if not logo:
            logo = self.get_default_org_logo()

        # Get the localized root org name
        org_names = common.get("root_org_names")
        root_org_name = org_names.get(root_org) if org_names else None

        # Logo
        if logo:
            self.draw_image(logo, w//2, h-30, width=40, height=40, halign="center", valign="middle")

        # Organisation Name
        if root_org_name:
            self.draw_string(10, h-65, root_org_name, width=w-20, height=14, size=8, bold=True, halign="center")

    # -------------------------------------------------------------------------
    def draw_shelter_details(self, item, t_):
        """
            Draws the shelter details:
                - shelter name
                - shelter address

            Args:
                item: the data item
                t_: the translator
        """

        w = self.width
        h = self.height

        raw = item["_row"]

        draw_string = self.draw_string

        # Start position
        x, y = 8, h-20
        wt = w - x*2 # text width

        # Shelter
        shelter_id = raw["cr_shelter_registration.shelter_id"]
        if shelter_id:

            # Shelter Name
            shelter = item["cr_shelter_registration.shelter_id"]
            draw_string(x, y, shelter, width=wt, height=16, size=9, halign="center")

            # Shelter address
            address = place = None
            location = raw["gis_location.L4"] or raw["gis_location.L3"]
            if location:
                address = item["gis_location.addr_street"]
                postcode = item["gis_location.addr_postcode"]
                place = "%s %s" % (postcode, location) if postcode else location
            if address:
                y -= 9
                draw_string(x, y, address, width=wt, height=8, size=7, halign="center")
            if place:
                y -= 9
                draw_string(x, y, place, width=wt, height=8, size=7, halign="center")

    # -------------------------------------------------------------------------
    def draw_person_details(self, item, t_):
        """
            Draws the person details:
                - full name
                - date of birth
                - shelter unit name, if available
                - picture

            Args:
                item: the data item
                t_: the translator
        """

        h = self.height
        w = self.width

        raw = item["_row"]
        common = self.common
        extra_data = item.get("_ext")

        draw_string = self.draw_string

        x, y = 18, 82
        wt = w-2*x # text width

        # Name
        name = s3_format_fullname(fname = raw["pr_person.first_name"],
                                  lname = raw["pr_person.last_name"],
                                  truncate = False,
                                  )
        draw_string(x, y, name, width=wt, height=12, size=12, halign="center")

        # Date of birth
        y = y - 15
        cl, cr = w * 2/5 - 2, w * 2/5 + 2
        dob = raw["pr_person.date_of_birth"]
        if dob:
            dob = item["pr_person.date_of_birth"]
            # draw_string(x, y + 8, t_("Date of Birth"), size=5, halign="center")
            # draw_string(x, y, dob, width=wt, height=9, size=8, halign="center")
            draw_string(0, y, t_("Date of Birth"), width=cl, size=5, halign="right")
            draw_string(cr, y, dob, width=wt/2, height=9, size=8, halign="left")

        # Reference Number (=tag)
        y = y - 10
        tag = extra_data.get("tag") if extra_data else None
        if tag:
            draw_string(0, y, t_("Ref.No.##fileref"), width=cl, size=5, halign="right")
            draw_string(cr, y, tag, width=wt/2, height=9, size=8, halign="left")

        # Shelter Unit
        # TODO do not draw if transitory unit?
        y = y - 10
        unit = raw["cr_shelter_registration.shelter_unit_id"]
        if unit:
            unit = item["cr_shelter_registration.shelter_unit_id"]
            draw_string(0, y, t_("Housing Unit"), width=cl, size=5, halign="right")
            draw_string(cr, y, unit, width=wt/2, height=9, size=8, halign="left")

        # Profile picture
        pictures = common.get("pictures")
        picture = pictures.get(raw["pr_person.pe_id"]) if pictures else None
        if picture:
            self.draw_image(picture,
                            w * 1/2, h * 1/2 + 6, height=60, width=60,
                            halign = "center",
                            valign = "middle",
                            )

    # -------------------------------------------------------------------------
    def draw_registration_details(self, item, t_):
        """
            Draws the registration details:
                - ID label and barcode
                - QR code and signature

            Args:
                item: the data item
                t_: the translator
        """

        h = self.height
        w = self.width

        raw = item["_row"]
        code = raw["pr_person.pe_label"]
        if not code:
            code = "XXXXXXX"

        if self.backside:
            # QR-Code and Hash Signature
            registration = item.get("_reg")
            if not registration or \
               not all(registration.get(d) for d in ("token", "vhash", "vcode")):
                vcode = "%s##UNVERIFIED##UNREGISTERED" % code
                signature = None
            else:
                vcode = "##".join(map(s3_str, (code, registration["token"], registration["vhash"])))
                signature = registration["vcode"]

            if vcode:
                self.draw_qrcode(vcode,
                                 w * 1/2,
                                 h * 1/2,
                                 size = 96,
                                 halign = "center",
                                 valign = "middle",
                                 level = "M",
                                 )
            if signature:
                self.draw_string(20, h * 1/2 + 48, signature,
                                 size = 6.5,
                                 bold = False,
                                 width = w-40,
                                 halign = "center",
                                 )
        else:
            # ID Number and barcode
            y = 24
            self.draw_string(10, y, s3_str(code), width=w-20, size=12, bold=True, halign="center")
            self.draw_barcode(s3_str(code), w / 2, y - 14, height=12, halign="center", maxwidth=w-40)

# =============================================================================
class IDCardLayoutA4(IDCardLayoutP):
    """
        Layout for printable beneficiary ID cards
    """

    cardsize = A4
    orientation = "Portrait"
    doublesided = False

    # -------------------------------------------------------------------------
    def draw(self):
        """
            Draws the card (one side)

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

        # Enforce current default language
        T = current.T
        default_language = current.deployment_settings.get_L10n_default_language()
        if default_language:
            translate = lambda s: T(s, language=default_language)
        else:
            translate = T

        item = self.item

        # Invoke draw callback
        callback = self.resource.get_config("id_card_callback")
        if callable(callback):
            callback(item)

        if not self.backside:

            self.draw_base_layout(item, translate)
            self.draw_organisation_details(item, translate)
            self.draw_shelter_details(item, translate)
            self.draw_person_details(item, translate)
            self.draw_registration_details(item, translate)

        else:
            # No backside
            pass

    # -------------------------------------------------------------------------
    def draw_base_layout(self, item, t_):
        """
            Draws the basic layout elements:
                - document title
                - border decorations
                - validity advice

            Args:
                item: the data item
                t_: the translator
        """

        w = self.width
        h = self.height

        # Document Title
        title = "Registrierungskarte"
        self.draw_string(20, h-165, title, width=w/2-40, height=20, size=14, bold=True, halign="center")

        # Advice
        advice = "Kein Identitätsnachweis! Nur gültig in Verbindung mit dem digitalen Register."
        self.draw_vertical_string(h/2+20, 25, advice, width=h/2-50)

        # Border
        self.draw_border()

    # -------------------------------------------------------------------------
    def draw_organisation_details(self, item, t_):
        """
            Draws the organisation details:
                - logo
                - organisation name

            Args:
                item: the data item
                t_: the translator
        """

        w = self.width
        h = self.height

        raw = item["_row"]
        common = self.common

        # Get the root organisation ID
        root_org = raw["org_organisation.root_organisation"]

        # Get the localized root org name
        org_names = common.get("root_org_names")
        root_org_name = org_names.get(root_org) if org_names else None

        # Get the organisation logo
        logos = common.get("logos")
        logo = logos.get(root_org) if logos else None
        if not logo:
            logo = self.get_default_org_logo()

        # Logo
        if logo:
            self.draw_image(logo, w//4, h-80, width=80, height=80, halign="center", valign="middle")

        # Organisation Name
        if root_org_name:
            self.draw_string(20, h-140, root_org_name, width=w/2-40, height=20, size=12, bold=True, halign="center")

    # -------------------------------------------------------------------------
    def draw_person_details(self, item, t_):
        """
            Draws the person details:
                - full name
                - date of birth
                - shelter unit name, if available
                - picture

            Args:
                item: the data item
                t_: the translator
        """

        w = self.width
        h = self.height

        raw = item["_row"]
        common = self.common
        extra_data = item.get("_ext")

        draw_string = self.draw_string

        # ----- Left -----

        # Draw box around person data
        left = 30
        bottom = h/2 + 78
        self.draw_box(left, bottom, w/2-60, 165)

        x = left + 10
        y = bottom + 76
        wt = w/2 - 2*x # text width

        # Name
        name = s3_format_fullname(fname = raw["pr_person.first_name"],
                                  lname = raw["pr_person.last_name"],
                                  truncate = False,
                                  )
        draw_string(x, y + 13, t_("Name"))
        draw_string(x, y, name, width=wt, height=20, size=12, bold=True)

        # Date of birth
        y = y - 25
        dob = raw["pr_person.date_of_birth"]
        if dob:
            dob = item["pr_person.date_of_birth"]
            draw_string(x, y + 12, t_("Date of Birth"))
            draw_string(x, y, dob, size=10, width=wt)

        # Reference Number (=tag)
        y = y - 23
        tag = extra_data.get("tag") if extra_data else None
        if tag:
            draw_string(x, y + 12, t_("Ref.No.##fileref"))
            draw_string(x, y, tag, size=10, width=wt)

        # Shelter Unit
        # TODO do not draw if transitory unit?
        y = y - 23
        unit = raw["cr_shelter_registration.shelter_unit_id"]
        if unit:
            unit = item["cr_shelter_registration.shelter_unit_id"]
            draw_string(x, y + 12, t_("Housing Unit"))
            draw_string(x, y, unit, size=10, width=wt)

        # ----- Right -----

        # Profile picture
        pictures = common.get("pictures")
        picture = pictures.get(raw["pr_person.pe_id"]) if pictures else None
        if picture:
            self.draw_image(picture,
                            w * 3/4, h * 7/8, height=h/4 - 80, width=w/2 - 60,
                            halign = "center",
                            valign = "middle",
                            )

    # -------------------------------------------------------------------------
    def draw_shelter_details(self, item, t_):
        """
            Draws the shelter details:
                - shelter name
                - shelter address

            Args:
                item: the data item
                t_: the translator
        """

        w = self.width
        h = self.height

        raw = item["_row"]

        draw_string = self.draw_string

        x = 40
        y = h/2 + 215
        wt = w/2 - 2*x # text width

        # Shelter
        shelter_id = raw["cr_shelter_registration.shelter_id"]
        if shelter_id:
            # Shelter Name
            shelter = item["cr_shelter_registration.shelter_id"]
            draw_string(x, y + 14, t_("Shelter"))
            draw_string(x, y, shelter, width=wt, height=20, size=10)

            # Shelter address
            address = place = None
            location = raw["gis_location.L4"] or raw["gis_location.L3"]
            if location:
                address = item["gis_location.addr_street"]
                postcode = item["gis_location.addr_postcode"]
                place = "%s %s" % (postcode, location) if postcode else location
            if address:
                y -= 13
                draw_string(x, y, address, width=wt, height=12, size=9)
            if place:
                y -= 13
                draw_string(x, y, place, width=wt, height=12, size=9)

    # -------------------------------------------------------------------------
    def draw_registration_details(self, item, t_):
        """
            Draws the registration details:
                - ID label and barcode
                - QR code and signature

            Args:
                item: the data item
                t_: the translator
        """

        h = self.height
        w = self.width

        raw = item["_row"]

        # ----- Left -----

        # ID Number and barcode
        y = h/2 + 45
        code = raw["pr_person.pe_label"]
        if code:
            self.draw_string(30, y, s3_str(code), width=w/2-60, size=28, bold=True, halign="center")
            self.draw_barcode(s3_str(code), w / 4, y - 25, height=20, halign="center", maxwidth=w/2-40)

        # ----- Right -----

        # QR-Code and Hash Signature
        registration = item.get("_reg")
        if not registration or \
            not all(registration.get(d) for d in ("token", "vhash", "vcode")):
            vcode = "%s##UNVERIFIED##UNREGISTERED" % code
            signature = None
        else:
            vcode = "##".join(map(s3_str, (code, registration["token"], registration["vhash"])))
            signature = registration["vcode"]

        if vcode:
            self.draw_qrcode(vcode,
                             w * 3/4,
                             h * 5/8,
                             size = w/2 - 120,
                             halign = "center",
                             valign = "middle",
                             level = "M",
                             )
        if signature:
            self.draw_string(w/2 + 20, h * 6/8 - 15, signature,
                             size = 9,
                             bold = False,
                             width = w/2-40,
                             halign = "center",
                             )

    # -------------------------------------------------------------------------
    def draw_border(self):
        """
            Draws a border around the contents
        """

        c = self.canv
        c.saveState()

        w = self.width
        h = self.height

        c.setFillColor(self.border_color)

        # Horizontal bars
        c.rect(18, h-22, w-36, 12, fill=1, stroke=0) # horizontal top
        c.rect(18, h/2, w-36, 12, fill=1, stroke=0) # horizontal bottom

        # Vertical bars
        c.rect(18, h/2, 4, h/2-22, fill=1, stroke=0) # vertical left
        c.rect(w-22, h/2, 4, h/2-22, fill=1, stroke=0) # vertical right

        c.restoreState()

    # -------------------------------------------------------------------------
    def draw_box(self, x, y, width, height):
        """
            Draws a (gray) box

            Args:
                x - bottom left corner, x coordinate (in points)
                y - bottom left corner, y coordinate (in points)
                width - the width in points
                height - the height in points
        """

        c = self.canv
        c.saveState()

        c.setLineWidth(1)
        c.setFillGray(0.95)
        c.setStrokeGray(0.9)

        c.rect(x, y, width, height, stroke=1, fill=0)

        c.restoreState()

# =============================================================================
class StaffIDCardLayout(PDFCardLayout):
    """
        Variant of IDCardLayout for staff members
    """

    border_color = HexColor(0xeb003c)

    # -------------------------------------------------------------------------
    @classmethod
    def fields(cls, resource):
        """
            The layout-specific list of fields to look up from the resource

            Args:
                resource: the resource

            Returns:
                list of field selectors
        """

        return ["id",
                "pe_id",
                "pe_label",
                "first_name",
                #"middle_name",
                "last_name",
                "date_of_birth",
                "human_resource.organisation_id$root_organisation",
                "human_resource.site_id",
                "human_resource.job_title_id",
                ]

    # -------------------------------------------------------------------------
    @classmethod
    def lookup(cls, resource, items):
        """
            Looks up layout-specific common data for all cards
            (extending super-method)

            Args:
                resource: the resource
                items: the items

            Returns:
                a dict with common data
        """

        output = super().lookup(resource, items)

        # Get the human_resource.site_ids
        site_ids = {item["_row"]["hrm_human_resource.site_id"] for item in items}
        site_ids.discard(None)

        # Look up shelter names and addresses for site_ids
        db = current.db
        s3db = current.s3db

        stable = s3db.cr_shelter
        ltable = s3db.gis_location

        left = ltable.on(ltable.id == stable.location_id)
        query = (stable.site_id.belongs(site_ids)) & \
                (stable.deleted == False)
        rows = db(query).select(stable.id,
                                stable.site_id,
                                stable.name,
                                ltable.id,
                                ltable.addr_postcode,
                                ltable.addr_street,
                                ltable.L3,
                                ltable.L4,
                                left = left,
                                )
        shelters = {}
        for row in rows:
            shelter = row.cr_shelter
            address = row.gis_location
            if address.id:
                d = [shelter.name,
                     address.addr_street,
                     address.L3 or address.L4,
                     address.addr_postcode,
                     ]
            else:
                d = [shelter.name, None, None, None]
            shelters[shelter.site_id] = d

        output["shelters"] = shelters

        return output

    # -------------------------------------------------------------------------
    def get_site_details(self, item):
        """
            Looks up the site details for the staff member from commons

            Args:
                item: the staff member data

            Returns:
                tuple with site details (name, place, address)
        """

        raw = item["_row"]

        # Shelter
        site_id = raw["hrm_human_resource.site_id"]

        shelter = self.common["shelters"].get(site_id) if site_id else None
        if shelter:
            name, address, place, postcode = shelter
            if place:
                place = "%s %s" % (postcode, place) if postcode else place
        else:
            name = place = address = None

        return name, place, address

# =============================================================================
class StaffIDCardLayoutL(StaffIDCardLayout, IDCardLayoutL):
    """
        Variant of IDCardLayoutL for staff members
    """

    # -------------------------------------------------------------------------
    def draw_person_details(self, item, t_):
        """
            Draws the person details:
                - full name
                - job title, if availbale
                - picture

            Args:
                item: the data item
                t_: the translator
        """

        w = self.width

        raw = item["_row"]
        common = self.common

        draw_string = self.draw_string

        x, y = 12, 82
        wt = w - (x + 70) # text width

        # Names
        name = s3_format_fullname(fname = raw["pr_person.first_name"],
                                  lname = raw["pr_person.last_name"],
                                  truncate = False,
                                  )
        draw_string(x, y, name, width=wt, height=12, size=12)

        # Date of birth
        y = y - 18
        #dob = raw["pr_person.date_of_birth"]
        #if dob:
        #    dob = item["pr_person.date_of_birth"]
        #    draw_string(x, y + 10, t_("Date of Birth"), size=5)
        #    draw_string(x, y, dob, width=wt, height=9, size=8)

        # Staff Role
        y = y - 17
        draw_string(x, y, t_("Staff"), width=wt, height=15, size=12, bold=True)
        job_title_id = raw["hrm_human_resource.job_title_id"]
        if job_title_id:
            job_title = item["hrm_human_resource.job_title_id"]
            draw_string(x, y-10, job_title, width=wt, height=10, size=10)

        # Profile picture
        pictures = common.get("pictures")
        picture = pictures.get(raw["pr_person.pe_id"]) if pictures else None
        if picture:
            self.draw_image(picture,
                            w - 16, 32, height=60, width=60,
                            halign = "right",
                            valign = "bottom",
                            )

    # -------------------------------------------------------------------------
    def draw_shelter_details(self, item, t_):
        """
            Draws the shelter details:
                - shelter name
                - shelter address

            Args:
                item: the data item
                t_: the translator
        """

        draw_string = self.draw_string

        # Start position
        w = self.width
        h = self.height
        x, y = 10, h-16
        wt = w - x*2 # text width

        # Shelter
        name, place, address = self.get_site_details(item)
        if name:
            draw_string(x, y, name, width=wt, height=12, size=9, halign="center")
            if address and place:
                address = ", ".join((address, place))
            elif place:
                address = place
            if address:
                draw_string(x, y-9, address, width=wt, height=8, size=7, halign="center")

# =============================================================================
class StaffIDCardLayoutP(StaffIDCardLayout, IDCardLayoutP):
    """
        Variant of IDCardLayoutP for staff members
    """

    def draw_person_details(self, item, t_):
        """
            Draws the person details:
                - full name
                - job title, if availbale
                - picture

            Args:
                item: the data item
                t_: the translator
        """

        h = self.height
        w = self.width

        raw = item["_row"]
        common = self.common

        draw_string = self.draw_string

        x, y = 18, 82
        wt = w-2*x # text width

        # Name
        name = s3_format_fullname(fname = raw["pr_person.first_name"],
                                  lname = raw["pr_person.last_name"],
                                  truncate = False,
                                  )
        draw_string(x, y, name, width=wt, height=12, size=12, halign="center")

        # Staff Role
        y = y - 24
        draw_string(x, y, t_("Staff"), width=wt, height=15, size=12, bold=True, halign="center")
        job_title_id = raw["hrm_human_resource.job_title_id"]
        if job_title_id:
            job_title = item["hrm_human_resource.job_title_id"]
            draw_string(x, y-12, job_title, width=wt, height=10, size=10, halign="center")

        # Profile picture
        pictures = common.get("pictures")
        picture = pictures.get(raw["pr_person.pe_id"]) if pictures else None
        if picture:
            self.draw_image(picture,
                            w * 1/2, h * 1/2 + 6, height=60, width=60,
                            halign = "center",
                            valign = "middle",
                            )

    # -------------------------------------------------------------------------
    def draw_shelter_details(self, item, t_):
        """
            Draws the shelter details:
                - shelter name
                - shelter address

            Args:
                item: the data item
                t_: the translator
        """

        draw_string = self.draw_string

        # Start position
        w = self.width
        h = self.height
        x, y = 8, h-20
        wt = w - x*2 # text width

        # Shelter
        name, place, address = self.get_site_details(item)
        if name:
            draw_string(x, y, name, width=wt, height=16, size=9, halign="center")
            if address:
                draw_string(x, y-9, address, width=wt, height=8, size=7, halign="center")
            if place:
                draw_string(x, y-18, place, width=wt, height=8, size=7, halign="center")

# =============================================================================
class StaffIDCardLayoutA4(StaffIDCardLayout, IDCardLayoutA4):
    """
        Variant of IDCardLayoutA4 for staff members
    """

    def draw_person_details(self, item, t_):
        """
            Draws the person details:
                - full name
                - job title, if availbale
                - picture

            Args:
                item: the data item
                t_: the translator
        """

        w = self.width
        h = self.height

        raw = item["_row"]
        common = self.common

        draw_string = self.draw_string

        # ----- Left -----

        # Draw box around person data
        left = 30
        bottom = h/2 + 95
        self.draw_box(left, bottom, w/2-60, 130)

        x = left + 10
        y = bottom + 100
        wt = w/2-2*x # text width

        # Names
        name = s3_format_fullname(fname = raw["pr_person.first_name"],
                                  #mname = raw["pr_person.middle_name"],
                                  lname = raw["pr_person.last_name"],
                                  truncate = False,
                                  )
        draw_string(x, y + 13, t_("Name"))
        draw_string(x, y, name, width=wt, height=20, size=12)

        site_id = raw["hrm_human_resource.site_id"]
        y = bottom + (27 if site_id else 50)

        # Staff Role
        draw_string(x, y, t_("Staff"), width=wt, height=20, size=18, bold=True)
        job_title_id = raw["hrm_human_resource.job_title_id"]
        if job_title_id:
            job_title = item["hrm_human_resource.job_title_id"]
            draw_string(x, y-16, job_title, width=wt, height=20, size=12)

        # ----- Right -----

        # Profile picture
        pictures = common.get("pictures")
        picture = pictures.get(raw["pr_person.pe_id"]) if pictures else None
        if picture:
            self.draw_image(picture,
                            w * 3/4, h * 7/8, height=h/4 - 80, width=w/2 - 60,
                            halign = "center",
                            valign = "middle",
                            )

    # -------------------------------------------------------------------------
    def draw_shelter_details(self, item, t_):
        """
            Draws the shelter details:
                - shelter name
                - shelter address

            Args:
                item: the data item
                t_: the translator
        """

        w = self.width
        h = self.height

        draw_string = self.draw_string

        x = 40
        y = h/2 + 165
        wt = w/2 - 2*x # text width

        # Shelter
        name, place, address = self.get_site_details(item)
        if name:
            # Shelter Name
            draw_string(x, y + 14, t_("Shelter"))
            draw_string(x, y, name, width=wt, height=20, size=10)

            # Shelter address
            if address:
                draw_string(x, y-10, address, width=wt, height=12, size=9)
            if place:
                draw_string(x, y-20, place, width=wt, height=12, size=9)

# END =========================================================================
