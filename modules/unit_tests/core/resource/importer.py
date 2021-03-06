# Eden Unit Tests
#
# To run this script use:
# python web2py.py -S eden -M -R applications/eden/modules/unit_tests/core/resource/importer.py
#
import datetime
import json
import unittest

from gluon import *
from gluon.storage import Storage
from lxml import etree

from core import S3Duplicate, ImportItem, ImportJob, s3_meta_fields
from core.resource.importer import ObjectReferences

from unit_tests import run_suite

# =============================================================================
class ListStringImportTests(unittest.TestCase):

    def setUp(self):

        xmlstr = """
<s3xml>
    <resource name="gis_layer_feature" uuid="TestLayerFeature">
        <data field="name">TestLayerFeature</data>
        <data field="controller">gis</data>
        <data field="function">location</data>
        <data field="popup_fields" value="[&quot;test1&quot;, &quot;test2&quot;]"/>
    </resource>
</s3xml>"""

        self.tree = etree.ElementTree(etree.fromstring(xmlstr))
        current.auth.override = True

    def tearDown(self):

        current.auth.override = False
        current.db.rollback()

    # -------------------------------------------------------------------------
    def testListStringImport(self):
        """ Test import with list:string """

        db = current.db
        s3db = current.s3db

        resource = s3db.resource("gis_layer_feature")

        # Import the elements
        resource.import_xml(self.tree)

        # Check the record
        table = resource.table
        query = (table.uuid == "TestLayerFeature")
        row = db(query).select(table.popup_fields,
                               limitby=(0, 1)).first()
        self.assertTrue(isinstance(row.popup_fields, list))
        self.assertEqual(row.popup_fields, ['test1', 'test2'])

# =============================================================================
class DefaultApproverOverrideTests(unittest.TestCase):
    """ Test ability to override default approver in imports """

    def setUp(self):

        xmlstr = """
<s3xml>
    <resource name="org_organisation" uuid="DAOOrganisation1">
        <data field="name">DAOOrganisation1</data>
    </resource>
    <resource name="org_organisation" uuid="DAOOrganisation2" approved="false">
        <data field="name">DAOOrganisation2</data>
    </resource>
</s3xml>"""

        self.tree = etree.ElementTree(etree.fromstring(xmlstr))

    def tearDown(self):

        current.db.rollback()

    # -------------------------------------------------------------------------
    def testDefaultApproverOverride(self):
        """ Test import with approve-attribute """

        db = current.db
        s3db = current.s3db

        current.auth.override = True

        resource = s3db.resource("org_organisation")

        # Check default approver
        self.assertEqual(resource.table.approved_by.default, 0)

        # Import the elements
        resource.import_xml(self.tree)

        table = resource.table

        # Without approved-flag should be set to default approver
        query = (table.uuid == "DAOOrganisation1")
        row = db(query).select(table.approved_by, limitby=(0, 1)).first()
        self.assertEqual(row.approved_by, 0)

        # With approved-flag false should be set to None
        query = (table.uuid == "DAOOrganisation2")
        row = db(query).select(table.approved_by, limitby=(0, 1)).first()
        self.assertEqual(row.approved_by, None)

        current.auth.override = False

