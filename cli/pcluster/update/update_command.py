# Copyright 2018 Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"). You may not use this file except in compliance
# with the License. A copy of the License is located at
#
# http://aws.amazon.com/apache2.0/
#
# or in the "LICENSE.txt" file accompanying this file. This file is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES
# OR CONDITIONS OF ANY KIND, express or implied. See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import print_function

import logging
import sys
import time

import boto3
from botocore.exceptions import ClientError
from tabulate import tabulate

import pcluster.utils as utils
from pcluster.config.config_patch import ConfigPatch
from pcluster.config.pcluster_config import PclusterConfig

LOGGER = logging.getLogger(__name__)


def execute(args):
    LOGGER.info("Validating configuration file {0}...".format(args.config_file))
    stack_name = utils.get_stack_name(args.cluster_name)
    target_config = PclusterConfig(
        config_file=args.config_file, cluster_label=args.cluster_template, fail_on_file_absence=True
    )
    target_config.validate()
    cfn_params = target_config.to_cfn()
    cfn = boto3.client("cloudformation")
    _autofill_cfn_params(cfn, args, cfn_params, stack_name, target_config)

    if _check_updatability(args, target_config, stack_name):
        _update_cluster(args, cfn, cfn_params, stack_name)
    else:
        LOGGER.info("Update aborted.")
        sys.exit(1)


def _update_cluster(args, cfn, cfn_params, stack_name):
    LOGGER.info("Updating: %s", args.cluster_name)
    LOGGER.debug("Updating based on args %s", str(args))
    try:
        LOGGER.debug(cfn_params)
        if args.extra_parameters:
            LOGGER.debug("Adding extra parameters to the CFN parameters")
            cfn_params.update(dict(args.extra_parameters))

        cfn_params = [{"ParameterKey": key, "ParameterValue": value} for key, value in cfn_params.items()]
        LOGGER.info("Calling update_stack")
        cfn.update_stack(
            StackName=stack_name, UsePreviousTemplate=True, Parameters=cfn_params, Capabilities=["CAPABILITY_IAM"]
        )
        stack_status = utils.get_stack(stack_name, cfn).get("StackStatus")
        if not args.nowait:
            while stack_status == "UPDATE_IN_PROGRESS":
                stack_status = utils.get_stack(stack_name, cfn).get("StackStatus")
                events = cfn.describe_stack_events(StackName=stack_name).get("StackEvents")[0]
                resource_status = (
                    "Status: %s - %s" % (events.get("LogicalResourceId"), events.get("ResourceStatus"))
                ).ljust(80)
                sys.stdout.write("\r%s" % resource_status)
                sys.stdout.flush()
                time.sleep(5)
        else:
            stack_status = utils.get_stack(stack_name, cfn).get("StackStatus")
            LOGGER.info("Status: %s", stack_status)
    except ClientError as e:
        LOGGER.critical(e.response.get("Error").get("Message"))
        sys.exit(1)
    except KeyboardInterrupt:
        LOGGER.info("\nExiting...")
        sys.exit(0)


def _check_updatability(args, target_config, stack_name):
    can_proceed = True
    if args.force:
        LOGGER.warning("Forced update. All security checks are being skipped.")
    else:
        LOGGER.info("Retrieving configuration from CloudFormation for cluster {0}...".format(args.cluster_name))
        base_config = PclusterConfig(config_file=args.config_file, cluster_name=args.cluster_name)
        try:
            patch = ConfigPatch(base_config, target_config)
            LOGGER.info("Found Changes:")
            if len(patch.changes):
                allowed, rows, actions_needed = patch.check(stack_name)
                print(tabulate(rows, headers="firstrow"))
                print()

                if allowed:
                    LOGGER.info("Congratulations! The new configuration can be safely applied to your cluster.")
                else:
                    LOGGER.error("The new configuration cannot be safely applied to your cluster.")
                    print("Please try the following actions:")
                    for a in actions_needed:
                        print("- {0}".format(a.replace("\n", "\n  ")))
                    print("Then, retry the update.")
                    can_proceed = False
            else:
                LOGGER.info("No changes found in your cluster configuration.")
        except Exception as e:
            LOGGER.error(e)
            can_proceed = False

    # Final consent from user
    if can_proceed:
        can_proceed = input("Do you want to proceed with the update? - Y/N: ").strip().lower() == "y"
    return can_proceed


def _autofill_cfn_params(cfn_boto3_client, args, cfn_params, stack_name, target_config):
    cluster_section = target_config.get_section("cluster")

    if cluster_section.get_param_value("scheduler") != "awsbatch":
        if not args.reset_desired:
            asg_name = utils.get_asg_name(stack_name)
            desired_capacity = (
                boto3.client("autoscaling")
                .describe_auto_scaling_groups(AutoScalingGroupNames=[asg_name])
                .get("AutoScalingGroups")[0]
                .get("DesiredCapacity")
            )
            cfn_params["DesiredSize"] = str(desired_capacity)
    else:
        if args.reset_desired:
            LOGGER.info("reset_desired flag does not work with awsbatch scheduler")
        params = utils.get_stack(stack_name, cfn_boto3_client).get("Parameters")

        for parameter in params:
            if parameter.get("ParameterKey") == "ResourcesS3Bucket":
                cfn_params["ResourcesS3Bucket"] = parameter.get("ParameterValue")
