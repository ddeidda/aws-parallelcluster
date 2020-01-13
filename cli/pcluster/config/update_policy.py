# Copyright 2019 Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"). You may not use this file except in compliance
# with the License. A copy of the License is located at
#
# http://aws.amazon.com/apache2.0/
#
# or in the "LICENSE.txt" file accompanying this file. This file is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES
# OR CONDITIONS OF ANY KIND, express or implied. See the License for the specific language governing permissions and
# limitations under the License.
from enum import Enum

from pcluster import utils


class UpdatePolicy(object):
    """Describes the policy that rules the update of a configuration parameter."""

    class CheckResult(Enum):
        """Valid results for change checks."""

        SUCCEEDED = "SUCCEEDED"
        ACTION_NEEDED = "ACTION NEEDED"
        FAILED = "FAILED"

    def __init__(self, base_policy=None, level=None, fail_reason=None, action_needed=None, condition_checker=None):
        self.fail_reason = None
        self.action_needed = None
        self.condition_checker = None
        self.level = 0

        if base_policy:
            self.fail_reason = base_policy.fail_reason
            self.action_needed = base_policy.action_needed
            self.condition_checker = base_policy.condition_checker
            self.level = base_policy.level

        if level:
            self.level = level
        if fail_reason:
            self.fail_reason = fail_reason
        if action_needed:
            self.action_needed = action_needed
        if condition_checker:
            self.condition_checker = condition_checker

    def check(self, stack_name):
        """
        Check if the update can be safely performed.

        Based on the policy condition checker, the result can be FAILED, SUCCEEDED or ACTION_NEEDED.
        :param stack_name: The Cfn Stack to which check policy condition against
        :return: FAILED, SUCCEEDED or ACTION_NEEDED
        """
        result = UpdatePolicy.CheckResult.FAILED
        if self.condition_checker:
            result = (
                UpdatePolicy.CheckResult.SUCCEEDED
                if self.condition_checker(stack_name)
                else UpdatePolicy.CheckResult.ACTION_NEEDED
            )
        return result

    def __eq__(self, other):
        if not isinstance(other, UpdatePolicy):
            # don't attempt to compare against unrelated types
            return NotImplemented

        return self.fail_reason == other.fail_reason and self.level == other.level


# Base policies
UpdatePolicy.IGNORED = UpdatePolicy(level=-10, condition_checker=(lambda stack_name: True))
UpdatePolicy.ALLOWED = UpdatePolicy(level=0, condition_checker=(lambda stack_name: True))  # Can be safely updated
UpdatePolicy.COMPUTE_FLEET_RESTART = UpdatePolicy(
    level=10,
    fail_reason="Compute fleet must be empty",
    action_needed="Stop the cluster with the following command: \n" "pcluster stop -c $CONFIG_FILE $CLUSTER_NAME",
    condition_checker=lambda stack_name: len(utils.get_asg_instances(stack_name)) == 0,
)  # Can be updated but compute fleet must be restarted
UpdatePolicy.MASTER_RESTART = UpdatePolicy(
    level=20,
    fail_reason="Master node must be down",
    action_needed="Stop the cluster with the following command: \n" "pcluster stop -c $CONFIG_FILE $CLUSTER_NAME",
    condition_checker=lambda stack_name: utils.get_master_server_state(stack_name) == "stopped",
)  # Can be updated but master node must be restarted
UpdatePolicy.UNKNOWN = UpdatePolicy(
    level=100,
    fail_reason="Update currently not supported",
    action_needed="Restore the previous parameter value for the unsupported changes.",
)  # Can be updated but we don't know the effects
UpdatePolicy.DENIED = UpdatePolicy(
    level=1000,
    fail_reason="Update currently unsupported",
    action_needed="Restore the previous parameter value for the unsupported changes.",
)  # Cannot be updated
