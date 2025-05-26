"""
    MRCMS Presence List

    License: MIT
"""

import datetime
import json

from dateutil.relativedelta import relativedelta

from gluon import current
from gluon.contenttype import contenttype
from gluon.streamer import DEFAULT_CHUNK_SIZE

from core import CRUDMethod, S3DateTime, XLSXWriter, s3_str

# =============================================================================
class PresenceList(CRUDMethod):
    """
        A list of people currently reported present at a site
    """

    # -------------------------------------------------------------------------
    def apply_method(self, r, **attr):
        """
            Entry point for the CRUDController

            Args:
                r: the CRUDRequest
                attr: controller parameters
        """

        output = None

        if r.http == "GET":
            output = self.presence_list(r, **attr)
        else:
            r.error(405, current.ERROR.BAD_METHOD)

        return output

    # -------------------------------------------------------------------------
    def presence_list(self, r, **attr):
        """
            Generate the presence list

            Args:
                r: the CRUDRequest
                attr: controller parameters
        """

        record = r.record
        if not record or "site_id" not in record:
            r.error(400, current.ERROR.BAD_RECORD)

        shelter_name = record.name
        data = self.lookup(record)

        output = None
        if r.representation == "xlsx":
            output = self.xlsx(shelter_name, data)
        else:
            r.error(415, current.ERROR.BAD_FORMAT)

        return output

    # -------------------------------------------------------------------------
    @classmethod
    def xlsx(cls, shelter_name, data):
        """
            Serialize the presence data as Excel file

            Args:
                shelter_name: the shelter name
                data: the presence data as extracted with lookup()
            Returns:
                the Excel file as byte stream
        """

        # Prepare the input for XLSXWriter
        table_data = {"columns": [],
                      "headers": {},
                      "types": {},
                      "rows": data,
                      }
        for fname, label, ftype in cls.columns():
            table_data["columns"].append(fname)
            table_data["headers"][fname] = label
            table_data["types"][fname] = ftype

        # Use a title row (also includes exported-date)
        current.deployment_settings.base.xls_title_row = True
        title = current.T("Presence List")
        if shelter_name:
            title = "%s - %s" % (shelter_name, title)

        # Generate XLSX byte stream
        output = XLSXWriter.encode(table_data, title=title, as_stream=True)

        # Set response headers
        disposition = "attachment; filename=\"presence_list.xlsx\""
        response = current.response
        response.headers["Content-Type"] = contenttype(".xlsx")
        response.headers["Content-disposition"] = disposition

        # Return stream response
        return response.stream(output,
                               chunk_size = DEFAULT_CHUNK_SIZE,
                               request = current.request
                               )

    # -------------------------------------------------------------------------
    @staticmethod
    def columns():
        """
            The columns of the presence list, in order of appearance

            Returns:
                tuple of tuples ((fieldname, label, datatype), ...)
        """

        T = current.T

        return (("type", "", "string"),
                ("pe_label", T("ID"), "string"),
                ("last_name", T("Last Name"), "string"),
                ("first_name", T("First Name"), "string"),
                ("gender", T("Gender"), "string"),
                ("age", T("Age"), "string"),
                ("unit", T("Housing Unit"), "string"),
                ("since", T("Reported present since"), "datetime"),
                )

    # -------------------------------------------------------------------------
    @classmethod
    def lookup(cls, shelter):
        """
            Looks up people currently reported present at the shelter

            Args:
                shelter: the cr_shelter Row
            Returns:
                the entries for the presence list as a list of dicts,
                dict structure see columns()

            Note:
                entries pre-ordered by name (last name, then first name)
        """

        T = current.T
        STAFF = T("Staff")
        RESIDENT = T("Resident")

        db = current.db
        s3db = current.s3db

        shelter_id = shelter.id
        site_id = shelter.site_id
        organisation_id = shelter.organisation_id

        ptable = s3db.pr_person
        ctable = s3db.dvr_case
        htable = s3db.hrm_human_resource
        rtable = s3db.cr_shelter_registration
        left = [ctable.on((ctable.person_id == ptable.id) & \
                          (ctable.organisation_id == organisation_id) & \
                          (ctable.deleted == False)),
                htable.on((htable.person_id == ptable.id) & \
                          (htable.organisation_id == organisation_id) & \
                          (htable.deleted == False)),
                rtable.on((rtable.person_id == ptable.id) & \
                          (rtable.shelter_id == shelter_id) & \
                          (rtable.deleted == False)),
                ]

        sptable = s3db.org_site_presence

        join = sptable.on((sptable.person_id == ptable.id) & \
                          (sptable.site_id == site_id) & \
                          (sptable.status == "IN") & \
                          (sptable.deleted == False))

        query = (ptable.deleted == False)
        rows = db(query).select(ptable.id,
                                ptable.pe_label,
                                ptable.first_name,
                                ptable.last_name,
                                ptable.gender,
                                ptable.date_of_birth,
                                sptable.date,
                                ctable.id,
                                htable.id,
                                rtable.id,
                                rtable.shelter_unit_id,
                                left = left,
                                join = join,
                                orderby = (ptable.last_name,
                                           ptable.first_name,
                                           ),
                                )
        staff, residents = [], []
        units = {}
        seen = set()
        for row in rows:
            person = row.pr_person
            if person.id in seen:
                # Duplicate (e.g. multiple case records):
                # - this is a serious DB inconsistency, but an emergency
                #   tool is the wrong place to raise the issue, so we just
                #   skip it
                continue
            seen.add(person.id)

            details = {}

            # Differentiate staff/residents
            if row.dvr_case.id:
                items = residents
                details["type"] = RESIDENT
            elif row.hrm_human_resource.id:
                items = staff
                details["type"] = STAFF
            else:
                items = staff
                details["type"] = "-"

            # Basic person data
            for fn in ("pe_label", "first_name", "last_name", "gender"):
                value = person[fn]
                represent = ptable[fn].represent
                details[fn] = represent(value) if represent else s3_str(value)

            # Age
            now = datetime.datetime.utcnow().date()
            dob = person.date_of_birth
            age = str(relativedelta(now, dob).years) if dob else "-"
            details["age"] = age

            # Housing unit
            registration = row.cr_shelter_registration
            if registration.id:
                unit_id = registration.shelter_unit_id
                persons = units.get(unit_id)
                if not persons:
                    persons = units[unit_id] = []
                persons.append(details)
            details["unit"] = "-"

            # Presence date
            presence = row.org_site_presence
            since = sptable.date.represent(presence.date)
            details["since"] = since

            items.append(details)

        # Look up housing unit names
        if units:
            utable = s3db.cr_shelter_unit
            query = utable.id.belongs(list(units.keys()))
            rows = db(query).select(utable.id, utable.name)
            for row in rows:
                persons = units[row.id]
                for details in persons:
                    details["unit"] = row.name

        return staff + residents