# =============================================================================
class ComponentDisambiguationTests(unittest.TestCase):
    """ Test component disambiguation using the alias-attribute """

    def setUp(self):

        xmlstr1 = """
<s3xml>
    <resource name="org_organisation">
        <data field="name">MasterOrg1</data>
        <resource name="org_organisation_branch" alias="branch">
            <reference field="branch_id" tuid="TUID_OF_THE_BRANCH_ORG"/>
        </resource>
    </resource>
    <resource name="org_organisation" tuid="TUID_OF_THE_BRANCH_ORG">
        <data field="name">BranchOrg1</data>
    </resource>
</s3xml>"""

        xmlstr2 = """
<s3xml>
    <resource name="org_organisation">
        <data field="name">BranchOrg2</data>
            <resource name="org_organisation_branch" alias="parent">
                <reference field="organisation_id" tuid="TUID_OF_THE_MASTER_ORG"/>
            </resource>
    </resource>
    <resource name="org_organisation" tuid="TUID_OF_THE_MASTER_ORG">
        <data field="name">MasterOrg2</data>
    </resource>
</s3xml>"""

        self.branch_tree = etree.ElementTree(etree.fromstring(xmlstr1))
        self.parent_tree = etree.ElementTree(etree.fromstring(xmlstr2))

    def tearDown(self):

        current.db.rollback()

    # -------------------------------------------------------------------------
    def testOrganisationBranchImport(self):
        """ Test import of organisation branches using alias-attribute """

        db = current.db
        s3db = current.s3db

        current.auth.override = True
        resource = s3db.resource("org_organisation")
        resource.import_xml(self.branch_tree)

        table = resource.table

        query = (table.name == "MasterOrg1")
        master = db(query).select(table._id, limitby=(0, 1)).first()
        self.assertNotEqual(master, None)

        query = (table.name == "BranchOrg1")
        branch = db(query).select(table._id, limitby=(0, 1)).first()
        self.assertNotEqual(branch, None)

        table = s3db.org_organisation_branch
        query = (table.organisation_id == master.id) & \
                (table.branch_id == branch.id)
        link = db(query).select(limitby=(0, 1)).first()
        self.assertNotEqual(link, None)

    # -------------------------------------------------------------------------
    def testParentImport(self):
        """ Test import of organisation parents using alias-attribute """

        db = current.db
        s3db = current.s3db

        current.auth.override = True
        resource = s3db.resource("org_organisation")
        resource.import_xml(self.parent_tree)

        table = resource.table

        query = (table.name == "MasterOrg2")
        master = db(query).select(table._id, limitby=(0, 1)).first()
        self.assertNotEqual(master, None)

        query = (table.name == "BranchOrg2")
        branch = db(query).select(table._id, limitby=(0, 1)).first()
        self.assertNotEqual(branch, None)

        table = s3db.org_organisation_branch
        query = (table.organisation_id == master.id) & \
                (table.branch_id == branch.id)
        link = db(query).select(limitby=(0, 1)).first()
        self.assertNotEqual(link, None)

# =============================================================================
class PostParseTests(unittest.TestCase):
    """ Test xml_post_parse hook """

    def setUp(self):

        current.auth.override = True
        self.pp = current.s3db.get_config("pr_person", "xml_post_parse")

    def tearDown(self):

        current.db.rollback()
        current.auth.override = False
        current.s3db.configure("pr_person", xml_post_parse=self.pp)

    # -------------------------------------------------------------------------
    def testDynamicDefaults(self):
        """ Test setting dynamic defaults with xml_post_parse """

        xmlstr = """
<s3xml>
    <resource name="pr_person">
        <data field="first_name">Test</data>
        <data field="last_name">PostParseAdd1</data>
    </resource>
    <resource name="pr_person">
        <data field="first_name">Test</data>
        <data field="last_name">PostParseAdd2</data>
        <data field="gender" value="3"/>
    </resource>
</s3xml>"""

        tree = etree.ElementTree(etree.fromstring(xmlstr))

        resource = current.s3db.resource("pr_person")

        def xml_post_parse(elem, record):
            record["_gender"] = 2 # set female as dynamic default

        resource.configure(xml_post_parse=xml_post_parse)
        resource.import_xml(tree)

        db = current.db
        table = resource.table
        query = (table.first_name == "Test") & \
                (table.last_name == "PostParseAdd1")
        row = db(query).select(table.id, table.gender).first()
        self.assertNotEqual(row, None)
        self.assertEqual(row.gender, 2)

        query = (table.first_name == "Test") & \
                (table.last_name == "PostParseAdd2")
        row = db(query).select(table.id, table.gender).first()
        self.assertNotEqual(row, None)
        self.assertEqual(row.gender, 3)

