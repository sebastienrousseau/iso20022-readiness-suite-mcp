#!/usr/bin/env python3
# Copyright (C) 2023-2026 Sebastien Rousseau.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Example: ``list_profiles``.

Lists every clearing profile (CBPR+, FedNow, SEPA_Instant, Generic) the
server lints against. Call this first to discover the ``target_profile``
values the other tools accept. No sub-server is needed.

Usage::

    python examples/01_list_profiles.py
"""

from iso20022_readiness_suite_mcp.server import list_profiles


def main() -> None:
    """Print every available clearing profile with its rule count."""
    profiles = list_profiles()
    print(f"Available clearing profiles ({len(profiles)}):")
    for profile in profiles:
        rules = len(profile["custom_rules"])
        print(
            f"  {profile['profile_id']:<14}  {rules} rule(s)  "
            f"{profile['market_practice']}"
        )


if __name__ == "__main__":
    main()
