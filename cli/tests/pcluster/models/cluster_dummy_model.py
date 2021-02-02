# Copyright 2021 Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"). You may not use this file except in compliance
# with the License. A copy of the License is located at
#
# http://aws.amazon.com/apache2.0/
#
# or in the "LICENSE.txt" file accompanying this file. This file is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES
# OR CONDITIONS OF ANY KIND, express or implied. See the License for the specific language governing permissions and
# limitations under the License.
from typing import List

from pcluster.models.cluster import HeadNode, HeadNodeNetworking, Image, QueueNetworking, SharedFsx, SharedStorage, Ssh
from pcluster.models.cluster_slurm import SlurmCluster, SlurmComputeResource, SlurmQueue, SlurmScheduling


def dummy_head_node():
    """Generate dummy head node."""
    image = Image(os="fakeos")
    head_node_networking = HeadNodeNetworking(subnet_id="test-subnet")
    ssh = Ssh(key_name="test")
    return HeadNode(instance_type="fake", networking=head_node_networking, ssh=ssh, image=image)


def dummy_cluster():
    """Generate dummy cluster."""
    image = Image(os="fakeos")
    head_node = dummy_head_node()
    compute_resources = [SlurmComputeResource(instance_type="test")]
    queue_networking1 = QueueNetworking(subnet_ids=["subnet-1", "subnet-2"], security_groups=["sg-1", "sg-2"])
    queue_networking2 = QueueNetworking(subnet_ids=["subnet-1", "subnet-3"], security_groups=["sg-1", "sg-3"])
    queues = [
        SlurmQueue(name="testQueue1", networking=queue_networking1, compute_resources=compute_resources),
        SlurmQueue(name="testQueue2", networking=queue_networking2, compute_resources=compute_resources),
    ]
    scheduling = SlurmScheduling(queues=queues)
    # shared storage
    shared_storage: List[SharedStorage] = []
    shared_storage.append(dummy_fsx())
    return SlurmCluster(image=image, head_node=head_node, scheduling=scheduling, shared_storage=shared_storage)


def dummy_fsx():
    """Generate dummy fsx."""
    return SharedFsx(
        mount_dir="/shared",
        file_system_id="test-fsx",
        storage_capacity=300,
        deployment_type="SCRATCH_1",
        imported_file_chunk_size=1024,
        export_path="s3://bucket/folder",
        import_path="s3://bucket/folder",
        weekly_maintenance_start_time="1:00:00",
        automatic_backup_retention_days=0,
        copy_tags_to_backups=True,
        daily_automatic_backup_start_time="01:03",
        per_unit_storage_throughput=200,
        backup_id="backup-fedcba98",
        kms_key_id="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
        auto_import_policy="NEW",
        drive_cache_type="READ",
        storage_type="HDD",
    )
