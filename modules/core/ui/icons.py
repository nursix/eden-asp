"""
    Semantic Icons

    Copyright: 2009-2023 (c) Sahana Software Foundation

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

__all__ = ("ICON",
           )

from gluon import current, I

# =============================================================================
class ICON(I):
    """
        HTML helper to render <i> tags for icons, mapping semantic names
        to CSS classes. The standard icon set can be configured using

            - settings.ui.icons

        e.g. ICON("book"), gives:
            - font-awesome: <i class="icon icon-book">
            - foundation: <i class="fi-book">

        Standard sets are defined below.

        Additional icons (beyond the standard set) can be configured per
        deployment (settings.ui.custom_icons).

        If <i class=""> is not suitable for the CSS, a custom HTML layout can
        be configured as settings.ui.icon_layout. See S3Config for more details.

        TODO apply in widgets/crud/profile+datalist layouts etc.
        TODO better abstract names for the icons to indicate what they
             symbolize rather than what they depict, e.g. "sitemap" is
             typically used to symbolize an organisation => rename into
             "organisation".
    """

    # -------------------------------------------------------------------------
    # Standard icon sets,
    # - "_base" can be used to define a common CSS class for all icons
    #
    icons = {
        # Font-Awesome 4
        # https://fontawesome.com/v4.7.0/icons/
        "font-awesome": {
            "_base": "fa",
            "active": "fa-check",
            "activity": "fa-cogs",
            "add": "fa-plus",
            "administration": "fa-cog",
            "alert": "fa-bell",
            "arrow-down": "fa-arrow-down",
            "arrow-left": "fa-arrow-left",
            "arrow-right": "fa-arrow-right",
            "assessment": "fa-bar-chart",
            "asset": "fa-fire-extinguisher",
            "attachment": "fa-paperclip",
            "bar-chart": "fa-bar-chart",
            "bars": "fa-bars",
            "book": "fa-book",
            "bookmark": "fa-bookmark",
            "bookmark-empty": "fa-bookmark-o",
            "briefcase": "fa-briefcase",
            "calendar": "fa-calendar",
            "caret-right": "fa-caret-right",
            "certificate": "fa-certificate",
            "check": "fa-check",
            "close": "fa-close",
            "cog": "fa-cog",
            "comment-alt": "fa-comment-o",
            "commit": "fa-check-square-o",
            "copy": "fa-copy",
            "delete": "fa-trash",
            "delivery": "fa-thumbs-up",
            "deploy": "fa-plus",
            "deployed": "fa-check",
            "done": "fa-check",
            "down": "fa-caret-down",
            "edit": "fa-edit",
            "entering": "fa-arrow-down",
            "eraser": "fa-eraser",
            "event": "fa-bolt",
            "exclamation": "fa-exclamation",
            "eye": "fa-eye",
            "facebook": "fa-facebook",
            "facility": "fa-home",
            "file": "fa-file",
            "file-alt": "fa-file-o",
            "file-pdf": "fa-file-pdf-o",
            "file-doc": "fa-file-word-o",
            "file-xls": "fa-file-excel-o",
            "file-text": "fa-file-text-o",
            "file-image": "fa-file-image-o",
            "file-generic": "fa-file-o",
            "flag": "fa-flag",
            "flag-alt": "fa-flag-o",
            "folder": "fa-folder",
            "folder-alt": "fa-folder-o",
            "folder-open-alt": "fa-folder-open-o",
            "fullscreen": "fa-fullscreen",
            "globe": "fa-globe",
            "goods": "fa-cubes",
            "group": "fa-group",
            "hand-grab": "fa-hand-grab-o",
            "hashtag": "fa-hashtag",
            "hint": "fa-hand-o-right",
            "home": "fa-home",
            "id-check": "fa-id-card-o",
            "inactive": "fa-check-empty",
            "incident": "fa-bolt",
            "info": "fa-info",
            "info-circle": "fa-info-circle",
            "leaving": "fa-arrow-up",
            "link": "fa-external-link",
            "list": "fa-list",
            "location": "fa-globe",
            "mail": "fa-envelope-o",
            "map-marker": "fa-map-marker",
            "minus": "fa-minus",
            "move": "fa-arrows",
            "news": "fa-info",
            "offer": "fa-truck",
            "organisation": "fa-institution",
            "org-network": "fa-umbrella",
            "other": "fa-circle",
            "paper-clip": "fa-paperclip",
            "pause": "fa-pause",
            "pencil": "fa-pencil",
            "phone": "fa-phone",
            "picture": "fa-picture-o",
            "plane": "fa-plane",
            "play": "fa-play",
            "plus": "fa-plus",
            "plus-sign": "fa-plus-sign",
            "print": "fa-print",
            "project": "fa-dashboard",
            "question-circle-o": "fa-question-circle-o",
            "radio": "fa-microphone",
            "remove": "fa-remove",
            "request": "fa-flag",
            "responsibility": "fa-briefcase",
            "return": "fa-arrow-left",
            "rss": "fa-rss",
            "search": "fa-search",
            "sent": "fa-check",
            "settings": "fa-wrench",
            "share": "fa-share-alt",
            "ship": "fa-ship",
            "shipment": "fa-truck",
            "site": "fa-home",
            "skype": "fa-skype",
            "staff": "fa-user",
            "star": "fa-star",
            "stop": "fa-stop",
            "table": "fa-table",
            "tag": "fa-tag",
            "tags": "fa-tags",
            "tasks": "fa-tasks",
            "th": "fa-th",
            "time": "fa-time",
            "truck": "fa-truck",
            "undo": "fa-undo",
            "unsent": "fa-times",
            "up": "fa-caret-up",
            "upload": "fa-upload",
            "user": "fa-user",
            "volunteer": "fa-hand-paper-o",
            "wrench": "fa-wrench",
            "zoomin": "fa-zoomin",
            "zoomout": "fa-zoomout",
        },
        # Foundation Icon Fonts 3
        # http://zurb.com/playground/foundation-icon-fonts-3
        "foundation": {
            "active": "fi-check",
            "activity": "fi-price-tag",
            "add": "fi-plus",
            "arrow-down": "fi-arrow-down",
            "attachment": "fi-paperclip",
            "bar-chart": "fi-graph-bar",
            "book": "fi-book",
            "bookmark": "fi-bookmark",
            "bookmark-empty": "fi-bookmark-empty",
            "calendar": "fi-calendar",
            "caret-right": "fi-play",
            "certificate": "fi-burst",
            "comment-alt": "fi-comment",
            "commit": "fi-check",
            "copy": "fi-page-copy",
            "delete": "fi-trash",
            "deploy": "fi-plus",
            "deployed": "fi-check",
            "edit": "fi-page-edit",
            "eraser": "fi-trash",
            "exclamation": "fi-alert",
            "eye": "fi-eye",
            "facebook": "fi-social-facebook",
            "facility": "fi-home",
            "file": "fi-page-filled",
            "file-alt": "fi-page",
            "file-text": "fi-page-filled",
            "file-text-alt": "fi-page",
            "flag": "fi-flag",
            "flag-alt": "fi-flag",
            "folder": "fi-folder",
            "folder-alt": "fi-folder",
            "folder-open-alt": "fi-folder",
            "fullscreen": "fi-arrows-out",
            "globe": "fi-map",
            "group": "fi-torsos-all",
            "home": "fi-home",
            "inactive": "fi-x",
            "info": "fi-info",
            "info-circle": "fi-info",
            "link": "fi-web",
            "list": "fi-list-thumbnails",
            "location": "fi-map",
            "mail": "fi-mail",
            "map-marker": "fi-marker",
            "minus": "fi-minus",
            "offer": "fi-burst",
            "organisation": "fi-torsos-all",
            "org-network": "fi-asterisk",
            "other": "fi-asterisk",
            "paper-clip": "fi-paperclip",
            "pause": "fi-pause",
            "pencil": "fi-pencil",
            "phone": "fi-telephone",
            "play": "fi-play",
            "plus": "fi-plus",
            "plus-sign": "fi-plus",
            "print": "fi-print",
            "radio": "fi-microphone",
            "remove": "fi-x",
            "request": "fi-flag",
            "responsibility": "fi-sheriff-badge",
            "return": "fi-arrow-left",
            "rss": "fi-rss",
            "search": "fi-magnifying-glass",
            "sent": "fi-check",
            "settings": "fi-wrench",
            "share": "fi-share",
            "site": "fi-home",
            "skype": "fi-social-skype",
            "star": "fi-star",
            "stop": "fi-stop",
            "table": "fi-list-thumbnails",
            "tag": "fi-price-tag",
            "tags": "fi-pricetag-multiple",
            "tasks": "fi-clipboard-notes",
            "time": "fi-clock",
            "undo": "fi-arrow-left",
            "unsent": "fi-x",
            "upload": "fi-upload",
            "user": "fi-torso",
            "zoomin": "fi-zoom-in",
            "zoomout": "fi-zoom-out",
        },
        # Font-Awesome 3
        # https://fontawesome.com/v3.2.1/icons/
        "font-awesome3": {
            "_base": "icon",
            "active": "icon-check",
            "activity": "icon-tag",
            "add": "icon-plus",
            "administration": "icon-cog",
            "arrow-down": "icon-arrow-down",
            "attachment": "icon-paper-clip",
            "bar-chart": "icon-bar-chart",
            "book": "icon-book",
            "bookmark": "icon-bookmark",
            "bookmark-empty": "icon-bookmark-empty",
            "briefcase": "icon-briefcase",
            "calendar": "icon-calendar",
            "caret-right": "icon-caret-right",
            "certificate": "icon-certificate",
            "comment-alt": "icon-comment-alt",
            "commit": "icon-truck",
            "copy": "icon-copy",
            "delete": "icon-trash",
            "deploy": "icon-plus",
            "deployed": "icon-ok",
            "down": "icon-caret-down",
            "edit": "icon-edit",
            "eraser": "icon-eraser",
            "exclamation": "icon-exclamation",
            "eye": "icon-eye-open",
            "facebook": "icon-facebook",
            "facility": "icon-home",
            "file": "icon-file",
            "file-alt": "icon-file-alt",
            "file-text": "icon-file-text",
            "file-text-alt": "icon-file-text-alt",
            "flag": "icon-flag",
            "flag-alt": "icon-flag-alt",
            "folder": "icon-folder-close",
            "folder-alt": "icon-folder-close-alt",
            "folder-open-alt": "icon-folder-open-alt",
            "fullscreen": "icon-fullscreen",
            "globe": "icon-globe",
            "group": "icon-group",
            "home": "icon-home",
            "inactive": "icon-check-empty",
            "info": "icon-info",
            "info-circle": "icon-info-sign",
            "link": "icon-external-link",
            "list": "icon-list",
            "location": "icon-globe",
            "mail": "icon-envelope-alt",
            "map-marker": "icon-map-marker",
            "minus": "icon-minus",
            "offer": "icon-truck",
            "organisation": "icon-sitemap",
            "org-network": "icon-umbrella",
            "other": "icon-circle",
            "paper-clip": "icon-paper-clip",
            "pause": "icon-pause",
            "pencil": "icon-pencil",
            "phone": "icon-phone",
            "picture": "icon-picture",
            "play": "icon-play",
            "plus": "icon-plus",
            "plus-sign": "icon-plus-sign",
            "print": "icon-print",
            "radio": "icon-microphone",
            "remove": "icon-remove",
            "request": "icon-flag",
            "responsibility": "icon-briefcase",
            "return": "icon-arrow-left",
            "rss": "icon-rss",
            "search": "icon-search",
            "sent": "icon-ok",
            "settings": "icon-wrench",
            "share": "icon-share",
            "site": "icon-home",
            "skype": "icon-skype",
            "star": "icon-star",
            "stop": "icon-stop",
            "table": "icon-table",
            "tag": "icon-tag",
            "tags": "icon-tags",
            "tasks": "icon-tasks",
            "time": "icon-time",
            "truck": "icon-truck",
            "undo": "icon-undo",
            "unsent": "icon-remove",
            "up": "icon-caret-up",
            "upload": "icon-upload-alt",
            "user": "icon-user",
            "wrench": "icon-wrench",
            "zoomin": "icon-zoomin",
            "zoomout": "icon-zoomout",
        },
    }

    # -------------------------------------------------------------------------
    def __init__(self, name, **attr):
        """
            Args:
                name: the abstract icon name
                attr: additional HTML attributes (optional)
        """

        self.name = name
        super().__init__(" ", **attr)

    # -------------------------------------------------------------------------
    def xml(self):
        """
            Render this instance as XML
        """

        # Custom layout?
        layout = current.deployment_settings.get_ui_icon_layout()
        if layout:
            return layout(self)

        css_class = self.css_class(self.name)

        if css_class:
            self.add_class(css_class)

        return super().xml()

    # -------------------------------------------------------------------------
    @classmethod
    def css_class(cls, name):

        settings = current.deployment_settings
        fallback = "font-awesome"

        # Lookup the default set
        icons = cls.icons
        default_set = settings.get_ui_icons()
        default = icons[fallback]
        if default_set != fallback:
            default.pop("_base", None)
            default.update(icons.get(default_set, {}))

        # Custom set?
        custom = settings.get_ui_custom_icons()

        if custom and name in custom:
            css = custom[name]
            base = custom.get("_base")
        elif name in default:
            css = default[name]
            base = default.get("_base")
        else:
            css = name
            base = None

        return " ".join([c for c in (css, base) if c])


# END =========================================================================
