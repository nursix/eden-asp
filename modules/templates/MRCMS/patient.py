"""
    Patient Report for MRCMS

    Copyright: 2025 (c) Sahana Software Foundation

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

import datetime
import os

from io import BytesIO
from lxml import etree

from reportlab.pdfgen import canvas
from reportlab.platypus import BaseDocTemplate, Frame, KeepTogether, PageTemplate, Paragraph
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT, TA_JUSTIFY
from reportlab.lib.pagesizes import A4, LETTER
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader

from gluon import current
from gluon.contenttype import contenttype

from core import CRUDMethod, S3DateTime, s3_fullname, s3_str

# Fonts used in PatientReportTemplate
NORMAL = "Helvetica"
BOLD = "Helvetica-Bold"

# Report content fields (in order)
ANAMNESIS = ("allergies", "chronic", "disabilities", "history")
EPICRISIS = ("situation", "diagnoses", "progress", "outcome", "recommendation")

# =============================================================================
class PatientReport(CRUDMethod):
    # TODO docstring

    def apply_method(self, r, **attr):

        output = None

        if r.http == "GET":
            if r.representation == "pdf":
                output = self.export_pdf(r, **attr)
            else:
                r.error(415, current.ERROR.BAD_FORMAT)
        else:
            r.error(405, current.ERROR.BAD_METHOD)

        return output

    # -------------------------------------------------------------------------
    def export_pdf(self, r, **attr):
        # TODO docstring

        response = current.response

        if r.tablename != "med_patient" or not r.record:
            r.error(400, current.ERROR.BAD_RESOURCE)
        if not self._permitted("read"):
            r.unauthorised()

        # Generate PDF report
        patient = Patient(r.record.id)
        output = patient.pdf()

        # TODO Generate individual filename
        filename = "patient"
        disposition = "attachment; filename=\"%s.pdf\"" % filename

        # Set content type
        response.headers["Content-Type"] = contenttype(".pdf")
        response.headers["Content-disposition"] = disposition

        return output

# =============================================================================
class Patient:

    def __init__(self, patient_id):

        self.patient_id = patient_id

        self._record = None
        self._unit = None
        self._person = None
        self._shelter = None
        self._vitals = None

        self._anamnesis = None
        self._epicrisis = None

    # -------------------------------------------------------------------------
    @property
    def record(self):
        """
            The med_patient record (lazy property)

            Returns:
                the med_patient Row
        """

        record = self._record
        if record is None:
            table = current.s3db.med_patient
            query = (table.id == self.patient_id)
            record = current.db(query).select(table.id,
                                              table.refno,
                                              table.unit_id,
                                              table.person_id,
                                              table.person,
                                              table.date,
                                              table.reason,
                                              limitby = (0, 1),
                                              ).first()
            self._record = record
        return record

    # -------------------------------------------------------------------------
    @property
    def unit(self):
        # TODO docstring

        unit = self._unit
        if unit is None:
            s3db = current.s3db
            utable = s3db.med_unit
            otable = s3db.org_organisation
            join = otable.on(otable.id == utable.organisation_id)
            query = (utable.id == self.record.unit_id)
            row = current.db(query).select(#utable.id,
                                           utable.name,
                                           #otable.id,
                                           otable.name,
                                           otable.logo,
                                           join = join,
                                           limitby = (0, 1)
                                           ).first()
            if row:
                organisation = row.org_organisation
                unit = {"name": row.med_unit.name,
                        "organisation": organisation.name,
                        }
                if organisation.logo:
                    logo = os.path.join(otable.logo.uploadfolder, organisation.logo)
                else:
                    path = current.deployment_settings.get_custom("idcard_default_logo")
                    logo = os.path.join(current.request.folder, "static", "themes", *path) \
                           if path else None
                if logo:
                    unit["logo"] = logo
                self._unit = unit

        return unit

    # -------------------------------------------------------------------------
    @property
    def person(self):
        # TODO docstring

        person_id = self.record.person_id

        person = self._person
        if person is None and person_id:

            ptable = current.s3db.pr_person
            query = (ptable.id == person_id)
            row = current.db(query).select(ptable.id,
                                           ptable.first_name,
                                           ptable.middle_name,
                                           ptable.last_name,
                                           ptable.gender,
                                           ptable.date_of_birth,
                                           ptable.pe_label,
                                           limitby = (0, 1),
                                           ).first()
            if row:
                person = {"name": s3_fullname(row),
                          "gender": ptable.gender.represent(row.gender),
                          "dob": ptable.date_of_birth.represent(row.date_of_birth),
                          "label": row.pe_label,
                          }
                self._person = person
        return person

    # -------------------------------------------------------------------------
    @property
    def shelter(self):
        # TODO docstring

        shelter = self._shelter
        if shelter is None:
            shelter = {}

            db = current.db
            s3db = current.s3db

            rtable = s3db.cr_shelter_registration
            stable = s3db.cr_shelter
            ltable = s3db.gis_location

            join = stable.on(stable.id == rtable.shelter_id)
            left = ltable.on(ltable.id == stable.location_id)
            query = (rtable.person_id == self.record.person_id) & \
                    (rtable.registration_status.belongs((1, 2))) & \
                    (rtable.deleted == False)
            row = db(query).select(stable.name,
                                   ltable.id,
                                   ltable.addr_street,
                                   ltable.addr_postcode,
                                   ltable.L3,
                                   ltable.L4,
                                   join = join,
                                   left = left,
                                   limitby = (0, 1),
                                   ).first()
            if row:
                shelter["name"] = row.cr_shelter.name

                location = row.gis_location
                if location.id:
                    address = location.L4 or location.L3 or ""
                    if location.addr_postcode:
                        address = "%s %s" % (location.addr_postcode, address)
                    if location.addr_street:
                        address = "%s, %s" % (location.addr_street, address)
                    shelter["address"] = address

            self._shelter = shelter
        return shelter

    # -------------------------------------------------------------------------
    @property
    def visit(self):
        # TODO docstring

        table = current.s3db.med_patient

        record = self.record

        return {"refno": record.refno,
                "date": table.date.represent(record.date),
                "reason": record.reason,
                }

    # -------------------------------------------------------------------------
    @property
    def vitals(self):
        # TODO docstring

        vitals = self._vitals
        if vitals is None:
            vitals = {}

            db = current.db
            s3db = current.s3db

            fields = ("airways", "rf", "o2sat", "o2sub", "bp", "hf", "temp", "consc")

            # Must not be older than 12 hours
            earliest = current.request.utcnow - datetime.timedelta(hours=12)

            vtable = s3db.med_vitals
            query = (vtable.patient_id == self.patient_id) & \
                    (vtable.date > earliest) & \
                    (vtable.deleted == False)
            row = db(query).select(vtable.id,
                                   vtable.date,
                                   *(vtable[fn] for fn in fields),
                                   limitby = (0, 1),
                                   orderby = ~vtable.date,
                                   ).first()
            if row:
                vitals = {fn: row[fn] for fn in fields + ("date",)}
                if not row.temp:
                    # Look up temp from any earlier record in the last 12 hours
                    query = (vtable.temp != None) & query
                    row = db(query).select(vtable.temp, limitby=(0, 1), orderby=~vtable.date).first()
                    vitals["temp"] = row.temp if row else None

                # Represent values
                for k, v in vitals.items():
                    rv = vtable[k].represent(v)
                    if hasattr(rv, "flatten"):
                        try:
                            rv = rv.flatten()
                        except Exception:
                            # Fall back to str-ified raw value
                            rv = s3_str(v)
                    vitals[k] = rv

            self._vitals = vitals

        return vitals

    # -------------------------------------------------------------------------
    @property
    def anamnesis(self):
        # TODO docstring

        anamnesis = self._anamnesis
        if anamnesis is None:
            person_id = self.record.person_id
            if person_id:
                table = current.s3db.med_anamnesis
                query = (table.person_id == person_id) & \
                        (table.deleted == False)
                anamnesis = current.db(query).select(table.id,
                                                     *(table[fn] for fn in ANAMNESIS),
                                                     limitby = (0, 1),
                                                     ).first()
                self._anamnesis = anamnesis

        return anamnesis

    # -------------------------------------------------------------------------
    @property
    def epicrisis(self):
        # TODO docstring

        epicrisis = self._epicrisis
        if epicrisis is None:
            table = current.s3db.med_epicrisis
            query = (table.patient_id == self.patient_id) & \
                    (table.deleted == False)
            epicrisis = current.db(query).select(table.id,
                                                 table.is_final,
                                                 *(table[fn] for fn in EPICRISIS),
                                                 limitby = (0, 1),
                                                 ).first()
            self._epicrisis = epicrisis

        return epicrisis

    # -------------------------------------------------------------------------
    def contents_xml(self):
        # TODO docstring

        s3db = current.s3db

        contents = ""
        template = "<para fontSize=\"10\"><b>%s</b></para><para leftIndent=\"8\">%s</para>"
        paragraph = lambda l, v: template % (l, v.replace("\r\n", "<br/>").replace("\n", "<br/>"))

        anamnesis = self.anamnesis
        if anamnesis and any(anamnesis[fn] for fn in ANAMNESIS):
            atable = s3db.med_anamnesis
            for fn in ANAMNESIS:
                value = anamnesis[fn]
                if value:
                    label = atable[fn].label
                    contents += "<keepTogether>%s</keepTogether>" % paragraph(label, value)

        epicrisis = self.epicrisis
        if epicrisis and any(epicrisis[fn] for fn in EPICRISIS):
            etable = s3db.med_epicrisis
            for fn in EPICRISIS:
                value = epicrisis[fn]
                if value:
                    label = etable[fn].label
                    contents += "<keepTogether>%s</keepTogether>" % paragraph(label, value)

        contents = "<document><story>%s</story></document>" % contents

        return contents

    # -------------------------------------------------------------------------
    def pdf(self):
        """
            Renders the patient report as PDF

            Returns:
                Byte stream (BytesIO) if successful, otherwise None
        """

        doc = PatientReportTemplate(self)

        contents = self.contents_xml()
        output_stream = BytesIO()
        flow = doc.get_flowables(contents)
        doc.build(flow,
                  output_stream,
                  canvasmaker=NumberedCanvas,
                  )
        output_stream.seek(0)

        return output_stream

# =============================================================================
class PatientReportTemplate(BaseDocTemplate):
    """
        Platypus document template for patient reports
    """

    def __init__(self, patient, pagesize=None):
        """
            Args:
                patient: the Patient object
                pagesize: "A4"|"Letter"|(width,height), default "A4"
        """

        self.patient = patient


        # Page size (default A4)
        if pagesize == "A4":
            pagesize = A4
        elif pagesize == "Letter":
            pagesize = LETTER
        elif not isinstance(pagesize, (tuple, list)):
            pagesize = A4

        margins = (1.5*cm, 1.5*cm, 1.5*cm, 2.5*cm)

        pages = self.page_layouts(pagesize, margins)

        unit = patient.unit
        if unit:
            unit_name = "%s / %s" % (unit.get("organisation"), unit.get("name"))
        else:
            unit_name = None
        system_name = current.deployment_settings.get_system_name_short()

        # Call super-constructor
        super().__init__(None, # filename, unused
                         pagesize = pagesize,
                         pageTemplates = pages,
                         topMargin = margins[0],
                         rightMargin = margins[1],
                         bottomMargin = margins[2],
                         leftMargin = margins[3],
                         title = "Patient Report",
                         author = unit_name,
                         creator = system_name,
                         )

    # -------------------------------------------------------------------------
    def page_layouts(self, pagesize, margins):
        """
            Instantiates the necessary PageTemplates with Frames

            Returns:
                list of PageTemplates
        """

        footer_height = 1*cm
        first_header_height = 3*cm + 6 * 24 # 24 = box height
        later_header_height = 3*cm + 3 * 24

        pagewidth, pageheight = pagesize
        margin_top, margin_right, margin_bottom, margin_left = margins

        printable_width = pagewidth - margin_left - margin_right
        printable_height = pageheight - margin_top - margin_bottom

        fframe = Frame(margin_left,
                       margin_bottom + footer_height,
                       printable_width,
                       printable_height - footer_height - first_header_height,
                       topPadding = 8,
                       rightPadding = 0,
                       bottomPadding = 8,
                       leftPadding = 0,
                       )

        lframe = Frame(margin_left,
                       margin_bottom + footer_height,
                       printable_width,
                       printable_height - footer_height - later_header_height,
                       topPadding = 8,
                       rightPadding = 0,
                       bottomPadding = 8,
                       leftPadding = 0,
                       )

        return [PageTemplate(id="FirstPage", frames=[fframe], onPage=self.draw_fixed),
                PageTemplate(id="LaterPage", frames=[lframe], onPage=self.draw_fixed),
                ]
    # -------------------------------------------------------------------------
    def handle_pageBegin(self):
        # TODO docstring

        self._handle_pageBegin()
        self._handle_nextPageTemplate('LaterPage')

    # -------------------------------------------------------------------------
    def draw_fixed(self, canvas, doc):
        """
            Draws all fixes page elements

            Args:
                canvas: the Canvas to draw on
                doc: the document
        """

        T = current.T
        w, h = doc.pagesize

        # Printable width and remaining width
        pw = w - self.leftMargin - self.rightMargin
        rw = lambda x: w - self.rightMargin - x

        patient = self.patient

        # Unit data
        unit = patient.unit
        logo = unit.get("logo")
        if logo:
            self.draw_image(canvas,
                            logo,
                            self.leftMargin,
                            h - self.topMargin,
                            width = 2.5*cm,
                            proportional = True,
                            valign = "top",
                            )

        draw_value = self.draw_value

        x = (self.leftMargin + 3*cm + w - self.rightMargin) / 2
        y = h - self.topMargin - 20
        hw = pw - 3*cm
        draw_value(canvas, x, y,
                   unit.get("organisation", ""),
                   width = hw,
                   height = 18,
                   size = 16,
                   bold = True,
                   halign = "right",
                   )

        y -= 18
        shelter = patient.shelter
        if shelter:
            draw_value(canvas, x, y,
                       shelter.get("name", ""),
                       width = hw,
                       height = 12,
                       size = 10,
                       bold = True,
                       halign = "right",
                       )
            y -= 12
            draw_value(canvas, x, y,
                       shelter.get("address", ""),
                       width = hw,
                       height = 12,
                       size = 10,
                       bold = False,
                       halign = "right",
                       )
            y -= 12
        else:
            y -= 24

        # Unit Name and Phone
        y = h - self.topMargin - 2.5*cm
        draw_value(canvas, x, y,
                   unit.get("name", ""),
                   width = hw,
                   height = 14,
                   size = 12,
                   bold = True,
                   halign = "right",
                   )

        # Box height
        bh = 24
        box = self.draw_box_with_label

        # Patient data
        visit = patient.visit
        person = patient.person

        x = self.leftMargin
        y = h - self.topMargin - 4*cm
        box(canvas, x, y, width=100, height=bh, label="Pat.No.", text=visit.get("refno"))
        x += 100
        if person:
            box(canvas, x, y, width=rw(x)-180, height=bh, label="Patient", text=person.get("name"))
            x += rw(x)-180
            box(canvas, x, y, width=60, height=bh, label="Sex", text=person.get("gender"))
            x += 60
            box(canvas, x, y, width=60, height=bh, label="Date of Birth", text=person.get("dob"))
            x += 60
            box(canvas, x, y, width=60, height=bh, label="ID", text=person.get("label"))
        else:
            box(canvas, x, y, width=rw(x), height=bh, label="Patient", text=patient.record.person)

        # Current visit
        x = self.leftMargin
        y -= bh
        box(canvas, x, y, width=100, height=bh, label="Date", text=visit.get("date"))
        x += 100
        box(canvas, x, y, width = rw(x), height=bh, label="Reason for Visit", text=visit.get("reason"))


            # Vitals
        page_number = canvas._pageNumber
        if page_number == 1:
            vitals = patient.vitals
            y -= bh + 8
            draw_value(canvas, self.leftMargin + pw/2, y,
                       "Vitalparameter %s" % vitals.get("date", ""),
                       width = pw,
                       height = 10,
                       size = 8,
                       bold = True,
                       halign = "left",
                       )

            y -= bh + 4
            x = self.leftMargin
            box(canvas, x, y, width=180, height=bh, label="Airways", text=vitals.get("airways"))
            x += 180
            box(canvas, x, y, width=60, height=bh, label="RF", text=vitals.get("rf"))
            x += 60
            box(canvas, x, y, width=60, height=bh, label="O2 Sat", text=vitals.get("o2sat"))
            x += 60
            box(canvas, x, y, width=60, height=bh, label="O2 L/min", text=vitals.get("o2sub"))
            y -= bh
            x = self.leftMargin
            box(canvas, x, y, width=180, height=bh, label="Consciousness", text=vitals.get("consc"))
            x += 180
            box(canvas, x, y, width=60, height=bh, label="Blood Pressure", text=vitals.get("bp"))
            x += 60
            box(canvas, x, y, width=60, height=bh, label="HF", text=vitals.get("hf"))
            x += 60
            box(canvas, x, y, width=60, height=bh, label="Temp", text=vitals.get("temp"))
            # Empty box for annotations
            x+= 60
            box(canvas, x, y, width=rw(x), height=bh*2, label="Annotations")

        # Bottom box
        epicrisis = patient.epicrisis
        report_status = T("final") if epicrisis and epicrisis.is_final else T("preliminary")
        now = S3DateTime.datetime_represent(current.request.utcnow, utc=True)

        y = self.bottomMargin
        x = self.leftMargin
        box(canvas, x, y, width=100, height=bh, label="Report generated", text=now)
        x += 100
        box(canvas, x, y, width=100, height=bh, label="Report is", text=report_status)
        x += 100
        box(canvas, x, y, width=200, height=bh, label="Signature")
        x += 200
        box(canvas, x, y, width=rw(x), height=bh, label="Page")

    # -------------------------------------------------------------------------
    @staticmethod
    def draw_image(canvas, img, x, y, *,
                   width=None,
                   height=None,
                   proportional=True,
                   scale=None,
                   halign=None,
                   valign=None,
                   ):
        """
            Helper function to draw an image
                - requires PIL (required for ReportLab image handling anyway)

            Args:
                img: the image (filename or BytesIO buffer)
                x: drawing position
                y: drawing position
                width: the target width of the image (in points)
                height: the target height of the image (in points)
                proportional: keep image proportions when scaling to width/height
                scale: scale the image by this factor (overrides width/height)
                halign: horizontal alignment ("left"|"center"|"right"), default left
                valign: vertical alignment ("top"|"middle"|"bottom"), default bottom
        """

        if hasattr(img, "seek"):
            is_buffer = True
            img.seek(0)
        else:
            is_buffer = False

        try:
            from PIL import Image as pImage
        except ImportError:
            current.log.error("Image rendering failed: PIL not installed")
            return

        pimg = pImage.open(img)
        img_size = pimg.size

        if not img_size[0] or not img_size[1]:
            # This image has at least one dimension of zero
            return

        # Compute drawing width/height
        if scale:
            width = img_size[0] * scale
            height = img_size[1] * scale
        elif width and height:
            if proportional:
                scale = min(float(width) / img_size[0], float(height) / img_size[1])
                width = img_size[0] * scale
                height = img_size[1] * scale
        elif width:
            height = img_size[1] * (float(width) / img_size[0])
        elif height:
            width = img_size[0] * (float(height) / img_size[1])
        else:
            width = img_size[0]
            height = img_size[1]

        # Compute drawing position from alignment options
        hshift = vshift = 0
        if halign == "right":
            hshift = width
        elif halign == "center":
            hshift = width / 2.0

        if valign == "top":
            vshift = height
        elif valign == "middle":
            vshift = height / 2.0

        # Draw the image
        if is_buffer:
            img.seek(0)
        ir = ImageReader(img)

        canvas.drawImage(ir,
                         x - hshift,
                         y - vshift,
                         width = width,
                         height = height,
                         preserveAspectRatio = proportional,
                         mask = "auto",
                         )

    # -------------------------------------------------------------------------
    @classmethod
    def draw_box_with_label(cls, canvas, x, y, *,
                            width = 120,
                            height = 24,
                            label = None,
                            text = None,
                            ):
        """
            Draw a placeholder box with label at the inside top (paper
            form style), and text below label (if provided)

            Args:
                x: the horizontal position (from left)
                y: the vertical position (from bottom)
                width: the horizontal length of the line
                label: the label
                text: the text
        """

        label_size, text_size = 6, 10

        canvas.saveState()

        canvas.setStrokeGray(0.4)
        canvas.setFillGray(0.4)

        canvas.setLineWidth(0.5)
        canvas.rect(x, y, width, height, stroke=1, fill=0)

        if label:
            canvas.setFont("Helvetica", label_size)
            canvas.drawString(x + 2, y + height - label_size - 1, label)

        canvas.restoreState()

        if text:
            cls.draw_value(canvas,
                           x + width / 2,
                           y + 1,
                           text,
                           width = width - 10,
                           height = height - label_size - 1,
                           size = text_size,
                           )

    # -------------------------------------------------------------------------
    @staticmethod
    def draw_value(canvas, x, y, value, *,
                   width=120,
                   height=40,
                   size=7,
                   bold=True,
                   halign="left",
                   ):
        """
            Helper function to draw a centered text above position (x, y);
            allows the text to wrap if it would otherwise exceed the given
            width

            Args:
                canvas: the canvas to draw on
                x: drawing position
                y: drawing position
                value: the text to render
                width: the maximum available width (points)
                height: the maximum available height (points)
                size: the font size (points)
                bold: use bold font
                halign: horizontal alignment (left|center|right)

            Returns:
                the actual height of the text element drawn
        """

        alignments = {"left": TA_LEFT,
                      "right": TA_RIGHT,
                      "center": TA_CENTER,
                      }

        # Preserve line breaks by replacing them with <br/> tags
        value = s3_str(value).strip("\n").replace('\n','<br />\n')

        style_sheet = getSampleStyleSheet()
        style = style_sheet["Normal"]
        style.fontName = BOLD if bold else NORMAL
        style.fontSize = size
        style.leading = size + 2
        style.splitLongWords = False
        style.alignment = alignments.get(halign, TA_LEFT)

        para = Paragraph(value, style)
        aw, ah = para.wrap(width, height)

        while((ah > height or aw > width) and style.fontSize > 4):
            # Reduce font size to make fit
            style.fontSize -= 1
            style.leading = style.fontSize + 2
            para = Paragraph(value, style)
            aw, ah = para.wrap(width, height)

        para.drawOn(canvas, x - para.width / 2, y)

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

    # -------------------------------------------------------------------------
    @staticmethod
    def get_flowables(contents):
        """
            Converts the contents XML into a list of Flowables

            Args:
                contents: the contents XML (str)

            Returns:
                list of Flowables
        """

        style_sheet = getSampleStyleSheet()
        style = style_sheet["Normal"]
        style.spaceAfter = 10
        style.alignment = TA_JUSTIFY
        style.fontName = NORMAL

        body = []

        root = etree.fromstring(contents)

        for elem in root.xpath("story[1]/keepTogether|para"):
            if elem.tag == "keepTogether":
                items = []
                for para in elem.findall("para"):
                    item = etree.tostring(para).decode("utf-8")
                    items.append(Paragraph(item, style=style))
                body.append(KeepTogether(items))
            else:
                item = etree.tostring(elem).decode("utf-8")
                body.append(Paragraph(item, style=style))

        if not body:
            # Add at least one (empty) paragraph, so that the first
            # page with all fixed layout elements will be generated
            # even if the report as such is empty
            body = [Paragraph("")]

        return body

# =============================================================================
class NumberedCanvas(canvas.Canvas):
    """ Canvas type with page numbers """

    def __init__(self, *args, **kwargs):

        canvas.Canvas.__init__(self, *args, **kwargs)
        self._saved_page_states = []

    # -------------------------------------------------------------------------
    def showPage(self):

        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    # -------------------------------------------------------------------------
    def save(self):

        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_number(num_pages)
            canvas.Canvas.showPage(self)
        canvas.Canvas.save(self)

    # -------------------------------------------------------------------------
    def draw_page_number(self, page_count):

        self.setFont("Helvetica", 7)
        self.drawRightString(self._pagesize[0] - 2.1*cm,
                             1.6*cm,
                             "%d / %d" % (self._pageNumber, page_count),
                             )

# END =========================================================================
