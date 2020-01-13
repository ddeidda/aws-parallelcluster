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
import copy
import re
from collections import namedtuple

# Represents a single parameter change in a ConfigPatch instance
from pcluster.config.update_policy import UpdatePolicy

Change = namedtuple("Change", ["section_key", "section_label", "param_key", "old_value", "new_value", "update_policy"])


# Patch deepcopy for compiled regex to prevent "TypeError: cannot deepcopy this pattern object" error in Pyhton < 3.7
copy._deepcopy_dispatch[type(re.compile(""))] = lambda r, _: r


class ConfigPatch(object):
    """
    Represents the Diff Patch between two PclusterConfig instances.

    To be successfully created, it is mandatory that the base PclusterConfig instance can be "adapted" to the target
    one, which means that all its sections can be matched to the base PClusterConfig instance's sections.
    """

    IGNORED_SECTIONS = ["global", "aliases"]  # Sections ignored for patch creation

    def __init__(self, base_config, target_config):
        """
        Create a ConfigPatch.

        Tries creating a ConfigPatch instance to describe the changes needed to update a pre-existing base_config
        to the new settings contained in target_config.
        :param base_config: The base configuration, f.i. as reconstructed from CloudFormation
        :param target_config: The target configuration, f.i. as loaded from configuration file
        """
        # Cached condition results
        self.condition_results = {}

        self.base_config = copy.deepcopy(base_config)
        self.target_config = copy.deepcopy(target_config)
        self.changes = []
        self._adapt()
        self._compare()

    def _adapt(self):
        """
        Adapt the base config to the target one.

        The adaptation process involves restoring sections labels in the base config to make them match the ones in the
        target config, plus adding missing sections into one or the other configuration to make comparison possible.
        At the end of this process, both configurations will have the same number of sections, as well as the same
        section labels.
        """
        # Remove ignored sections
        self._remove_ignored_sections(self.base_config)
        self._remove_ignored_sections(self.target_config)

        # Automatically rename base sections to prevent false matches
        self._rename_base_sections()

        # Match base sections and create missing sections in target config
        for section_key in self.base_config.get_section_keys():
            for _, base_section in self.base_config.get_sections(section_key).items():
                target_section = self._get_target_section(base_section)
                # Base config's sections are re-labelled by target's sections names
                base_section.label = target_section.label

        # Create missing sections in base config
        for section_key in self.target_config.get_section_keys():
            for _, target_section in self.target_config.get_sections(section_key).items():
                base_section = self._get_base_section(target_section)

    def _compare(self):
        """
        Compare the target config to the source one.

        All sections in both configurations are compared one by one. This is made possible by the adaptation phase.
        The last compared section is "cluster". This is compared only after the mock sections created during the
        adaptation phase are removed, in order to make differences in settings parameters (like ebs_settings) appear
        correctly.
        """
        # First, compare all sections except "cluster".
        for section_key in self.target_config.get_section_keys():
            if section_key != "cluster":
                for _, target_section in self.target_config.get_sections(section_key).items():
                    base_section = self.base_config.get_section(target_section.key, target_section.label)
                    self._compare_section(base_section, target_section)

        # Then, remove all mock sections. Settings_parameters will be refresh after this.
        self._remove_mock_sections(self.base_config)
        self._remove_mock_sections(self.target_config)

        # Finally, compare cluster sections.
        self._compare_section(
            self.base_config.get_section("cluster"), self.target_config.get_section("cluster"),
        )

    def _compare_section(self, base_section, target_section):
        for _, param in target_section.params.items():
            base_value = base_section.get_param(param.key).value if base_section else None
            target_value = param.value

            if base_value != target_value:
                self.changes.append(
                    Change(
                        target_section.key,
                        target_section.label,
                        param.key,
                        base_value,
                        param.value,
                        param.get_update_policy(),
                    )
                )

    def _restore_settings_params(self, config):
        cluster_section = config.get_section("cluster")
        for _, param in cluster_section.params.items():
            if param.key.endswith("_settings"):
                self._restore_settings_param(config, param)

    def _restore_settings_param(self, config, settings_param):
        sections_labels_list = []
        sections = config.get_sections(settings_param.referred_section_key).items()

        for _, section in sections:
            if not hasattr(section, "mock"):
                sections_labels_list.append(section.label)
        settings_param.value = ",".join(sorted(sections_labels_list))

    def _remove_ignored_sections(self, config):
        for section_key in ConfigPatch.IGNORED_SECTIONS:
            config.remove_section(section_key)

    def _remove_mock_sections(self, config):
        for section_key in config.get_section_keys():
            for _, section in sorted(config.get_sections(section_key).items()):
                if hasattr(section, "mock"):
                    config.remove_section(section.key, section.label)

    def _rename_base_sections(self):
        """
        Rename sections in base config.

        Make all sections labels in base config different from labels in target config, so that after adaptation we can
        check that all sections have been correctly matched by just comparing their labels.
        """
        for section_key in self.base_config.get_section_keys():
            new_lbl = u"_{0}{1}"
            i = 0
            for _, base_section in sorted(self.base_config.get_sections(section_key).items()):
                base_section.label = new_lbl.format(section_key, i if i > 0 else "")
                i += 1

    @property
    def update_policy_level(self):
        """Get the max update policy level of the ConfigPatch."""
        return (
            max(change.update_policy.level for change in self.changes)
            if len(self.changes)
            else UpdatePolicy.ALLOWED.level
        )

    def _create_default_section(self, config, section):
        """Create a default section of same type of the provided section in the provided config to allow comparison."""
        section_definition = section.definition
        section_type = section_definition.get("type")
        mock_section = section_type(
            section_definition=section_definition, pcluster_config=self.target_config, section_label=section.label
        )
        # Sections with key param (like EBS) are marked as mock to be ignored from related settings params
        if section.key_param:
            mock_section.mock = True
        config.add_section(mock_section)
        return mock_section

    def _get_target_section_by_param(self, section_key, param_key, param_value):
        section = None
        sections = self.target_config.get_sections(section_key)
        for _, s in sections.items():
            param = s.get_param(param_key)
            if param and param.value == param_value:
                section = s
                break
        return section

    def _get_target_section(self, base_section):
        section = None
        key_param = base_section.key_param
        if key_param:
            # EBS sections are looked by shared dir
            key_param_value = base_section.get_param_value(key_param)
            section = self._get_target_section_by_param(base_section.key, key_param, key_param_value)
        else:
            # All other sections are matched only if exactly one is found
            sections = self.target_config.get_sections(base_section.key)
            if len(sections) == 1:
                section = next(iter(sections.values()))

        # If section is not present in target config we build a default section to allow comparison
        if not section:
            section = self._create_default_section(self.target_config, base_section)

        return section

    def _get_base_section(self, target_section):
        base_section = self.base_config.get_section(target_section.key, target_section.label)

        # If section is not present in base config we build a default section to allow comparison
        if not base_section:
            base_section = self._create_default_section(self.base_config, target_section)
        return base_section

    def check(self, stack_name):
        """
        Check the patch against the provided stack.

        Tells if the patch can be applied to the provided stack and returns a detailed report.
        :param stack_name The stack name
        :return The patch applicability and the report rows
        """
        rows = [["section", "parameter", "old value", "new value", "check", "reason"]]
        actions_needed = set()

        patch_allowed = True

        for change in self.changes:
            if change.update_policy != UpdatePolicy.IGNORED:
                section = ("{0}{1}{2}").format(
                    change.section_key,
                    " " if change.section_label else "",
                    change.section_label if change.section_label else "",
                )

                check_result = change.update_policy.check(stack_name)
                reason = "-"

                if check_result != UpdatePolicy.CheckResult.SUCCEEDED:
                    reason = change.update_policy.fail_reason
                    patch_allowed = False
                    action_needed = change.update_policy.action_needed
                    if action_needed:
                        action_needed = action_needed.replace("$CONFIG_FILE", self.target_config.config_file)
                        action_needed = action_needed.replace("$CLUSTER_NAME", self.base_config.config_file)
                        actions_needed.add(action_needed)

                rows.append([section, change.param_key, change.old_value, change.new_value, check_result.value, reason])

        return patch_allowed, rows, actions_needed
