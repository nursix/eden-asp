"""
    Maintenance Tasks for BETRA

    License: MIT
"""

import datetime
import os
import time

from gluon import current
from gluon.settings import global_settings

# =============================================================================
class Daily():
    """ Daily Maintenance Tasks """

    def __call__(self):

        db = current.db
        s3db = current.s3db

        current.log.info("Daily Maintenance BETRA")

        now = datetime.datetime.utcnow()
        week_past = now - datetime.timedelta(weeks=1)

        # Cleanup Scheduler logs
        table = s3db.scheduler_run
        db(table.start_time < week_past).delete()

        # Cleanup Sync logs
        table = s3db.sync_log
        db(table.timestmp < week_past).delete()

        # Cleanup old sessions
        self.cleanup_sessions(ttl=1)

        # Cleanup unverified accounts
        self.cleanup_unverified_accounts()

    # -------------------------------------------------------------------------
    @staticmethod
    def cleanup_sessions(ttl=7):
        """
            Clean up old sessions

            Args:
                ttl: time-to-live for unused sessions (days)
        """

        request = current.request

        path_join = os.path.join
        folder = path_join(global_settings.applications_parent,
                           request.folder,
                           "sessions",
                           )

        now = datetime.datetime.utcnow()
        earliest = now - datetime.timedelta(days=ttl)
        earliest_u = time.mktime(earliest.timetuple())

        stat = os.stat
        listdir = os.listdir
        rm = os.remove
        rmdir = os.rmdir

        for path, sub, files in os.walk(folder, topdown=False):

            # Remove all session files with mtime before earliest
            for filename in files:
                filepath = path_join(path, filename)
                if stat(filepath).st_mtime < earliest_u:
                    try:
                        rm(filepath)
                    except Exception: # (OSError, FileNotFoundError):
                        pass

            # Remove empty subfolders
            for dirname in sub:
                dirpath = path_join(path, dirname)
                if not listdir(dirpath):
                    try:
                        rmdir(dirpath)
                    except Exception: # (OSError, FileNotFoundError):
                        pass

    # -------------------------------------------------------------------------
    @staticmethod
    def cleanup_unverified_accounts():
        """
            Remove unverified user accounts
        """

        db = current.db
        s3db = current.s3db
        auth = current.auth

        auth_settings = auth.settings

        now = datetime.datetime.utcnow()

        utable = auth_settings.table_user
        mtable = auth_settings.table_membership
        ttable = s3db.auth_user_temp
        ltable = s3db.pr_person_user

        left = [ltable.on(ltable.user_id == utable.id),
                mtable.on(mtable.user_id == utable.id),
                ]

        query = (utable.created_on < now - datetime.timedelta(hours=48)) & \
                (utable.registration_key != None) & \
                (~(utable.registration_key.belongs("", "disabled", "blocked", "pending"))) & \
                (utable.deleted == False) & \
                (ltable.id == None) & \
                (mtable.id == None)

        rows = db(query).select(utable.id,
                                utable.email,
                                left = left,
                                )
        for row in rows:

            email = row.email

            try:
                success = db(ttable.user_id == row.id).delete()
            except Exception:
                success = False
            if not success:
                current.log.warning("Could not delete temp data for user %s" % email)
                continue

            try:
                success = row.delete_record()
            except Exception:
                success = False
            if not success:
                current.log.warning("Could not delete unverified user %s" % email)

            current.log.info("Deleted unverified user account %s" % email)

# END =========================================================================
