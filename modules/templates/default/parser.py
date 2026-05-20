"""
    Message Parsing

    Template-specific Message Parsers are defined here.

    @copyright: 2012-2021 (c) Sahana Software Foundation
    @license: MIT

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

__all__ = ("S3Parser",)

#import re

#import pyparsing
try:
    import nltk
    from nltk.corpus import wordnet as wn
    NLTK = True
except:
    NLTK = False

from gluon import current
from gluon.tools import fetch

from core import S3Represent
from core.msg.parser import S3Parsing

# =============================================================================
class S3Parser:
    """
       Message Parsing Template
    """

    # -------------------------------------------------------------------------
    @staticmethod
    def parse_email(message):
        """
            Parse Responses
                - parse responses to mails from the Monitor service
        """

        reply = None

        db = current.db
        s3db = current.s3db

        # Need to use Raw currently as not showing in Body
        message_id = message.message_id
        table = s3db.msg_email
        record = db(table.message_id == message_id).select(table.raw,
                                                           limitby=(0, 1)
                                                           ).first()
        if not record:
            return reply

        message_body = record.raw
        if not message_body:
            return reply

        # What type of message is this?
        if ":run_id:" in message_body:
            # Response to Monitor Check

            # Parse Mail
            try:
                run_id = S3Parser._parse_value(message_body, "run_id")
                run_id = int(run_id)
            except:
                return reply

            # Update the Run entry to show that we have received the reply OK
            rtable = s3db.monitor_run
            db(rtable.id == run_id).update(result = "Reply Received",
                                           status = 1)
            return reply

        else:
            # Don't know what this is: ignore
            return reply

    # -------------------------------------------------------------------------
    def search_resource(self, message):
        """
            1st Pass Parser for searching resources
            - currently supports people, hospitals and organisations.
        """

        message_body = message.body
        if not message_body:
            return None

        pquery, name = self._parse_keywords(message_body)

        if "person" in pquery:
            reply = self.search_person(message, pquery, name)
        elif "hospital" in pquery:
            reply = self.search_hospital(message, pquery, name)
        elif "organisation" in pquery:
            reply = self.search_organisation(message, pquery, name)
        else:
            reply = None

        return reply

    # -------------------------------------------------------------------------
    def search_person(self, message, pquery=None, name=None):
        """
            Search for People
           - can be called direct
           - can be called from search_resource
        """

        message_body = message.body
        if not message_body:
            return None

        if not pquery or not name:
            pquery, name = self._parse_keywords(message_body)

        T = current.T
        db = current.db
        s3db = current.s3db

        reply = None
        result = []

        # Person Search [get name person phone email]
        s3_accessible_query = current.auth.s3_accessible_query
        table = s3db.pr_person
        query = (table.deleted == False) & \
                (s3_accessible_query("read", table))
        rows = db(query).select(table.pe_id,
                                table.first_name,
                                table.middle_name,
                                table.last_name)
        soundex = self._soundex
        _name = soundex(str(name))
        for row in rows:
            if (_name == soundex(row.first_name)) or \
               (_name == soundex(row.middle_name)) or \
               (_name == soundex(row.last_name)):
                presult = dict(name = row.first_name, id = row.pe_id)
                result.append(presult)

        if len(result) == 0:
            return T("No Match")

        elif len(result) > 1:
            return T("Multiple Matches")

        else:
            # Single Match
            reply = result[0]["name"]
            table = s3db.pr_contact
            if "email" in pquery:
                query = (table.pe_id == result[0]["id"]) & \
                        (table.contact_method == "EMAIL") & \
                        (s3_accessible_query("read", table))
                recipient = db(query).select(table.value,
                                             orderby = table.priority,
                                             limitby=(0, 1)).first()
                if recipient:
                    reply = "%s Email->%s" % (reply, recipient.value)
                else:
                    reply = "%s 's Email Not available!" % reply
            if "phone" in pquery:
                query = (table.pe_id == result[0]["id"]) & \
                        (table.contact_method == "SMS") & \
                        (s3_accessible_query("read", table))
                recipient = db(query).select(table.value,
                                             orderby = table.priority,
                                             limitby=(0, 1)).first()
                if recipient:
                    reply = "%s Mobile->%s" % (reply,
                                               recipient.value)
                else:
                    reply = "%s 's Mobile Contact Not available!" % reply

        return reply

    # ---------------------------------------------------------------------
    def search_hospital(self, message, pquery=None, name=None):
        """
           Search for Hospitals
           - can be called direct
           - can be called from search_resource
        """

        message_body = message.body
        if not message_body:
            return None

        if not pquery or not name:
            pquery, name = self._parse_keywords(message_body)

        T = current.T
        db = current.db
        s3db = current.s3db

        reply = None
        result = []

        #  Hospital Search [example: get name hospital facility status ]
        table = s3db.hms_hospital
        stable = s3db.hms_status
        query = (table.deleted == False) & \
                (current.auth.s3_accessible_query("read", table))
        rows = db(query).select(table.id,
                                table.name,
                                table.aka1,
                                table.aka2,
                                table.phone_emergency
                                )
        soundex = self._soundex
        _name = soundex(str(name))
        for row in rows:
            if (_name == soundex(row.name)) or \
               (_name == soundex(row.aka1)) or \
               (_name == soundex(row.aka2)):
                result.append(row)

        if len(result) == 0:
            return T("No Match")

        elif len(result) > 1:
            return T("Multiple Matches")

        else:
            # Single Match
            hospital = result[0]
            status = db(stable.hospital_id == hospital.id).select(stable.facility_status,
                                                                  stable.clinical_status,
                                                                  stable.security_status,
                                                                  limitby=(0, 1)
                                                                  ).first()
            reply = "%s %s (%s) " % (reply, hospital.name, T("Hospital"))
            if "phone" in pquery:
                reply = reply + "Phone->" + str(hospital.phone_emergency)
            if "facility" in pquery:
                reply = reply + "Facility status " + \
                        str(stable.facility_status.represent(status.facility_status))
            if "clinical" in pquery:
                reply = reply + "Clinical status " + \
                        str(stable.clinical_status.represent(status.clinical_status))
            if "security" in pquery:
                reply = reply + "Security status " + \
                        str(stable.security_status.represent(status.security_status))

        return reply

    # ---------------------------------------------------------------------
    def search_organisation(self, message, pquery=None, name=None):
        """
           Search for Organisations
           - can be called direct
           - can be called from search_resource
        """

        message_body = message.body
        if not message_body:
            return None

        if not pquery or not name:
            pquery, name = self._parse_keywords(message_body)

        T = current.T
        db = current.db
        s3db = current.s3db

        reply = None
        result = []

        # Organization search [example: get name organisation phone]
        s3_accessible_query = current.auth.s3_accessible_query
        table = s3db.org_organisation
        query = (table.deleted == False) & \
                (s3_accessible_query("read", table))
        rows = db(query).select(table.id,
                                table.name,
                                table.phone,
                                table.acronym)
        soundex = self._soundex
        _name = soundex(str(name))
        for row in rows:
            if (_name == soundex(row.name)) or \
               (_name == soundex(row.acronym)):
                result.append(row)

        if len(reply) == 0:
            return T("No Match")

        elif len(result) > 1:
            return T("Multiple Matches")

        else:
            # Single Match
            org = result[0]
            reply = "%s %s (%s) " % (reply, org.name,
                                     T("Organization"))
            if "phone" in pquery:
                reply = reply + "Phone->" + str(org.phone)
            if "office" in pquery:
                otable = s3db.org_office
                query = (otable.organisation_id == org.id) & \
                        (s3_accessible_query("read", otable))
                office = db(query).select(otable.address,
                                          limitby=(0, 1)).first()
                reply = reply + "Address->" + office.address

        return reply

    # -------------------------------------------------------------------------
    def parse_ireport(self, message):
        """
            Parse Messages directed to the IRS Module
            - logging new incidents
            - responses to deployment requests
        """

        message_body = message.body
        if not message_body:
            return None

        (lat, lon, code, text) = current.msg.parse_opengeosms(message_body)

        if code == "SI":
            # Create New Incident Report
            reply = self._create_ireport(lat, lon, text)
        else:
            # Is this a Response to a Deployment Request?
            words = message_body.split(" ")
            text = ""
            reponse = ""
            report_id = None
            comments = False
            soundex = self._soundex
            for word in words:
                if "SI#" in word and not ireport:
                    report = word.split("#")[1]
                    report_id = int(report)
                elif (soundex(word) == soundex("Yes")) and report_id \
                                                        and not comments:
                    response = True
                    comments = True
                elif soundex(word) == soundex("No") and report_id \
                                                    and not comments:
                    response = False
                    comments = True
                elif comments:
                    text += word + " "

            if report_id:
                reply = self._respond_drequest(message, report_id, response, text)
            else:
                reply = None

        return reply

    # -------------------------------------------------------------------------
    @staticmethod
    def _create_ireport(lat, lon, text):
        """
            Create New Incident Report
        """

        s3db = current.s3db
        rtable = s3db.irs_ireport
        gtable = s3db.gis_location
        info = text.split(" ")
        name = info[len(info) - 1]
        category = ""
        for a in range(0, len(info) - 1):
            category = category + info[a] + " "

        #@ToDo: Check for an existing location in DB
        #records = db(gtable.id>0).select(gtable.id, \
        #                                 gtable.lat,
        #                                 gtable.lon)
        #for record in records:
        #   try:
        #	    if "%.6f"%record.lat == str(lat) and \
        #	        "%.6f"%record.lon == str(lon):
        #	        location_id = record.id
        #	        break
        #   except:
        #	    pass

        location_id = gtable.insert(name="Incident:%s" % name,
                                    lat=lat,
                                    lon=lon)
        rtable.insert(name=name,
                      message=text,
                      category=category,
                      location_id=location_id)

        # @ToDo: Include URL?
        reply = "Incident Report Logged!"
        return reply

    # -------------------------------------------------------------------------
    @staticmethod
    def _parse_keywords(message_body):
        """
            Parse Keywords
            - helper function for search_resource, etc
        """

        # Equivalent keywords in one list
        primary_keywords = ["get", "give", "show"]
        contact_keywords = ["email", "mobile", "facility", "clinical",
                            "security", "phone", "status", "hospital",
                            "person", "organisation"]

        pkeywords = primary_keywords + contact_keywords
        keywords = message_body.split(" ")
        pquery = []
        name = ""
        soundex = self._soundex
        for word in keywords:
            match = None
            for key in pkeywords:
                if soundex(key) == soundex(word):
                    match = key
                    break
            if match:
                pquery.append(match)
            else:
                name = word

        return pquery, name

    # -------------------------------------------------------------------------
    @staticmethod
    def _parse_value(text, fieldname):
        """
            Parse a value from a piece of text
        """

        parts = text.split(":%s:" % fieldname, 1)
        parts = parts[1].split(":", 1)
        result = parts[0]
        return result

    # -------------------------------------------------------------------------
    @staticmethod
    def _respond_drequest(message, report_id, response, text):
        """
            Parse Replies To Deployment Request
        """

        # Can we identify the Human Resource?
        hr_id = S3Parsing().lookup_human_resource(message.from_address)
        if hr_id:
            rtable = current.s3db.irs_ireport_human_resource
            query = (rtable.ireport_id == report_id) & \
                    (rtable.human_resource_id == hr_id)
            current.db(query).update(reply = text,
                                     response = response)
            reply = "Response Logged in the Report (Id: %d )" % report_id
        else:
            reply = None

        return reply

    # -------------------------------------------------------------------------
    def _soundex(name, len=4):
        """
            Code referenced from http://code.activestate.com/recipes/52213-soundex-algorithm/

            @todo: parameter description?
        """

        # digits holds the soundex values for the alphabet
        digits = "01230120022455012623010202"
        sndx = ""
        fc = ""

        # Translate alpha chars in name to soundex digits
        for c in name.upper():
            if c.isalpha():
                if not fc:
                    # remember first letter
                    fc = c
                d = digits[ord(c)-ord("A")]
                # duplicate consecutive soundex digits are skipped
                if not sndx or (d != sndx[-1]):
                    sndx += d

        # replace first digit with first alpha character
        sndx = fc + sndx[1:]

        # remove all 0s from the soundex code
        sndx = sndx.replace("0", "")

        # return soundex code padded to len characters
        return (sndx + (len * "0"))[:len]

# END =========================================================================
