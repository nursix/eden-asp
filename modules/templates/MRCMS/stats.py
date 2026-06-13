"""
    Performance Indicators for MRCMS

    License: MIT
"""

from dateutil.relativedelta import relativedelta
from io import BytesIO

from gluon import current, HTTP

from core import CRUDMethod, XLSWriter, s3_decode_iso_datetime, s3_str

# =============================================================================
class PerformanceIndicators:
    """ Default Performance Indicators Set (Base Class) """

    sectors = None
    exclude_sectors = None

    def __init__(self):

        self.styles = None

        self.title = current.T("Performance Indicators")

        self._sector_ids = None

    # -------------------------------------------------------------------------
    def compute(self, resource):
        """
            Query/compute the performance indicators

            Args:
                resource: the filtered dvr_response_action resource

            Returns:
                dict with performance indicators (raw values)
        """

        table = resource.table
        rows = resource.select(["id"], as_rows=True)

        # Master query
        record_ids = set(row.id for row in rows)
        dbset = self.dbset(record_ids,
                           consultation = current.deployment_settings.get_dvr_response_types(),
                           )

        # Total clients
        num_clients = table.person_id.count(distinct=True)
        row = dbset.select(num_clients).first()
        total_clients = row[num_clients]

        # Total number of consultations, average effort per consultation
        num_responses = table._id.count(distinct=True)
        avg_hours = table.hours.avg()
        row = dbset.select(num_responses, avg_hours).first()
        total_responses = row[num_responses]
        avg_hours_per_response = row[avg_hours]

        # Average number of consultations per client
        if total_clients:
            avg_responses_per_client = total_responses / total_clients
        else:
            avg_responses_per_client = 0

        # Return indicators
        return {"total_responses": total_responses,
                "total_clients": total_clients,
                "avg_hours_per_response": avg_hours_per_response,
                "avg_responses_per_client": round(avg_responses_per_client, 2),
                }

    # -------------------------------------------------------------------------
    def export(self, resource, sheet, title, subtitle=None):
        """
            Export performance indicators

            Args:
                resource: the CRUDResource
                sheet: the XLS worksheet to write to
                title: the title for the export
                subtitle: an optional subtitle (e.g. start+end dates)
        """

        T = current.T

        indicators = self.compute(resource)

        write = self.write
        rowindex = 0

        # Title
        write(sheet, rowindex, 0, title, style="header")
        rowindex += 1

        # Subtitle (optional)
        if subtitle:
            write(sheet, rowindex, 0, subtitle)
            rowindex += 2
        else:
            rowindex += 1

        # Basic performance indicators
        write(sheet, rowindex, 0, T("Total Number of Consultations"))
        write(sheet, rowindex, 1, indicators.get("total_responses", ""))
        rowindex += 1

        write(sheet, rowindex, 0, T("Total Number of Clients"))
        write(sheet, rowindex, 1, indicators.get("total_clients", ""))
        rowindex += 1

        write(sheet, rowindex, 0, T("Average Duration of Consultations (minutes)"))
        avg_hours_per_response = indicators.get("avg_hours_per_response")
        if avg_hours_per_response:
            avg_minutes_per_response = int(round(avg_hours_per_response * 60))
        else:
            avg_minutes_per_response = ""
        write(sheet, rowindex, 1, avg_minutes_per_response)
        rowindex += 1

        write(sheet, rowindex, 0, T("Average Number of Consultations per Client"))
        write(sheet, rowindex, 1, indicators.get("avg_responses_per_client", ""))
        rowindex += 2

    # -------------------------------------------------------------------------
    def write(self, sheet, rowindex, colindex, label, style="odd"):
        """
            Write a label/value into the XLS worksheet

            Args:
                sheet: the worksheet
                rowindex: the row index
                colindex: the column index
                label: the label/value to write
                style: style name (XLSWriter styles)
        """

        styles = self.styles
        if not styles:
            self.styles = styles = XLSWriter._styles()

        style = styles.get(style)
        if not style:
            import xlwt
            style = xlwt.XFStyle()

        label = s3_str(label)

        # Adjust column width
        col = sheet.col(colindex)
        curwidth = col.width or 0
        adjwidth = max(len(label) * 240, 2480) if label else 2480
        col.width = max(curwidth, adjwidth)

        row = sheet.row(rowindex)
        row.write(colindex, label, style)

    # -------------------------------------------------------------------------
    # Properties and helper functions
    # -------------------------------------------------------------------------
    @property
    def sector_ids(self):
        """
            The record ID of the relevant sector (lazy property)

            Returns:
                org_sector record ID
        """

        sector_ids = self._sector_ids
        if sector_ids is None:

            table = current.s3db.org_sector

            query = (table.deleted == False)
            for exclude, sectors in enumerate((self.sectors, self.exclude_sectors)):
                if sectors:
                    if len(sectors) == 1:
                        q = (table.abrv == sectors[0])
                    else:
                        q = (table.abrv.belongs(sectors))
                    if exclude:
                        q = ~q
                    query = q & query

            rows = current.db(query).select(table.id)
            sector_ids = self._sector_ids = {row.id for row in rows}

        return sector_ids

    # -------------------------------------------------------------------------
    @staticmethod
    def need_ids(code):
        """
            Returns a sub-select for dvr_need.id matching the given type code

            Args:
                code: the need type code

            Returns:
                sub-select
        """

        table = current.s3db.dvr_need
        if isinstance(code, (tuple, set, list)):
            query = (table.code.belongs(code))
        else:
            query = (table.code == code)
        query &= (table.deleted == False)

        return current.db(query)._select(table.id)

    # -------------------------------------------------------------------------
    def theme_ids(self, need=None, invert=False):
        """
            Returns a sub-select for the themes in the relevant sector

            Args:
                need: limit selection to themes linked to need types with
                      this type code(s)
                invert: invert the need filter

            Returns:
                sub-select
        """

        table = current.s3db.dvr_response_theme
        query = (table.sector_id.belongs(self.sector_ids))
        if need:
            if invert:
                query &= (~(table.need_id.belongs(self.need_ids(need))))
            else:
                query &= (table.need_id.belongs(self.need_ids(need)))
        query &= (table.deleted == False)
        return current.db(query)._select(table.id)

    # -------------------------------------------------------------------------
    def action_ids(self, subset, need=None, invert=False):
        """
            Returns a sub-select for actions in the subset linked to relevant
            themes

            Args:
                subset: a pre-filtered set of dvr_response_action.id
                need: limit selection to actions with themes linked to need
                      types with this type code(s)
                invert: invert the need filter

            Returns:
                sub-select
        """

        table = current.s3db.dvr_response_action_theme
        query = (table.theme_id.belongs(self.theme_ids(need=need, invert=invert))) & \
                (table.action_id.belongs(subset)) & \
                (table.deleted == False)
        return current.db(query)._select(table.action_id, distinct=True)

    # -------------------------------------------------------------------------
    def dbset(self,
              subset,
              consultation = True,
              code = None,
              indirect_closure = False,
              need = None,
              invert = False,
              ):
        """
            Returns a Set (dbset) of relevant dvr_response_action

            Args:
                subset: a pre-filtered set of dvr_response_action.id
                consultation: only consultation-type actions
                code: limit selection to actions of types with this type code
                indirect_closure: whether to include actions that have been
                                  accomplished by participation of the client
                                  in another action
                need: limit selection to actions with themes linked to needs
                      with this type code(s) (mutually exclusive with code)
                invert: invert the need filter

            Returns:
                a Set (dbset)
        """

        db = current.db
        s3db = current.s3db

        # Status filter
        stable = s3db.dvr_response_status
        query = (stable.is_closed == True)
        if not indirect_closure:
            query &= (stable.is_indirect_closure == False)
        query &= (stable.is_canceled == False) & \
                 (stable.deleted == False)
        status_ids = db(query)._select(stable.id)

        # Type filter
        ttable = s3db.dvr_response_type
        query = (ttable.deleted == False)
        if consultation:
            query = (ttable.is_consultation == True) & query
        if code:
            if isinstance(code, (tuple, list, set)):
                query = (ttable.code.belongs(code)) & query
            else:
                query = (ttable.code == code) & query
        type_ids = db(query)._select(ttable.id)

        # Themes filter
        if consultation:
            subset = self.action_ids(subset, need=need, invert=invert)

        atable = s3db.dvr_response_action
        master_query = (atable.status_id.belongs(status_ids)) & \
                       (atable.response_type_id.belongs(type_ids)) & \
                       (atable.id.belongs(subset)) & \
                       (atable.deleted == False)

        return db(master_query)