# =============================================================================
class FailedReferenceTests(unittest.TestCase):
    """ Test handling of failed references """

    def setUp(self):

        current.auth.override = True

    def tearDown(self):

        current.db.rollback()
        current.auth.override = False

    # -------------------------------------------------------------------------
    def testFailedReferenceExplicit(self):
        """ Test handling of failed explicit reference """

        xmlstr = """
<s3xml>
    <resource name="org_office">
        <data field="name">FRTestOffice1</data>
        <reference field="organisation_id">
            <resource name="org_organisation" uuid="TROX">
                <data field="name">FRTestOrgX</data>
            </resource>
        </reference>
        <reference field="location_id" resource="gis_location" tuid="FRLOCATION"/>
    </resource>
    <resource name="gis_location" tuid="FRLOCATION">
        <!-- Error -->
        <data field="lat">283746.285753</data>
        <data field="lon">172834.334556</data>
    </resource>
</s3xml>"""

        tree = etree.ElementTree(etree.fromstring(xmlstr))

        s3db = current.s3db

        org = s3db.resource("org_organisation", uid="TROX")
        before = org.count()

        resource = current.s3db.resource("org_office")
        result = resource.import_xml(tree)

        msg = json.loads(result.json_message())
        self.assertEqual(msg["status"], "failed")

        error_resources = list(msg["tree"].keys())
        self.assertEqual(len(error_resources), 2)
        self.assertTrue("$_gis_location" in error_resources)
        self.assertTrue("$_org_office" in error_resources)
        self.assertTrue("@error" in msg["tree"]["$_org_office"][0]["$k_location_id"])

        # Check rollback
        org = s3db.resource("org_organisation", uid="TROX")
        self.assertEqual(before, org.count())
        org.delete()

    # -------------------------------------------------------------------------
    def testFailedReferenceInline(self):
        """ Test handling of failed inline reference """

        xmlstr = """
<s3xml>
    <resource name="org_office">
        <data field="name">FRTestOffice2</data>
        <reference field="organisation_id">
            <resource name="org_organisation" uuid="TROY">
                <data field="name">FRTestOrgY</data>
            </resource>
        </reference>
        <reference field="location_id" resource="gis_location">
            <resource name="gis_location">
                <!-- Error -->
                <data field="lat">283746.285753</data>
                <data field="lon">172834.334556</data>
            </resource>
        </reference>
    </resource>
</s3xml>"""

        tree = etree.ElementTree(etree.fromstring(xmlstr))

        s3db = current.s3db

        org = s3db.resource("org_organisation", uid="TROY")
        before = org.count()

        resource = current.s3db.resource("org_office")
        result = resource.import_xml(tree)

        msg = json.loads(result.json_message())
        self.assertEqual(msg["status"], "failed")

        error_resources = list(msg["tree"].keys())
        self.assertEqual(len(error_resources), 2)
        self.assertTrue("$_gis_location" in error_resources)
        self.assertTrue("$_org_office" in error_resources)
        self.assertTrue("@error" in msg["tree"]["$_org_office"][0]["$k_location_id"])

        # Check rollback
        org = s3db.resource("org_organisation", uid="TROY")
        self.assertEqual(before, org.count())
        org.delete()

