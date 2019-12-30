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
import pytest

from pcluster.config.pcluster_config import PclusterConfig


def test_update_sections(pcluster_config_reader):
    pcluster_config = PclusterConfig(
        cluster_label="default", config_file=pcluster_config_reader(), fail_on_file_absence=True, fail_on_error=True,
    )

    ebs1 = pcluster_config.get_section("ebs", "ebs1")
    assert ebs1
    assert ebs1.get_param_value("shared_dir") == "ebs1"
    assert pcluster_config.get_section("cluster").get_param_value("ebs_settings") == "ebs1,ebs2"

    # Test section re-labelling
    ebs1.label = "ebs1_updated"
    assert pcluster_config.get_section("ebs", "ebs1") is None
    ebs1_updated = pcluster_config.get_section("ebs", "ebs1_updated")
    assert ebs1_updated
    assert ebs1_updated.get_param_value("shared_dir") == "ebs1"
    assert pcluster_config.get_section("cluster").get_param_value("ebs_settings") == "ebs1_updated,ebs2"

    # Test removing section
    ebs2 = pcluster_config.get_section("ebs", "ebs2")
    pcluster_config.remove_section(ebs2.key, ebs2.label)
    assert pcluster_config.get_section("cluster").get_param_value("ebs_settings") == "ebs1_updated"

    # Test adding section
    pcluster_config.add_section(ebs2)
    assert pcluster_config.get_section("cluster").get_param_value("ebs_settings") == "ebs1_updated,ebs2"

    # Test removing multiple sections by key
    with pytest.raises(Exception):
        pcluster_config.remove_section("ebs")
