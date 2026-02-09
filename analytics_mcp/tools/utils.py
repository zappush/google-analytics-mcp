# Copyright 2025 Google LLC All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Common utilities used by the MCP server.

Modified to support per-request OAuth tokens for multi-user deployments.
"""

from contextvars import ContextVar
from typing import Any, Dict, Optional

from google.analytics import admin_v1beta, data_v1beta, admin_v1alpha
from google.api_core.gapic_v1.client_info import ClientInfo
from google.oauth2.credentials import Credentials
from importlib import metadata
import google.auth
import proto


def _get_package_version_with_fallback():
    """Returns the version of the package.

    Falls back to 'unknown' if the version can't be resolved.
    """
    try:
        return metadata.version("analytics-mcp")
    except:
        return "unknown"


# Client information that adds a custom user agent to all API requests.
_CLIENT_INFO = ClientInfo(
    user_agent=f"analytics-mcp/{_get_package_version_with_fallback()}"
)

# Read-only scope for Analytics Admin API and Analytics Data API.
_READ_ONLY_ANALYTICS_SCOPE = (
    "https://www.googleapis.com/auth/analytics.readonly"
)

# Context variable to hold the current request's access token
# This allows per-request credentials in a multi-user environment
_current_access_token: ContextVar[Optional[str]] = ContextVar(
    "current_access_token", default=None
)


def set_access_token(token: str) -> None:
    """Sets the access token for the current request context.

    Call this at the start of each request to set the user's OAuth token.
    """
    _current_access_token.set(token)


def get_access_token() -> Optional[str]:
    """Gets the access token for the current request context."""
    return _current_access_token.get()


def clear_access_token() -> None:
    """Clears the access token for the current request context."""
    _current_access_token.set(None)


def _create_credentials() -> google.auth.credentials.Credentials:
    """Returns credentials for API calls.

    If an access token is set in the current context (via set_access_token),
    uses OAuth2 credentials with that token. Otherwise, falls back to
    Application Default Credentials.

    This allows the server to work in both:
    - Multi-user mode: Each request provides its own OAuth token
    - Single-user mode: Uses ADC (original behavior)
    """
    token = get_access_token()

    if token:
        # Use the provided OAuth token
        return Credentials(
            token=token,
            scopes=[_READ_ONLY_ANALYTICS_SCOPE]
        )

    # Fall back to Application Default Credentials
    credentials, _ = google.auth.default(scopes=[_READ_ONLY_ANALYTICS_SCOPE])
    return credentials


def create_admin_api_client() -> admin_v1beta.AnalyticsAdminServiceAsyncClient:
    """Returns a properly configured Google Analytics Admin API async client.

    Uses OAuth token from context if available, otherwise ADC.
    """
    return admin_v1beta.AnalyticsAdminServiceAsyncClient(
        client_info=_CLIENT_INFO, credentials=_create_credentials()
    )


def create_data_api_client() -> data_v1beta.BetaAnalyticsDataAsyncClient:
    """Returns a properly configured Google Analytics Data API async client.

    Uses OAuth token from context if available, otherwise ADC.
    """
    return data_v1beta.BetaAnalyticsDataAsyncClient(
        client_info=_CLIENT_INFO, credentials=_create_credentials()
    )


def create_admin_alpha_api_client() -> (
    admin_v1alpha.AnalyticsAdminServiceAsyncClient
):
    """Returns a properly configured Google Analytics Admin API (alpha) async client.

    Uses OAuth token from context if available, otherwise ADC.
    """
    return admin_v1alpha.AnalyticsAdminServiceAsyncClient(
        client_info=_CLIENT_INFO, credentials=_create_credentials()
    )


def construct_property_rn(property_value: int | str) -> str:
    """Returns a property resource name in the format required by APIs."""
    property_num = None
    if isinstance(property_value, int):
        property_num = property_value
    elif isinstance(property_value, str):
        property_value = property_value.strip()
        if property_value.isdigit():
            property_num = int(property_value)
        elif property_value.startswith("properties/"):
            numeric_part = property_value.split("/")[-1]
            if numeric_part.isdigit():
                property_num = int(numeric_part)
    if property_num is None:
        raise ValueError(
            (
                f"Invalid property ID: {property_value}. "
                "A valid property value is either a number or a string starting "
                "with 'properties/' and followed by a number."
            )
        )

    return f"properties/{property_num}"


def proto_to_dict(obj: proto.Message) -> Dict[str, Any]:
    """Converts a proto message to a dictionary."""
    return type(obj).to_dict(
        obj, use_integers_for_enums=False, preserving_proto_field_name=True
    )


def proto_to_json(obj: proto.Message) -> str:
    """Converts a proto message to a JSON string."""
    return type(obj).to_json(obj, indent=None, preserving_proto_field_name=True)