# =============================================================================
class RegistrationHistory(CRUDMethod):
    """
        Ajax method to read the shelter registration history of a client
    """

    def apply_method(self, r, **attr):
        """
            Entry point for the CRUDController

            Args:
                r: the CRUDRequest
                attr: controller parameters
        """

        output = {}

        resource = r.resource
        if resource.tablename != "pr_person":
            r.error(400, current.ERROR.BAD_RESOURCE)
        if not r.record:
            r.error(400, current.ERROR.BAD_RECORD)

        has_permission = current.auth.s3_has_permission
        person_id = r.record.id
        if not has_permission("read", "pr_person", record_id=person_id) or \
           not has_permission("read", "cr_shelter_registration_history"):
            r.unauthorised()

        if r.http == "GET":
            if r.representation == "json":
                history = self.extract(person_id)
                response = current.response
                if response:
                    response.headers["Content-Type"] = "application/json"
                output = self.serialize(history)

            else:
                r.error(415, current.ERROR.BAD_FORMAT)
        else:
            r.error(405, current.ERROR.BAD_METHOD)

        return output

    # -------------------------------------------------------------------------
    @staticmethod
    def extract(person_id):
        """
            Extracts the registration registry of a person

            Args:
                person_id: the person record ID

            Returns:
                a list of dicts like:
                    [{s: ShelterID,
                      p: PlannedDateTime,
                      i: CheckedInDateTime,
                      o: CheckedOutDateTime,
                      }, ...]
        """

        db = current.db
        s3db = current.s3db

        # Get all shelter registration history entries for person_id
        # ordered by date
        table = s3db.cr_shelter_registration_history

        query = (table.person_id == person_id) & \
                (table.deleted == False)
        rows = db(query).select(table.shelter_id,
                                table.date,
                                table.status,
                                table.previous_status,
                                orderby = table.date,
                                )

        history = []
        new_item = lambda s: {"s": s, "p": None, "i": None, "o": None, "c": False}

        item = None
        shelter_id = None
        current_status = None
        for row in rows:
            date = row.date
            status = row.status

            if not date or status not in (1, 2, 3):
                continue
            if shelter_id != row.shelter_id:
                if item:
                    history.append(item)
                shelter_id, item = row.shelter_id, None
            elif not shelter_id:
                continue

            if not item:
                item = new_item(shelter_id)

            if status == 1:
                if current_status == 2:
                    history.append(item)
                    item = new_item(shelter_id)
                if not item.get("p"):
                    item["p"] = date
            elif status == 2:
                if not item.get("i"):
                    item["i"] = date
            elif status == 3:
                item["o"] = date
                history.append(item)
                item = None
            else:
                continue

            current_status = status

        if item:
            history.append(item)
        return history

    # -------------------------------------------------------------------------
    @staticmethod
    def serialize(history):
        """
            Serializes the registration history as JSON

            Args:
                history: the history as returned by extract()

            Returns:
                a JSON array of objects like:
                    [{n: ShelterName,
                      p: PlannedDate,
                      i: CheckedInDate,
                      o: CheckedOutDate,
                      }, ...]
        """

        # Lookup all shelter names
        table = current.s3db.cr_shelter
        shelter_ids = {item.get("s") for item in history}
        rows = current.db(table.id.belongs(shelter_ids)).select(table.id,
                                                                table.name,
                                                                )
        shelters = {row.id: row.name for row in rows}

        # Format all items
        dtfmt = lambda dt: S3DateTime.date_represent(dt, utc=True)
        formatted = []
        for item in history:
            name = shelters.get(item.get("s"))
            if not name:
                name = "?"

            planned = item.get("p")
            planned = dtfmt(planned) if planned else None
            checked_in = item.get("i")
            checked_in = dtfmt(checked_in) if checked_in else None
            checked_out = item.get("o")
            checked_out = dtfmt(checked_out) if checked_out else None

            formatted.append({"n": name, "p": planned, "i": checked_in, "o": checked_out})

        # Mark last item as current if not checked-out
        if formatted and formatted[-1]["o"] is None:
            formatted[-1]["c"] = True

        # Serialize as JSON
        return json.dumps(formatted)

# END =========================================================================
