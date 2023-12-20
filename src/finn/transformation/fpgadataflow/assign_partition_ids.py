from qonnx.custom_op.registry import getCustomOp
from qonnx.transformation.base import Transformation

from finnexperimental.analysis.partitioning import partition

class AssignPartitionIDs(Transformation):
    def __init__(self, target_clk_ns, target_platform, ndevices):
        self.target_clk_ns = target_clk_ns
        self.target_platform = target_platform
        self.ndevices = ndevices

    def apply(self, model):
        # floorplans = partition(
        #     model,
        #     self.target_clk_ns,
        #     self.target_platform,
        #     self.ndevices,
        #     # TODO: Remove this after testing
        #     abs_anchors=[(0, [1]), (1, [4])]
        # )

        # if floorplans is None:
        #     raise Exception("Partitioning failed")

        # floorplan = floorplans[0]

        model.set_metadata_prop("worldSize", str(self.ndevices))

        for i, node in enumerate(model.graph.node):
            node_inst = getCustomOp(node)
            node_inst.set_nodeattr("device_id", 0 if i < 2 else 1)

        return model, False

