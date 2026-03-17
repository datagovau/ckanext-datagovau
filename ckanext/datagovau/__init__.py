from __future__ import annotations

import inspect
import os
from typing import Any, Optional

import dominate.tags as tags
from markupsafe import Markup

import ckan.lib.mailer as mailer
import ckan.plugins.toolkit as tk
from ckan import authz
from ckan.lib.helpers import Page

from ckanext.toolbelt.magic import (  # type: ignore
    conjure_fast_group_activities,
    reveal_readonly_scheming_fields,  # type: ignore
)
from ckanext.xloader.plugin import xloaderPlugin

__version__ = "3.0.0"

###############################################################################
#      Faster computation of new activities for dashboard icon in header      #
###############################################################################
conjure_fast_group_activities()
###############################################################################
#                                     End                                     #
###############################################################################

###############################################################################
#           Add readonly fields to dataset: slow index but fast read          #
###############################################################################
reveal_readonly_scheming_fields(
    {
        ("duplicate_score",): "",
        ("original_harvest_source",): {},
    }
)
###############################################################################
#                                     End                                     #
###############################################################################


###############################################################################
#                 Catch XLoader error when resource is deleted                #
###############################################################################
def _dga_xnotify(self: xloaderPlugin, entity: Any, operation: str):
    try:
        return _original_xnotify(self, entity, operation)
    except tk.ObjectNotFound:
        # resource has `deleted` state
        pass


_original_xnotify: Any = xloaderPlugin.notify
xloaderPlugin.notify = _dga_xnotify
###############################################################################
#                                     End                                     #
###############################################################################


###############################################################################
#                       Anyone can add datasets to group                      #
###############################################################################
_original_permission_check = authz.has_user_permission_for_group_or_org


def _dga_permission_check(
    group_id: str | None,
    user_name: str | None,
    permission: str,
) -> bool:
    stack = inspect.stack()
    # Bypass authorization to enable datasets to be removed from/added to AGIFT
    # classification
    if stack[1].function == "package_membership_list_save":
        return True
    return _original_permission_check(group_id, user_name, permission)


authz.has_user_permission_for_group_or_org = _dga_permission_check
###############################################################################
#                                     End                                     #
###############################################################################


###############################################################################
#                    Customize markup of pagination widget                    #
###############################################################################
def dga_update_pager(self: Page, *args: Any, **kwargs: Any) -> Markup:
    """Override CKAN default pagination method with custom implementation.

    Returns:
        Customized pagination Markup
    """
    # Create the wrapper div
    div: Any = tags.div(cls="pagination-wrapper")
    with div as wrapper:
        tags.ul(
            "$link_previous ~3~ $link_next", cls="pagination justify-content-center"
        )

    def _arrow_link(
        page_attr: str, active_svg: str, disabled_svg: str, label: str
    ) -> str:
        """Create accessible previous and next links."""
        page_num = getattr(self, page_attr)
        page_param = kwargs.get("page_param", "page")

        if page_num:
            link_params = {}
            link_params.update(self.kwargs)
            link_params.update(kwargs)
            link_params[page_param] = page_num

            if self._url_generator is not None:
                url_generator = self._url_generator
            else:
                from ckan.lib.helpers import pager_url as url_generator
            url = url_generator(**link_params)

            a_tag = tags.a(
                _render_svg(active_svg),
                href=url,
                **{"class": "page-link", "aria-label": label},
            )
            return str(tags.li(a_tag, cls="page-item"))

        # Disabled: use alternate SVG and disable interaction
        a_tag = tags.a(
            _render_svg(disabled_svg),
            href="#",
            **{"class": "page-link", "aria-hidden": "true", "tabindex": "-1"},
        )
        return str(tags.li(a_tag, cls="page-item disabled"))

    link_previous = _arrow_link(
        "previous_page",
        "arrow-left.svg",
        "arrow-left-grey.svg",
        "Previous page",
    )
    link_next = _arrow_link(
        "next_page",
        "arrow-right.svg",
        "arrow-right-grey.svg",
        "Next page",
    )

    custom_params: dict[str, Any] = {
        "format": str(wrapper)
        .replace("$link_previous", link_previous)
        .replace("$link_next", link_next),
        "curpage_attr": {"class": "page-item active"},
        "link_attr": {"class": "page-link"},
    }
    custom_params.update(kwargs)

    return super(Page, self).pager(*args, **custom_params)


