#!/usr/bin/env python
# -*- coding: utf-8 -*-

# MIT License
#
# Copyright (c) 2021 TROUVERIE Joachim <jtrouverie@joakode.fr>
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

"""
flask_inertia.inertia
---------------------

Create a Sanic extension to bind Flask and InertiaJS.
"""

import os
from typing import Any, Optional

# from flask import Flask, Markup, Response, current_app, request
from sanic import Sanic
from sanic.request import Request
from sanic.response import HTTPResponse, html, text
from jinja2 import Template
from jinja2.utils import pass_context
from jsmin import jsmin
from werkzeug.exceptions import BadRequest

from sanic_inertia.version import get_asset_version


class Inertia:
    """Inertia Plugin for Sanic."""

    def __init__(self, app: Optional[Sanic] = None):
        if app is not None:
            self.app = app
            self.init_app(app)

    def init_app(self, app: Sanic):
        """Init as an app extension

        * Register before_request hook
        * Register after_request hook
        * Set context processor to have an `inertia` value in templates
        """
        self.app = app
        self._shared_data = {}
        if not hasattr(app.ctx, "extensions"):
           self. app.ctx.extensions = {}
        self.app.ctx.extensions["inertia"] = self
        # self.app.context_processor(self.context_processor)
        self.app.ext.templating.environment.globals.update({"inertia": self})
        self.app.register_middleware(self.process_incoming_inertia_requests, "request")
        self.app.register_middleware(self.update_redirect, "response")

    def process_incoming_inertia_requests(self, request) -> Optional[HTTPResponse]:
        """Process incoming Inertia requests.

        AJAX requests must be forged by Inertia.

        Whenever an Inertia request is made, Inertia will include the current asset
        version in the X-Inertia-Version header. If the asset versions are the same,
        the request simply continues as expected. However, if they are different,
        the server immediately returns a 409 Conflict response (only for GET request),
        and includes the URL in a X-Inertia-Location header.
        """
        # request is ajax
        if request.headers.get("X-Requested-With") != "XMLHttpRequest":
            return None

        # check if send with Inertia
        if not request.headers.get("X-Inertia"):
            raise BadRequest("Inertia headers not found")

        # check inertia version
        server_version = get_asset_version(request.app)
        inertia_version = request.headers.get("X-Inertia-Version")
        if (
            request.method == "GET"
            and inertia_version
            and inertia_version != server_version
        ):
            response = text("Inertia versions does not match", status=409)
            response.headers["X-Inertia-Location"] = request.full_path
            return response

        return None

    def update_redirect(self, request: Request, response: HTTPResponse) -> HTTPResponse:
        """Update redirect to set 303 status code.

        409 conflict responses are only sent for GET requests, and not for
        POST/PUT/PATCH/DELETE requests. That said, they will be sent in the
        event that a GET redirect occurs after one of these requests. To force
        Inertia to use a GET request after a redirect, the 303 HTTP status is used

        :param response: The generated response to update
        """
        if (
            request.method in ["PUT", "PATCH", "DELETE"]
            and response.status_code == 302
        ):
            response.status_code = 303

        return response

    def share(self, key: str, value: Any):
        """Preassign shared data for each request.

        Sometimes you need to access certain data on numerous pages within your
        application. For example, a common use-case for this is showing the
        current user in the site header. Passing this data manually in each
        response isn't practical. In these situations shared data can be useful.

        :param key: Data key to share between requests
        :param value: Data value or Function returning the data value
        """
        self._shared_data[key] = value

    # @staticmethod
    @pass_context
    def context_processor(self, context):
        """Add an `inertia` directive to Jinja2 template to allow router inclusion

        .. code-block:: html

           <head>
             <script lang="javascript">
               {{ inertia.include_router() }}
             </script>
           </head>
        """
        context["inertia"] = self.app.ctx.extensions["inertia"]

    def include_router(self) -> HTTPResponse:
        """Include JS router in Templates."""
        router_file = os.path.join(
            os.path.abspath(os.path.dirname(__file__)), "router.js"
        )
        # print( self.app.router.routes)
        routes = {
            name: route.path for name, route in self.app.router.name_index.items()
        }
        print(routes)
        with open(router_file, "r") as jsfile:
            template = Template(jsfile.read())
            # Jinja2 template automatically gets rid of ['<'|'>'|'''] chars
            content = (
                template.render(routes=routes)
                .replace("\\u003c", "<")
                .replace("\\u003e", ">")
                .replace("\\u0022", '"')
                .replace("\\u0027", '"')
            )
            # print(content)
            content_minified = jsmin(content)

            return content