# =============================================================================
class DuplicateDetectionTests(unittest.TestCase):
    """ Test cases for S3Duplicate """

    @classmethod
    def setUpClass(cls):

        db = current.db

        # Define test table
        db.define_table("dedup_test",
                        Field("name"),
                        Field("secondary"),
                        *s3_meta_fields())

        # Create sample records
        samples = (
            {"uuid": "TEST0", "name": "Test0", "secondary": "SecondaryX"},
            {"uuid": "TEST1", "name": "test1", "secondary": "Secondary1"},
            {"uuid": "TEST2", "name": "Test2", "secondary": "seCondaryX"},
            {"uuid": "TEST3", "name": "Test3", "secondary": "Secondary3"},
            {"uuid": "TEST4", "name": "test4", "secondary": "Secondary4"},
        )
        table = db.dedup_test
        for data in samples:
            table.insert(**data)

        current.db.commit()

    @classmethod
    def tearDownClass(cls):

        db = current.db
        db.dedup_test.drop()
        db.commit()

    # -------------------------------------------------------------------------
    def setUp(self):

        # Create a dummy import job
        self.job = ImportJob(current.db.dedup_test)

        db = current.db
        table = db.dedup_test
        rows = db(table.id > 0).select(table.uuid, table.id)

        ids = {}
        uids = {}
        for row in rows:
            uids[row.id] = row.uuid
            ids[row.uuid] = row.id

        self.ids = ids
        self.uids = uids

    def tearDown(self):

        self.job = None
        self.ids = None
        self.uids = None

    # -------------------------------------------------------------------------
    def testMatch(self):
        """ Test match with primary/secondary field """

        assertEqual = self.assertEqual

        deduplicate = S3Duplicate(primary=("name",),
                                  secondary=("secondary",),
                                  )

        # Dummy item for testing
        item = ImportItem(self.job)
        item.table = current.db.dedup_test

        ids = self.ids

        # Test primary match
        item.id = None
        item.method = item.METHOD.CREATE
        item.data = Storage(name="Test0")

        deduplicate(item)
        assertEqual(item.id, ids["TEST0"])
        assertEqual(item.method, item.METHOD.UPDATE)

        # Test primary match + secondary match
        item.id = None
        item.method = item.METHOD.CREATE
        item.data = Storage(name="Test2", secondary="secondaryX")

        deduplicate(item)
        assertEqual(item.id, ids["TEST2"])
        assertEqual(item.method, item.METHOD.UPDATE)

        # Test primary match + secondary mismatch
        item.id = None
        item.method = item.METHOD.CREATE
        item.data = Storage(name="test4", secondary="secondaryX")

        deduplicate(item)
        assertEqual(item.id, None)
        assertEqual(item.method, item.METHOD.CREATE)

        # Test primary mismatch
        item.id = None
        item.method = item.METHOD.CREATE
        item.data = Storage(name="Test")

        deduplicate(item)
        assertEqual(item.id, None)
        assertEqual(item.method, item.METHOD.CREATE)

    # -------------------------------------------------------------------------
    def testDefaults(self):
        """ Test default behavior """

        assertEqual = self.assertEqual

        deduplicate = S3Duplicate()

        # Dummy item for testing
        item = ImportItem(self.job)
        item.table = current.db.dedup_test

        ids = self.ids

        # Test primary match
        item.id = None
        item.method = item.METHOD.CREATE
        item.data = Storage(name="Test0")

        deduplicate(item)
        assertEqual(item.id, ids["TEST0"])
        assertEqual(item.method, item.METHOD.UPDATE)

        # Test primary match + secondary mismatch
        item.id = None
        item.method = item.METHOD.CREATE
        item.data = Storage(name="test4", secondary="secondaryX")

        deduplicate(item)
        assertEqual(item.id, ids["TEST4"])
        assertEqual(item.method, item.METHOD.UPDATE)

        # Test primary mismatch
        item.id = None
        item.method = item.METHOD.CREATE
        item.data = Storage(name="Test")

        deduplicate(item)
        assertEqual(item.id, None)
        assertEqual(item.method, item.METHOD.CREATE)

    # -------------------------------------------------------------------------
    def testExceptions(self):
        """ Test S3Duplicate exceptions for nonexistent fields """

        assertRaises = self.assertRaises


        # Dummy item for testing
        item = ImportItem(self.job)
        item.table = current.db.dedup_test

        # Test invalid primary
        deduplicate = S3Duplicate(primary=("nonexistent",))
        item.id = None
        item.method = item.METHOD.CREATE
        item.data = Storage(name="Test0")

        with assertRaises(SyntaxError):
            deduplicate(item)

        # Test invalid secondary
        deduplicate = S3Duplicate(secondary=("nonexistent",))
        item.id = None
        item.method = item.METHOD.CREATE
        item.data = Storage(name="Test0")

        with assertRaises(SyntaxError):
            deduplicate(item)

        # Test invalid type
        with assertRaises(TypeError):
            deduplicate = S3Duplicate(primary=lambda: None)
        with assertRaises(TypeError):
            deduplicate = S3Duplicate(secondary=17)

# =============================================================================
class MtimeImportTests(unittest.TestCase):

    def setUp(self):

        current.auth.override = True

    def tearDown(self):

        current.auth.override = False
        current.db.rollback()

    # -------------------------------------------------------------------------
    def testMtimeImport(self):
        """
            Verify that create-postprocess does not overwrite
            imported modified_on
        """

        s3db = current.s3db

        assertEqual = self.assertEqual

        # Fixed modified_on date in the past
        mtime = datetime.datetime(1988, 8, 13, 10, 0, 0)

        xmlstr = """
<s3xml>
    <resource name="org_facility" modified_on="%(mtime)s" uuid="MTFAC">
        <data field="name">MtimeTestOffice</data>
        <reference field="organisation_id">
            <resource name="org_organisation" modified_on="%(mtime)s" uuid="MTORG">
                <data field="name">MtimeTestOrg</data>
            </resource>
        </reference>
    </resource>
</s3xml>""" % {"mtime": mtime.isoformat()}

        tree = etree.ElementTree(etree.fromstring(xmlstr))

        # Import the data
        resource = s3db.resource("org_facility")
        resource.import_xml(tree)

        # Verify outer resource
        resource = s3db.resource("org_facility", uid="MTFAC")
        row = resource.select(["id", "modified_on"], as_rows=True)[0]
        assertEqual(row.modified_on, mtime)

        # Verify inner resource
        resource = s3db.resource("org_organisation", uid="MTORG")
        row = resource.select(["id", "modified_on"], as_rows=True)[0]
        assertEqual(row.modified_on, mtime)