# =============================================================================
class PerformanceIndicatorsBAMF(PerformanceIndicators):
    """ Performance Indicator Set BAMF (LEA) """

    sectors = ("AVB",)
    exclude_sectors = None

    # -------------------------------------------------------------------------
    def __init__(self):

        super().__init__()

        self.title = current.T("Indikatorenbericht")

    # -------------------------------------------------------------------------
    def compute(self, resource):
        """
            Query/compute the performance indicators

            Args:
                resource: the filtered dvr_response_action resource

            Returns:
                dict with performance indicators (raw values)
        """

        rows = resource.select(["id"], as_rows=True)
        subset = {row.id for row in rows}

        output = {"clients": self.clients(subset),
                  "consultations": self.consultations(subset),
                  "referrals": self.referrals(subset),
                  "vulnerabilities": self.vulnerabilities(subset),
                  "themes": self.themes(subset),
                  "followups": self.followups(subset),
                  "efforts": self.efforts(subset),
                  }

        return output

    # -------------------------------------------------------------------------
    def export(self, resource, sheet, title, subtitle=None):
        """
            Export performance indicators

            Args:
                resource: the CRUDResource
                sheet: the XLS worksheet to write to
                title: the title for the export
                subtitle: an optional subtitle (e.g. start+end dates)
        """

        write = self.write
        rowindex = 0

        # Title
        write(sheet, rowindex, 0, title, style="header")
        rowindex += 1

        # Subtitle (optional)
        if subtitle:
            write(sheet, rowindex, 0, subtitle)
            rowindex += 2
        else:
            rowindex += 1

        indicators = (
            (1, "Anzahl der Beratungen", "consultations", "total"),
            (2, "Anzahl der beratenen Personen", "clients", "total"),
            (3, "Anzahl der Beratungen pro VZÄ (Durchschnitt)", "consultations", "per_fte"),
            (4, "Anzahl aller Männer", "clients", "gender", "male"),
            (5, "Anzahl aller Frauen", "clients", "gender", "female"),
            (6, "Anzahl aller Divers", "clients", "gender", "diverse"),
            (7, "Anzahl aller Personen bis zum vollendeten 18. Lebensjahr", "clients", "age_group", "u18"),
            (8, "Anzahl aller Personen vom vollendeten 18. bis zum vollendeten 27. Lebensjahr", "clients", "age_group", "18-27"),
            (9, "Anzahl aller Personen über dem vollendeten 65. Lebensjahr", "clients", "age_group", "65+"),
            (10, "Anzahl aller beratenen Personen aus Syrien", "clients", "nationality", "SY"),
            (11, "Anzahl aller beratenen Personen aus Afghanistan", "clients", "nationality", "AF"),
            (12, "Anzahl aller beratenen Personen aus Türkei", "clients", "nationality", "TR"),
            (13, "Anzahl aller beratenen Personen aus Georgien", "clients", "nationality", "GE"),
            (14, "Anzahl aller beratenen Personen aus Iran", "clients", "nationality", "IR"),
            (15, "Anzahl aller beratenen Personen aus Irak", "clients", "nationality", "IQ"),
            (16, "Anzahl aller beratenen Personen aus Russische Föderation", "clients", "nationality", "RU"),
            (17, "Anzahl aller beratenen Personen aus Nordmazedonien", "clients", "nationality", "MK"),
            (18, "Anzahl aller beratenen Personen aus Venezuela", "clients", "nationality", "VE"),
            (19, "Anzahl aller beratenen Personen aus Somalia", "clients", "nationality", "SO"),
            (20, "Anzahl aller beratenen Personen aus Eritrea", "clients", "nationality", "ER"),
            (21, "Anzahl aller beratenen Personen aus Algerien", "clients", "nationality", "DZ"),
            (22, "Anzahl aller beratenen Personen aus Kolumbien", "clients", "nationality", "CO"),
            (23, "Anzahl aller beratenen Personen aus Tunesien", "clients", "nationality", "TN"),
            (24, "Anzahl aller beratenen Personen aus Nigeria", "clients", "nationality", "NG"),
            (25, "Anzahl aller beratenen Personen aus Ungeklärt", "clients", "nationality", "??"),
            (26, "Anzahl aller beratenen Personen aus Indien", "clients", "nationality", "IN"),
            (27, "Anzahl aller beratenen Personen aus Pakistan", "clients", "nationality", "PK"),
            (28, "Anzahl aller beratenen Personen aus Ägypten", "clients", "nationality", "EG"),
            (29, "Anzahl aller beratenen Personen aus Serbien", "clients", "nationality", "RS"),
            (30, "Anzahl aller beratenen Personen aus anderen Staaten", "clients", "nationality", "*"),
            (31, "Anzahl der Fälle bei denen eine Weiterleitung zu Beratungsstelle stattgefunden hat", "referrals", "total"),
            (32, "Anzahl der Weiterleitung von Meldebögen zu Vulnerabilitäten an BAMF", "vulnerabilities", "VRBAMF", "reports"),
            (33, "Davon Anzahl der Fälle zu unbegleiteten minderjährigen Ausländern", "vulnerabilities", "VRBAMF", "cases", "UAM"),
            (34, "Davon Anzahl der Fälle zu sexueller Orientierung oder geschlechtlicher Identität", "vulnerabilities", "VRBAMF", "cases", "LGBQTi"),
            (35, "Davon Anzahl der Fälle zu Opfer von Menschenhandel", "vulnerabilities", "VRBAMF", "cases", "VHT"),
            (36, "Davon Anzahl der Fälle zu Opfer von Folter, Vergewaltigung oder sonstigen schweren Formen psychischer, physischer oder sexueller Gewalt", "vulnerabilities", "VRBAMF", "cases", "VT"),
            (37, "Davon Anzahl der Fälle zu Behinderung", "vulnerabilities", "VRBAMF", "cases", "DISAB"),
            (38, "Davon Anzahl der Fälle die keiner der oben genannten Kategorien zugewiesen werden kann", "vulnerabilities", "VRBAMF", "cases", "*"),
            (39, "Anzahl der Weiterleitung von Vulnerabilitäten an Aufnahmeeinrichtungen", "vulnerabilities", "VRRP", "reports"),
            (40, "Davon Anzahl der Fälle zu unbegleiteten minderjährigen Ausländern", "vulnerabilities", "VRRP", "cases", "UAM"),
            (41, "Davon Anzahl der Fälle zu sexueller Orientierung oder geschlechtlicher identität", "vulnerabilities", "VRRP", "cases", "LGBQTi"),
            (42, "Davon Anzahl der Fälle zu Opfer von Menschenhandel", "vulnerabilities", "VRRP", "cases", "VHT"),
            (43, "Davon Anzahl der Fälle zu Opfer von Folter, Vergewaltigung oder sonstigen schweren Formen psychischer, physischer oder sexueller Gewalt", "vulnerabilities", "VRRP", "cases", "VT"),
            (44, "Davon Anzahl der Fälle zu Behinderung", "vulnerabilities", "VRRP", "cases", "DISAB"),
            (45, "Davon Anzahl der Fälle die keiner der oben genannten Kategorien zugewiesen werden kann", "vulnerabilities", "VRRP", "cases", "*"),
            (46, "Anzahl der Beratungen mit dem Themenschwerpunkt Anhörung", "themes", "HEARING"),
            (47, "Anzahl der Beratungen mit dem Themenschwerpunkt Bescheid", "themes", "DECISION"),
            (48, "Anzahl der Beratungen mit dem Themenschwerpunkt Klage", "themes", "COMPLAINT"),
            (49, "Anzahl der Beratungen mit dem Themenschwerpunkt Dublin", "themes", "DUBLIN"),
            (50, "Anzahl der Beratungen mit dem Themenschwerpunkt Sonstiges", "themes", "*"),
            (51, "Anzahl der Erstgespräche (Erstes Beratungsgespräch eines Falles) gesamt", "followups", "initial"),
            (52, "Anzahl der Folgegespräche (Beratungen nach Erstberatung eines Falles) gesamt", "followups", "followup"),
            (53, "Anzahl der Beratungen mit einer Beratungszeit unter 15 Minuten", "efforts", "<15min"),
            (54, "Anzahl der Beratungen mit einer Beratungszeit unter 30 Minuten", "efforts", "<30min"),
            (55, "Anzahl der Beratungen mit einer Beratungszeit unter 60 Minuten", "efforts", "<60min"),
            )
        data = self.compute(resource)

        for indicator in indicators:
            index, title = indicator[:2]

            items = data
            for key in indicator[2:-1]:
                items = items.get(key)
                if items is None:
                    break
            value = items.get(indicator[-1], 0) if items else 0

            write(sheet, rowindex, 0, index)
            if value is not None:
                write(sheet, rowindex, 1, value)
            write(sheet, rowindex, 2, title)
            rowindex += 1

    # -------------------------------------------------------------------------
    # Client indicators
    # -------------------------------------------------------------------------
    def clients(self, subset):
        """
            Indicators for clients

            Args:
                subset: the dvr_response_action subset (list of record IDs)

            Returns:
                indicator dict

            Indicators:
                # 2 Anzahl der beratenen Personen
                + other client indicators
        """

        s3db = current.s3db
        atable = s3db.dvr_response_action

        # Include actions with indirect closure
        dbset = self.dbset(subset, indirect_closure=True)

        clients = {}

        num_clients = atable.person_id.count(distinct=True)
        row = dbset.select(num_clients).first()

        clients["total"] = row[num_clients]
        clients["gender"] = self.clients_by_gender(dbset)
        clients["age_group"] = self.clients_by_age_group(dbset)
        clients["nationality"] = self.clients_by_nationality(dbset)

        return clients

    # -------------------------------------------------------------------------
    @staticmethod
    def clients_by_gender(dbset):
        """
            Indicators for clients by gender

            Args:
                subset: the dvr_response_action subset (list of record IDs)

            Returns:
                indicator dict

            Indicators:
                # 4 Anzahl aller Männer
                # 5 Anzahl aller Frauen
                # 6 Anzahl aller Divers
        """

        gender_groups = (("male", 3), ("female", 2), ("diverse", 4))

        s3db = current.s3db

        atable = s3db.dvr_response_action
        ptable = s3db.pr_person
        join = ptable.on(ptable.id == atable.person_id)

        num_clients = ptable.id.count(distinct=True)
        rows = dbset.select(num_clients,
                            ptable.gender,
                            join = join,
                            groupby = ptable.gender,
                            )
        clients = {}
        for row in rows:
            clients[row.pr_person.gender] = row[num_clients]

        return {k: clients.get(v, 0) for k, v in gender_groups}

    # -------------------------------------------------------------------------
    @staticmethod
    def clients_by_age_group(dbset):
        """
            Indicators for clients by age group

            Args:
                subset: the dvr_response_action subset (list of record IDs)

            Returns:
                indicator dict

            Indicators:
                # 7 Anzahl aller Personen bis zum vollendeten 18. Lebensjahr
                # 8 Anzahl aller Personen vom vollendeten 18. bis zum vollendeten 27. Lebensjahr
                # 9 Anzahl aller Personen über dem vollendeten 65. Lebensjahr
        """

        age_groups = {(0, 18): 0, (18, 27): 0, (27, 65): 0, (65, None): 0}

        s3db = current.s3db

        atable = s3db.dvr_response_action
        ptable = s3db.pr_person
        join = ptable.on((ptable.id == atable.person_id) & \
                         (ptable.date_of_birth != None))

        dob = ptable.date_of_birth.max()
        doi = atable.date.min() # first consultation of the client

        rows = dbset.select(ptable.id,
                            dob,
                            doi,
                            join = join,
                            groupby = ptable.id,
                            )
        for row in rows:
            age = relativedelta(row[doi], row[dob]).years
            for g in age_groups:
                if age >= g[0] and (g[1] is None or age < g[1]):
                    age_groups[g] += 1

        return {"u18": age_groups[(0, 18)],
                "18-27": age_groups[(18, 27)],
                "27-65": age_groups[(27, 65)],
                "65+": age_groups[(65, None)],
                }

    # -------------------------------------------------------------------------
    @staticmethod
    def clients_by_nationality(dbset):
        """
            Indicators for clients by nationality

            Args:
                subset: the dvr_response_action subset (list of record IDs)

            Returns:
                indicator dict

            Indicators:
                # 10 Anzahl aller beratenen Personen aus Syrien
                # 11 Anzahl aller beratenen Personen aus Afghanistan
                # 12 Anzahl aller beratenen Personen aus Türkei
                # 13 Anzahl aller beratenen Personen aus Georgien
                # 14 Anzahl aller beratenen Personen aus Iran
                # 15 Anzahl aller beratenen Personen aus Irak
                # 16 Anzahl aller beratenen Personen aus Russische Föderation
                # 17 Anzahl aller beratenen Personen aus Nordmazedonien
                # 18 Anzahl aller beratenen Personen aus Venezuela
                # 19 Anzahl aller beratenen Personen aus Somalia
                # 20 Anzahl aller beratenen Personen aus Eritrea
                # 21 Anzahl aller beratenen Personen aus Algerien
                # 22 Anzahl aller beratenen Personen aus Kolumbien
                # 23 Anzahl aller beratenen Personen aus Tunesien
                # 24 Anzahl aller beratenen Personen aus Nigeria
                # 25 Anzahl aller beratenen Personen aus Ungeklärt
                # 26 Anzahl aller beratenen Personen aus Indien
                # 27 Anzahl aller beratenen Personen aus Pakistan
                # 28 Anzahl aller beratenen Personen aus Ägypten
                # 29 Anzahl aller beratenen Personen aus Serbien
                # 30 Anzahl aller beratenen Personen aus anderen Staaten
        """

        nationalities = ("SY", "AF", "TR", "GE", "IR", "IQ", "RU",
                         "MK", "VE", "SO", "ER", "DZ", "CO", "TN",
                         "NG", "??", "IN", "PK", "EG", "RS", "*",
                         )

        s3db = current.s3db

        atable = s3db.dvr_response_action
        dtable = s3db.pr_person_details
        left = dtable.on(dtable.person_id == atable.person_id)

        num_clients = atable.person_id.count(distinct=True)
        rows = dbset.select(num_clients,
                            dtable.nationality,
                            left = left,
                            groupby = dtable.nationality,
                            )
        clients = {n:0 for n in nationalities}
        for row in rows:
            nationality = row.pr_person_details.nationality
            if nationality is None:
                nationality = "??"
            if nationality not in nationalities:
                nationality = "*"
            clients[nationality] += row[num_clients]

        return clients

    # -------------------------------------------------------------------------
    # Consultation indicators
    # -------------------------------------------------------------------------
    def consultations(self, subset):
        """
            Indicators for consultation totals

            Args:
                subset: the dvr_response_action subset (list of record IDs)

            Returns:
                indicator dict

            Indicators:
                # 1 Anzahl der Beratungen
                # 3 Anzahl der Beratungen pro VZÄ (Durchschnitt)
        """

        s3db = current.s3db
        atable = s3db.dvr_response_action

        dbset = self.dbset(subset)

        num_actions = atable.id.count(distinct=True)
        row = dbset.select(num_actions).first()

        return {"total": row[num_actions], "per_fte": None}

    # -------------------------------------------------------------------------
    def referrals(self, subset):
        """
            Indicators for referrals

            Args:
                subset: the dvr_response_action subset (list of record IDs)

            Returns:
                indicator dict

            Indicators:
                # 31 Anzahl der Fälle bei denen eine Weiterleitung zu Beratungsstelle stattgefunden hat
        """

        response_type = "REF"

        s3db = current.s3db
        atable = s3db.dvr_response_action

        dbset = self.dbset(subset, code=response_type, consultation=False)

        num_actions = atable.id.count(distinct=True)
        row = dbset.select(num_actions).first()

        return {"total": row[num_actions],
                }

    # -------------------------------------------------------------------------
    def followups(self, subset):
        """
            Indicators for initial consultations / followups

            Args:
                subset: the dvr_response_action subset (list of record IDs)

            Returns:
                indicator dict

            Indicators:
                # 51 Anzahl der Erstgespräche (Erstes Beratungsgespräch eines Falles) gesamt
                # 52 Anzahl der Folgegespräche (Beratungen nach Erstberatung eines Falles) gesamt
        """

        response_types = {"initial": ("INI", "INI+I"),
                          "followup": ("FUP", "FUP+I"),
                          }

        result = {k: 0 for k in response_types}

        s3db = current.s3db
        atable = s3db.dvr_response_action

        for indicator, code in response_types.items():

            dbset = self.dbset(subset, code=code)
            num_actions = atable.id.count(distinct=True)

            row = dbset.select(num_actions).first()
            if row:
                result[indicator] += row[num_actions]

        return result

    # -------------------------------------------------------------------------
    def themes(self, subset):
        """
            Indicators for counseling reasons (by themes)

            Args:
                subset: the dvr_response_action subset (list of record IDs)

            Returns:
                indicator dict

            Indicators:
                # 46 Anzahl der Beratungen mit dem Themenschwerpunkt Anhörung
                # 47 Anzahl der Beratungen mit dem Themenschwerpunkt Bescheid
                # 48 Anzahl der Beratungen mit dem Themenschwerpunkt Klage
                # 49 Anzahl der Beratungen mit dem Themenschwerpunkt Dublin
                # 50 Anzahl der Beratungen mit dem Themenschwerpunkt Sonstiges
        """

        needs = ("HEARING", "DECISION", "COMPLAINT", "DUBLIN", "*")

        s3db = current.s3db
        atable = s3db.dvr_response_action
        ltable = s3db.dvr_response_action_theme
        ttable = s3db.dvr_response_theme
        ntable = s3db.dvr_need

        join = [ttable.on(ttable.id == ltable.theme_id),
                ntable.on(ntable.id == ttable.need_id),
                ]

        action_ids = self.dbset(subset)._select(atable.id)
        query = (ltable.action_id.belongs(action_ids)) & \
                (ltable.theme_id.belongs(self.theme_ids())) & \
                (ltable.deleted == False)

        num_actions = ltable.action_id.count(distinct=True)
        rows = current.db(query).select(ntable.code,
                                        num_actions,
                                        join = join,
                                        groupby = ntable.code,
                                        )

        result = {c: 0 for c in needs}
        for row in rows:
            code = row[ntable.code]
            if code in needs:
                result[code] = row[num_actions]
            else:
                result["*"] += row[num_actions]

        return result

    # -------------------------------------------------------------------------
    # Vulnerabilities indicators
    # -------------------------------------------------------------------------
    def vulnerabilities(self, subset):
        """
            Indicators for vulnerability reports

            Args:
                subset: the dvr_response_action subset (list of record IDs)

            Returns:
                indicator dict

            Indicators:
                # 32 Anzahl der Weiterleitung von Meldebögen zu Vulnerabilitäten an BAMF
                # 33 Davon Anzahl der Fälle zu unbegleiteten minderjährigen Ausländern
                # 34 Davon Anzahl der Fälle zu sexueller Orientierung oder geschlechtlicher Identität
                # 35 Davon Anzahl der Fälle zu Opfer von Menschenhandel
                # 36 Davon Anzahl der Falle infolge von Folter, Vergewaltigung oder sonstigen schweren Formen psychischer, physischer oder sexueller Gewalt
                # 37 Davon Anzahl der Fälle zu Behinderung
                # 38 Davon Anzahl der Fälle die keiner der oben genannten Kategorien zugewiesen werden kann
                # 39 Anzahl der Weiterleitung von Vulnerabilitäten an Aufnahmeeinrichtungen
                # 40 Davon Anzahl der Fälle zu unbegleiteten minderjährigen Ausländern
                # 41 Davon Anzahl der Fälle zu sexueller Orientierung oder geschlechtlicher identität
                # 42 Davon Anzahl der Fälle zu Opfer von Menschenhandel
                # 43 Davon Anzahl der Falle infolge von Folter, Vergewaltigung oder sonstigen schweren Formen psychischer, physischer oder sexueller Gewalt
                # 44 Davon Anzahl der Fälle zu Behinderung
                # 45 Davon Anzahl der Fälle die keiner der oben genannten Kategorien zugewiesen werden kann
        """

        response_types = ("VRBAMF", "VRRP")
        vulnerability_types = ("UAM", "LGBQTi", "VHT", "VT", "DISAB", "*")

        db = current.db
        s3db = current.s3db

        atable = s3db.dvr_response_action
        vtable = s3db.dvr_vulnerability
        ttable = s3db.dvr_vulnerability_type
        ltable = s3db.dvr_vulnerability_type_sector
        rtable = s3db.dvr_vulnerability_response_action

        reports = {}

        # All vulnerability types linked to self.sector
        query = (ltable.sector_id.belongs(self.sector_ids)) & \
                (ltable.deleted == False)
        type_ids = db(query)._select(ltable.vulnerability_type_id)

        query = (ttable.id.belongs(type_ids))
        rows = db(query).select(ttable.id, ttable.code)
        types = {row.id: row.code for row in rows}

        for code in response_types:
            dbset = self.dbset(subset, code=code, consultation=False)

            # Count all reports
            num_reports = atable.id.count(distinct=True)
            row = dbset.select(num_reports).first()
            output = {"reports": row[num_reports] if row else 0}

            # Count cases per vulnerability type
            # - where vulnerability is linked to the report
            join = [rtable.on((rtable.action_id == atable.id) & \
                              (rtable.deleted == False)),
                    vtable.on((vtable.id == rtable.vulnerability_id) & \
                              (vtable.person_id == atable.person_id) & \
                              (vtable.vulnerability_type_id.belongs(type_ids)) & \
                              (vtable.deleted == False)),
                    ]
            # Alternative join (if direct vulnerability<=>action links not available)
            # - where the vulnerability applied at the same time as the report
            #join = vtable.on((vtable.person_id == atable.person_id) & \
                             #(vtable.vulnerability_type_id.belongs(type_ids)) & \
                             #((vtable.date == None) | (vtable.date <= atable.start_date)) & \
                             #((vtable.end_date == None) | (vtable.end_date >= atable.start_date)) & \
                             #(vtable.deleted == False))
            type_id = vtable.vulnerability_type_id
            num_clients = vtable.person_id.count(distinct=True)
            rows = dbset.select(num_clients, type_id, join=join, groupby=type_id)

            # Sort by required vulnerability types
            cases = {k: 0 for k in vulnerability_types}
            for row in rows:
                vcode = types.get(row[type_id])
                if vcode not in cases:
                    vcode = "*"
                cases[vcode] += row[num_clients]
            output["cases"] = cases

            reports[code] = output

        return reports

    # -------------------------------------------------------------------------
    # Efforts indicators
    # -------------------------------------------------------------------------
    def efforts(self, subset):
        """
            Indicators for efforts

            Args:
                subset: the dvr_response_action subset (list of record IDs)

            Returns:
                indicator dict

            Indicators:
                # 53 Anzahl der Beratungen mit einer Beratungszeit unter 15 Minuten
                # 54 Anzahl der Beratungen mit einer Beratungszeit unter 30 Minuten
                # 55 Anzahl der Beratungen mit einer Beratungszeit unter 60 Minuten
        """

        db = current.db
        s3db = current.s3db

        atable = s3db.dvr_response_action
        ltable = s3db.dvr_response_action_theme

        dbset = self.dbset(subset)
        action_ids = dbset._select(atable.id)
        theme_ids = self.theme_ids()

        # All actions with any efforts recorded per-theme
        query = (ltable.action_id.belongs(action_ids)) & \
                (ltable.hours != None) & \
                (ltable.deleted == False)
        actions_with_theme_efforts = db(query)._select(ltable.action_id)

        # For these actions, compute the total effort for sector-related themes
        query = (ltable.action_id.belongs(actions_with_theme_efforts)) & \
                (ltable.theme_id.belongs(theme_ids)) & \
                (ltable.deleted == False)
        action_id = ltable.action_id
        total_hours = ltable.hours.sum()
        rows = db(query).select(action_id,
                                total_hours,
                                groupby = action_id,
                                )
        efforts = {row[action_id]: row[total_hours] for row in rows}

        # For all other actions in the set...
        query = (~atable.id.belongs(efforts.keys())) & (atable.hours != None)

        # ...determine the total effort and the total number of theme links
        left = ltable.on((ltable.action_id == atable.id) & \
                         (ltable.deleted == False))
        action_id = atable.id
        total_hours = atable.hours.max()
        num_links = ltable.id.count()
        rows = dbset(query).select(action_id,
                                   total_hours,
                                   num_links,
                                   left = left,
                                   groupby = action_id,
                                   )

        # ...compute average per-theme effort per action
        per_theme_efforts = {}
        for row in rows:
            record_id = row[action_id]
            hours = row[total_hours]
            links = row[num_links]
            per_theme_efforts[record_id] = hours / links if links else 0

        # ...determine the number of links to sector-related themes per action
        left = ltable.on((ltable.action_id == atable.id) & \
                         (ltable.theme_id.belongs(theme_ids)) & \
                         (ltable.deleted == False))
        rows = dbset(query).select(action_id,
                                   num_links,
                                   left = left,
                                   groupby = action_id,
                                   having = num_links > 0,
                                   )

        # From this, calculate an estimate for the total effort
        # for sector-related themes per action
        for row in rows:
            record_id = row[action_id]
            if record_id not in efforts:
                efforts[record_id] = per_theme_efforts.get(record_id, 0) * row[num_links]

        # Count actions per effort limit group
        groups = (("<15min", 0.25), ("<30min", 0.5), ("<60min", 1.0))
        result = {k: 0 for k, _ in groups}
        for record_id, hours in efforts.items():
            for indicator, limit in groups:
                if hours is None or hours < limit:
                    result[indicator] += 1
                    break

        return result

