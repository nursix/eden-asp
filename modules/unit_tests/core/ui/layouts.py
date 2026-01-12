# Layouts Unit Tests
#
# To run this script use:
# python web2py.py -S eden -M -R applications/eden/modules/unit_tests/modules/core.ui.layouts_tests.py
#
import unittest

from gluon import current
from core.ui.layouts import *

from unit_tests import run_suite

# =============================================================================
class LayoutTests(unittest.TestCase):
    """ Layout Tests """

    # -------------------------------------------------------------------------
    def testHomepageFunction(self):
        """ Test homepage() navigation item """

        # Test existing module
        hp = homepage("pr")
        self.assertTrue(hp is not None)

        # Test non-existent (deactivated) module
        hp = homepage("nonexistent")
        self.assertTrue(hp is not None)
        self.assertFalse(hp.check_active())
        rendered_hp = hp.xml()
        self.assertEqual(rendered_hp, "")

    # -------------------------------------------------------------------------
    def testPopupLink(self):
        """ Test PopupLink """

        auth = current.auth
        deployment_settings = current.deployment_settings

        comment = PopupLink(c="pr", f="person")

        # If the module is active, the comment should always be active
        self.assertEqual(comment.check_active(),
                         deployment_settings.has_module("pr"))
        self.assertEqual(comment.method, "create")

        # Label should fall back to CRUD string
        from core import get_crud_string
        crud_string = get_crud_string("pr_person", "label_create")
        self.assertEqual(comment.label, crud_string)

        if "inv" in deployment_settings.modules:
            comment = PopupLink(c="inv", f="inv_item")
            # Deactivate module
            inv = deployment_settings.modules["inv"]
            del deployment_settings.modules["inv"]
            # Comment should auto-deactivate
            self.assertFalse(comment.check_active())
            # Restore module
            deployment_settings.modules["inv"] = inv
            # Comment should auto-reactivate
            self.assertTrue(comment.check_active())

        self.assertFalse(comment.check_permission())
        self.assertEqual(comment.xml(), "")
        auth.s3_impersonate("admin@example.com")
        self.assertTrue(comment.check_permission())
        output = comment.xml()
        self.assertTrue(type(output) in (str, bytes))
        self.assertNotEqual(output, "")
        auth.s3_impersonate(None)

# =============================================================================
if __name__ == "__main__":

    run_suite(
        LayoutTests,
    )

# END ========================================================================