# =============================================================================
class ObjectReferencesTests(unittest.TestCase):
    """ Tests for ObjectReferences """

    # -------------------------------------------------------------------------
    def testDiscoverFromObject(self):
        """ Test reference discovery in object """

        assertTrue = self.assertTrue
        assertEqual = self.assertEqual

        obj = {"key_1": "value_1",
               "$k_key_2": {"@resource": "org_organisation",
                            "@tuid": "ORG1",
                            },
               "key3": "value_3",
               }

        refs = ObjectReferences(obj).refs

        assertTrue(isinstance(refs, list))
        assertEqual(len(refs), 1)

        ref = refs[0]
        assertEqual(len(ref), 3)
        assertEqual(ref[0], "org_organisation")
        assertEqual(ref[1], "tuid")
        assertEqual(ref[2], "ORG1")

    # -------------------------------------------------------------------------
    def testDiscoverFromList(self):
        """ Test reference discovery in list with objects """

        assertTrue = self.assertTrue
        assertEqual = self.assertEqual

        obj = ["item1",
               {"$k_key_2": {"@resource": "org_organisation",
                             "@uuid": "ORG1",
                             },
                },
               129384,
               None,
               ]

        refs = ObjectReferences(obj).refs

        assertTrue(isinstance(refs, list))
        assertEqual(len(refs), 1)

        ref = refs[0]
        assertEqual(len(ref), 3)
        assertEqual(ref[0], "org_organisation")
        assertEqual(ref[1], "uuid")
        assertEqual(ref[2], "ORG1")

    # -------------------------------------------------------------------------
    def testDiscoverFromNested(self):
        """ Test reference discovery in nested objects """

        assertTrue = self.assertTrue
        assertEqual = self.assertEqual

        obj = ["item1",
               {"complex": [{"someint": 3465,
                             "astring": "example",
                             },
                            {"$k_key_2": {"@resource": "pr_person",
                                          "@tuid": "PR2",
                                          },
                             "somebool": True,
                             },
                            ],
                },
               129384,
               None,
               ]

        refs = ObjectReferences(obj).refs

        assertTrue(isinstance(refs, list))
        assertEqual(len(refs), 1)

        ref = refs[0]
        assertEqual(len(ref), 3)
        assertEqual(ref[0], "pr_person")
        assertEqual(ref[1], "tuid")
        assertEqual(ref[2], "PR2")

    # -------------------------------------------------------------------------
    def testDiscoverMultiple(self):
        """ Test discovery of multiple references """

        assertTrue = self.assertTrue
        assertEqual = self.assertEqual
        assertIn = self.assertIn

        obj = ["item1",
               {"complex": [{"someint": 3465,
                             "astring": "example",
                             },
                            {"$k_key_2": {"@resource": "pr_person",
                                          "@tuid": "PR2",
                                          },
                             "somebool": True,
                             },
                            ],
                "$k_key_1": {"r": "org_organisation",
                             "u": "ORG1",
                             },
                },
               129384,
               None,
               ]

        refs = ObjectReferences(obj).refs

        assertTrue(isinstance(refs, list))
        assertEqual(len(refs), 2)

        for ref in refs:
            uid = ref[2]
            assertIn(uid, ("PR2", "ORG1"))
            if uid == "ORG1":
                assertEqual(ref[0], "org_organisation")
                assertEqual(ref[1], "uuid")
            else:
                assertEqual(ref[0], "pr_person")
                assertEqual(ref[1], "tuid")

    # -------------------------------------------------------------------------
    def testDiscoverInvalid(self):
        """ Test reference discovery in presence of invalid keys """

        assertTrue = self.assertTrue
        assertEqual = self.assertEqual

        obj = ["item1",
               {"$k_key_3": [{"someint": 3465,
                              "astring": "example",
                              },
                             {"$k_key_2": {"@resource": "req_req",
                                           "@uuid": "REQ0928",
                                           },
                              "somebool": True,
                              },
                             ],
                "$k_key_1": {"name": "org_organisation",
                             "id": "ORG1",
                             },
                },
               129384,
               None,
               ]

        refs = ObjectReferences(obj).refs

        assertTrue(isinstance(refs, list))
        assertEqual(len(refs), 1)

        ref = refs[0]
        assertEqual(len(ref), 3)
        assertEqual(ref[0], "req_req")
        assertEqual(ref[1], "uuid")
        assertEqual(ref[2], "REQ0928")

    # -------------------------------------------------------------------------
    def testResolveObject(self):
        """ Test reference resolution in an object """

        obj = {"key_1": "value_1",
               "$k_key_2": {"@resource": "org_organisation",
                            "@tuid": "ORG1",
                            },
               "key3": "value_3",
               }

        ObjectReferences(obj).resolve("org_organisation", "tuid", "ORG1", 57)

        target = obj
        self.assertNotIn("$k_key_2", target)
        self.assertIn("key_2", target)
        self.assertEqual(target["key_2"], 57)

    # -------------------------------------------------------------------------
    def testResolveList(self):
        """ Test reference resolution in a list with objects """

        obj = ["item1",
               {"$k_key_2": {"@resource": "org_organisation",
                             "@uuid": "ORG1",
                             },
                },
               129384,
               None,
               ]

        ObjectReferences(obj).resolve("org_organisation", "uuid", "ORG1", 57)

        target = obj[1]
        self.assertNotIn("$k_key_2", target)
        self.assertIn("key_2", target)
        self.assertEqual(target["key_2"], 57)

    # -------------------------------------------------------------------------
    def testResolveNested(self):
        """ Test reference resolution in nested objects """

        obj = ["item1",
               {"complex": [{"someint": 3465,
                             "astring": "example",
                             },
                            {"$k_key_2": {"@resource": "pr_person",
                                          "@tuid": "PR2",
                                          },
                             "somebool": True,
                             },
                            ],
                },
               129384,
               None,
               ]

        ObjectReferences(obj).resolve("pr_person", "tuid", "PR2", 3283)

        target = obj[1]["complex"][1]
        self.assertNotIn("$k_key_2", target)
        self.assertIn("key_2", target)
        self.assertEqual(target["key_2"], 3283)

    # -------------------------------------------------------------------------
    def testResolveMultiple(self):
        """ Test resolution of multiple references in nested objects """

        assertNotIn = self.assertNotIn
        assertIn = self.assertIn
        assertEqual = self.assertEqual

        obj = ["item1",
               {"complex": [{"someint": 3465,
                             "astring": "example",
                             },
                            {"$k_key_2": {"@resource": "pr_person",
                                          "@tuid": "PR2",
                                          },
                             "somebool": True,
                             },
                            ],
                "$k_key_1": {"r": "org_organisation",
                             "u": "ORG1",
                             },
                },
               129384,
               {"$k_key_3": {"r": "pr_person",
                             "t": "PR2",
                             },
                },
               ]

        refs = ObjectReferences(obj)
        refs.resolve("pr_person", "tuid", "PR2", 3283)
        refs.resolve("org_organisation", "uuid", "ORG1", 14)

        target = obj[1]["complex"][1]
        assertNotIn("$k_key_2", target)
        assertIn("key_2", target)
        assertEqual(target["key_2"], 3283)

        target = obj[3]
        assertNotIn("$k_key_3", target)
        assertIn("key_3", target)
        assertEqual(target["key_3"], 3283)

        target = obj[1]
        assertNotIn("$k_key_1", target)
        assertIn("key_1", target)
        assertEqual(target["key_1"], 14)

    # -------------------------------------------------------------------------
    def testResolveInvalid(self):
        """ Test reference resolution in nested objects with invalid keys """

        obj = ["item1",
               {"$k_key_3": [{"someint": 3465,
                              "astring": "example",
                              },
                             {"$k_key_2": {"@resource": "req_req",
                                           "@uuid": "REQ0928",
                                           },
                              "somebool": True,
                              },
                             ],
                "$k_key_1": {"name": "org_organisation",
                             "id": "ORG1",
                             },
                },
               129384,
               None,
               ]

        ObjectReferences(obj).resolve("req_req", "uuid", "REQ0928", 3)

        target = obj[1]["$k_key_3"][1]
        self.assertNotIn("$k_key_2", target)
        self.assertIn("key_2", target)
        self.assertEqual(target["key_2"], 3)