# =============================================================================
class PerformanceIndicatorExport(CRUDMethod):
    """ REST Method to produce a response statistics data sheet """

    # Custom Performance Indicator Sets
    PISETS = {"default": PerformanceIndicators,
              "bamf": PerformanceIndicatorsBAMF,
              }

    def __init__(self, pitype=None):
        """
            Args:
                pitype: the performance indicator set
        """

        super().__init__()

        self.suffix = pitype

        indicators = self.PISETS.get(pitype) if pitype else None

        if indicators:
            self.indicators = indicators()
        else:
            # Default Set
            self.indicators = PerformanceIndicators()

    # -------------------------------------------------------------------------
    def apply_method(self, r, **attr):
        """
            Page-render entry point for REST interface.

            Args:
                r: the CRUDRequest instance
                attr: controller attributes
        """

        output = {}

        if r.http == "GET":
            if r.representation == "xls":
                output = self.xls(r, **attr)
            else:
                r.error(415, current.ERROR.BAD_FORMAT)
        else:
            r.error(405, current.ERROR.BAD_METHOD)

        return output

    # -------------------------------------------------------------------------
    def xls(self, r, **attr):
        """
            Export the performance indicators as XLS data sheet

            Args:
                r: the CRUDRequest instance
                attr: controller attributes
        """

        try:
            import xlwt
        except ImportError as e:
            raise HTTP(503, body="XLWT not installed") from e

        T = current.T
        resource = self.resource
        table = resource.table

        # Get the statistics
        indicators = self.indicators

        # Create workbook and sheet
        book = xlwt.Workbook(encoding="utf-8")

        title = indicators.title
        if not title:
            title = T("Performance Indicators")
        title = s3_str(title)
        sheet = book.add_sheet(title)

        # Title and Report Dates (from filter)
        dates = []
        get_vars = r.get_vars
        field = table.date
        for fvar in ("~.start_date__ge", "~.start_date__le"):
            dtstr = get_vars.get(fvar)
            if dtstr:
                try:
                    dt = s3_decode_iso_datetime(dtstr).date()
                except (ValueError, AttributeError):
                    dt = None
                else:
                    dates.append(field.represent(dt))
            else:
                dates.append("...")
        dates = " -- ".join(dates) if dates else None

        # Write the performance indicators
        indicators.export(resource, sheet, title, subtitle=dates)

        # Output
        output = BytesIO()
        book.save(output)
        output.seek(0)

        # Filename
        suffix = self.suffix
        filename = ("indicators_%s.xls" % suffix) if suffix else "indicators.xls"

        # Response headers
        from gluon.contenttype import contenttype
        disposition = "attachment; filename=\"%s\"" % filename
        response = current.response
        response.headers["Content-Type"] = contenttype(".xls")
        response.headers["Content-disposition"] = disposition

        from gluon.streamer import DEFAULT_CHUNK_SIZE
        return response.stream(output,
                               chunk_size=DEFAULT_CHUNK_SIZE,
                               request=r,
                               )

# END =========================================================================