def _render_svg(file_name: str) -> Markup:
    """Reads and returns the contents of an SVG file from the public/images directory.

    :return: The SVG file content as a Markup string
    or an empty string if file not found.
    """
    static_path = os.path.join(os.path.dirname(__file__), "public", "images", file_name)
    try:
        with open(static_path, encoding="utf-8") as svg_file:
            return Markup(svg_file.read())
    except FileNotFoundError:
        # Return an empty Markup string to avoid serialization errors
        return Markup("")


# Monkey patch the Page class to use our custom pager method
Page.pager = dga_update_pager
###############################################################################
#                                     End                                     #
###############################################################################

###############################################################################
#    Fix for AWS SMTP authentication. will be included into v2.10.5/2.11.0    #
###############################################################################
def _mail_recipient(
        recipient_name: str, recipient_email: str, sender_name: str,
        sender_url: str, subject: Any, body: Any,
        body_html: Optional[Any] = None,
        headers: Optional[dict[str, Any]] = None,
        attachments: Optional[mailer.Iterable[mailer.Attachment]] = None) -> None:

    if not headers:
        headers = {}

    if not attachments:
        attachments = []

    mail_from = mailer.config.get('smtp.mail_from')

    reply_to = mailer.config.get('smtp.reply_to')

    msg = mailer.EmailMessage()

    msg.set_content(body, cte='base64')

    if body_html:
        msg.add_alternative(body_html, subtype='html', cte='base64')

    for k, v in headers.items():
        if k in msg.keys():
            msg.replace_header(k, v)
        else:
            msg.add_header(k, v)
    msg['Subject'] = subject
    msg['From'] = mailer.utils.formataddr((sender_name, mail_from))
    msg['To'] = mailer.utils.formataddr((recipient_name, recipient_email))
    msg['Date'] = mailer.utils.formatdate(mailer.time())
    if not mailer.config.get('ckan.hide_version'):
        msg['X-Mailer'] = "CKAN %s" % mailer.ckan.__version__
    # Check if extension is setting reply-to via headers or use config option
    if reply_to and reply_to != '' and not msg['Reply-to']:
        msg['Reply-to'] = reply_to

    for attachment in attachments:
        if len(attachment) == 3:
            name, _file, media_type = attachment
        else:
            name, _file = attachment
            media_type = None

        if not media_type:
            media_type, _encoding = mailer.mimetypes.guess_type(name)
        if media_type:
            main_type, sub_type = media_type.split('/')
        else:
            main_type = sub_type = None

        msg.add_attachment(
            _file.read(), filename=name, maintype=main_type, subtype=sub_type)

    # Send the email using Python's smtplib.
    smtp_server: str = mailer.config.get('smtp.server')
    smtp_starttls = mailer.config.get('smtp.starttls')
    smtp_user = mailer.config.get('smtp.user')
    smtp_password = mailer.config.get('smtp.password')

    try:
        parts = smtp_server.rsplit(":", 1)
        host = parts[0]
        port = int(parts[1]) if len(parts) == 2 else 0

        smtp_connection = mailer.smtplib.SMTP(host, port)
    except (mailer.socket.error, mailer.smtplib.SMTPConnectError) as e:
        mailer.log.exception(e)
        raise mailer.MailerException('SMTP server could not be connected to: "%s" %s'
                              % (smtp_server, e))

    try:
        # Identify ourselves and prompt the server for supported features.
        smtp_connection.ehlo()

        # If 'smtp.starttls' is on in CKAN config, try to put the SMTP
        # connection into TLS mode.
        if smtp_starttls:
            if smtp_connection.has_extn('STARTTLS'):
                smtp_connection.starttls()
                # Re-identify ourselves over TLS connection.
                smtp_connection.ehlo()
            else:
                raise mailer.MailerException("SMTP server does not support STARTTLS")

        # If 'smtp.user' is in CKAN config, try to login to SMTP server.
        if smtp_user:
            assert smtp_password, ("If smtp.user is configured then "
                                   "smtp.password must be configured as well.")
            smtp_connection.login(smtp_user, smtp_password)

        smtp_connection.sendmail(mail_from, [recipient_email], msg.as_string())
        mailer.log.info("Sent email to {0}".format(recipient_email))

    except mailer.smtplib.SMTPException as e:
        msg = '%r' % e
        mailer.log.exception(msg)
        raise mailer.MailerException(msg)
    finally:
        smtp_connection.quit()

mailer._mail_recipient = _mail_recipient
###############################################################################
#                                     End                                     #
###############################################################################