# =============================================================================
class ObjectReferencesImportTests(unittest.TestCase):
    """ Tests for import of references in JSON field values """

    @classmethod
    def setUpClass(cls):

        db = current.db

        # Define tables for test
        db.define_table("ort_master",
                        Field("jsontest", "json"),
                        *s3_meta_fields())
        db.define_table("ort_referenced",
                        Field("name"),
                        *s3_meta_fields())

        # Enable feature
        current.s3db.configure("ort_master",
                               json_references = "jsontest",
                               )

    @classmethod
    def tearDownClass(cls):

        db = current.db

        db.ort_referenced.drop()
        db.ort_master.drop()

        current.s3db.clear_config("ort_master")

    # -------------------------------------------------------------------------
    def setUp(self):

        current.auth.override = True

    def tearDown(self):

        current.auth.override = False

    # -------------------------------------------------------------------------
    def testImpliedImport(self):
        """ Verify that JSON references are scheduled for implicit import """

        assertEqual = self.assertEqual
        assertTrue = self.assertTrue

        xmlstr = """
<s3xml>
    <resource name="ort_master">
        <data field="jsontest">["item1",{"complex":[{"someint":3465,"astring":"example"},{"$k_key_2":{"@resource":"ort_referenced","@tuid":"REF1"},"somebool":true}]},129384,null]</data>
    </resource>
    <resource name="ort_referenced" tuid="REF1">
        <data field="name">Test</data>
    </resource>
</s3xml>"""

        # Create an import job
        tree = etree.fromstring(xmlstr)
        job = ImportJob(current.db.ort_master, tree)

        # Add the ort_master element to it
        element = tree.findall('resource[@name="ort_master"][1]')[0]
        job.add_item(element)

        # Verify that the ort_referenced item has been added implicitly
        items = job.items
        assertEqual(len(items), 2)
        for item_id, item in items.items():

            if str(item.table) == "ort_master":

                # Should be exactly one reference
                references = item.references
                assertEqual(len(references), 1)

                # ...in the "jsontest" field
                reference = references[0]
                assertEqual(reference.field, "jsontest")

                # Verify that the referenced item has been scheduled
                item_id = reference.entry.item_id
                assertTrue(item_id in items)

    # -------------------------------------------------------------------------
    def testReferenceResolution(self):
        """ Test resolution of JSON object references during import """

        db = current.db
        s3db = current.s3db

        import uuid
        muid = uuid.uuid4().urn
        name = uuid.uuid4().urn

        xmlstr = """
<s3xml>
    <resource name="ort_master" uuid="%s">
        <data field="jsontest">{"$k_referenced_id": {"r": "ort_referenced", "t": "REF1"}}</data>
    </resource>
    <resource name="ort_referenced" tuid="REF1">
        <data field="name">%s</data>
    </resource>
</s3xml>""" % (muid, name)

        tree = etree.ElementTree(etree.fromstring(xmlstr))

        resource = s3db.resource("ort_master")
        resource.import_xml(tree)

        # Get the ID of the referenced record
        table = s3db.ort_referenced
        row = db(table.name == name).select(table.id, limitby=(0, 1)).first()
        try:
            record_id = row.id
        except AttributeError:
            raise AssertionError("Referenced record not imported!")

        # Get the JSON object
        table = s3db.ort_master
        row = db(table.uuid == muid).select(table.jsontest, limitby=(0, 1)).first()

        # Inspect the JSON object, verify that the reference is resolved
        obj = row.jsontest
        self.assertNotIn("$k_referenced_id", obj)
        self.assertIn("referenced_id", obj)
        self.assertEqual(obj["referenced_id"], record_id)

# =============================================================================
class UIDCollisionHandlingTests(unittest.TestCase):
    """ Tests for imports with UID collisions """

    @classmethod
    def setUpClass(cls):

        db = current.db

        # Define tables for test
        db.define_table("tuid_type_1",
                        Field("name"),
                        *s3_meta_fields())
        db.define_table("tuid_type_2",
                        Field("name"),
                        *s3_meta_fields())
        db.define_table("tuid_master",
                        Field("name"),
                        Field("type1_id", "reference tuid_type_1"),
                        Field("type2_id", "reference tuid_type_2"),
                        *s3_meta_fields())

    @classmethod
    def tearDownClass(cls):

        db = current.db

        db.tuid_master.drop()
        db.tuid_type_1.drop()
        db.tuid_type_2.drop()

    # -------------------------------------------------------------------------
    def setUp(self):

        current.auth.override = True

        xmlstr = """
<s3xml>
    <resource name="tuid_type_1" tuid="TESTUID1">
        <data field="name">Test 1-a</data>
    </resource>
    <resource name="tuid_type_1" tuid="TESTUID2">
        <data field="name">Test 1-b</data>
    </resource>
    <resource name="tuid_type_1" tuid="TESTUID3">
        <data field="name">Test 1-c</data>
    </resource>
    <resource name="tuid_type_2" tuid="TESTUID1">
        <data field="name">Test 2-a</data>
    </resource>
    <resource name="tuid_type_2" tuid="TESTUID3">
        <data field="name">Test 2-c</data>
    </resource>
    <resource name="tuid_master">
        <reference field="type1_id" resource="tuid_type_1" tuid="TESTUID1"/>
        <reference field="type2_id" resource="tuid_type_2" tuid="TESTUID1"/>
    </resource>
    <resource name="tuid_master">
        <reference field="type1_id" resource="tuid_type_1" tuid="TESTUID2"/>
        <reference field="type2_id" resource="tuid_type_2" tuid="TESTUID3"/>
    </resource>
    <resource name="tuid_master">
        <reference field="type1_id" resource="tuid_type_1" tuid="TESTUID3"/>
        <reference field="type2_id" resource="tuid_type_2" tuid="TESTUID1"/>
    </resource>
    <resource name="tuid_master" uuid="TUIDMASTER">
        <reference field="type1_id" resource="tuid_type_1" tuid="TESTUID3"/>
        <reference field="type2_id" resource="tuid_type_2" tuid="TESTUID3"/>
    </resource>

</s3xml>"""

        tree = etree.ElementTree(etree.fromstring(xmlstr))

        # Import the data
        current.s3db.resource("tuid_master").import_xml(tree)

    def tearDown(self):

        current.auth.override = False

    # -------------------------------------------------------------------------
    def testCrossTypeTUIDCollision(self):
        """ Cross-type colliding TUIDs should be mapped correctly """

        db = current.db

        assertEqual = self.assertEqual
        assertNotEqual = self.assertNotEqual

        # Get the record ID of tuid_type_1 with name="Test 1-c"
        ttable = db.tuid_type_1
        query = (ttable.name == "Test 1-c")
        row = db(query).select(ttable.id, limitby=(0, 1)).first()
        assertNotEqual(row, None)
        type1_id = row.id

        # Get the record ID of tuid_type_2 with name="Test 2-c"
        ttable = db.tuid_type_2
        query = (ttable.name == "Test 2-c")
        row = db(query).select(ttable.id, limitby=(0, 1)).first()
        assertNotEqual(row, None)
        type2_id = row.id

        if type1_id != type2_id:
            # Verify that the references have been resolved into
            # the correct record IDs (NB this check is partially
            # redundant because the import would already fail if
            # the resolution did not work properly)

            # Get TUID master
            mtable = db.tuid_master
            query = (mtable.uuid == "TUIDMASTER")
            row = db(query).select(mtable.type1_id,
                                   mtable.type2_id,
                                   limitby = (0, 1),
                                   ).first()
            assertNotEqual(row, None)

            # Verify that IDs are correct
            assertEqual(row.type1_id, type1_id)
            assertEqual(row.type2_id, type2_id)

# =============================================================================
if __name__ == "__main__":

    run_suite(
        ListStringImportTests,
        DefaultApproverOverrideTests,
        ComponentDisambiguationTests,
        PostParseTests,
        FailedReferenceTests,
        DuplicateDetectionTests,
        MtimeImportTests,
        ObjectReferencesTests,
        ObjectReferencesImportTests,
        UIDCollisionHandlingTests,
        )

# END ========================================================================
