# Copyright (c) 2020, Xilinx
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# * Redistributions of source code must retain the above copyright notice, this
#   list of conditions and the following disclaimer.
#
# * Redistributions in binary form must reproduce the above copyright notice,
#   this list of conditions and the following disclaimer in the documentation
#   and/or other materials provided with the distribution.
#
# * Neither the name of FINN nor the names of its
#   contributors may be used to endorse or promote products derived from
#   this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

import math
import numpy as np
import warnings
from qonnx.core.datatype import DataType

from finn.custom_op.fpgadataflow.hlscustomop import HLSCustomOp

from IPython.core.debugger import set_trace

import subprocess
import os

class ACCLOp(HLSCustomOp):
    def get_nodeattr_types(self):
        my_attrs = {
            "NumChannels": ("i", True, 0),
            # FINN input datatype
            "dataType": ("s", True, ""),
            # utilized width of accl words
            "intfWidth": ("i", False, 32),
            # Width of input or output stream
            "streamWidth": ("i", False, 32),
            # shape describing input vecs per execution
            "numInputVectors": ("ints", False, [1]),
            # accl specific attrs
            "startPort": ("i", False, 5500),
            "rank": ("i", True, 0),
            "worldSize": ("i", True, 0),
            "otherRank": ("i", True, 0),
        }
        my_attrs.update(super().get_nodeattr_types())
        return my_attrs

    def get_normal_input_shape(self, ind=0):
        vecs = list(self.get_nodeattr("numInputVectors"))
        num_ch = self.get_nodeattr("NumChannels")
        ishape = tuple(vecs + [num_ch])
        return ishape

    def get_normal_output_shape(self, ind=0):
        return self.get_normal_input_shape()

    def compile_singlenode_code(self):
        code_gen_dir = self.get_nodeattr("code_gen_dir_cppsim")
        subprocess.run(["/usr/bin/cmake", f"{os.environ['FINN_ROOT']}/ACCL/test/model/bfm"],
            cwd=code_gen_dir)
        subprocess.run(["make"], cwd=code_gen_dir)
    
        self.set_nodeattr("executable_path", code_gen_dir + "/bin/node_model")

    def get_number_output_values(self):
        oshape = self.get_normal_output_shape()
        itype_bits = self.get_input_datatype().bitwidth()
        stream_width = self.get_nodeattr("streamWidth")
        nelems = np.prod(oshape)
        nbits = nelems * itype_bits
        assert (
            nbits % stream_width == 0
        ), "DMA: total transfer size must be word multiple"
        ovalues = nbits // stream_width
        return ovalues

    def make_shape_compatible_op(self, model):
        exp_ishape = self.get_normal_input_shape()
        oshape = self.get_normal_output_shape()
        ishape = tuple(model.get_tensor_shape(self.onnx_node.input[0]))
        assert ishape == exp_ishape, "Unexpected input shape."
        return super().make_const_shape_op(oshape)

    def infer_node_datatype(self, model):
        node = self.onnx_node
        idt = model.get_tensor_datatype(node.input[0])
        if idt != self.get_input_datatype():
            warn_str = "inputDataType changing for %s: %s -> %s " % (
                node.name,
                str(self.get_input_datatype()),
                str(idt),
            )
            warnings.warn(warn_str)
        self.set_nodeattr("dataType", idt.name)
        model.set_tensor_datatype(node.output[0], idt)

    def get_input_datatype(self, ind=0):
        """Returns FINN DataType of input."""
        return DataType[self.get_nodeattr("dataType")]

    def get_output_datatype(self, ind=0):
        """Returns FINN DataType of output. (Same as input datatype)"""
        return self.get_input_datatype()


    def global_includes(self):
        self.code_gen_dict["$GLOBALS$"] = [
            '#include <accl_hls.h>',
            '#include "cclo_bfm.h"',
            '#include "accl_funcs.hpp"',
        ]

    def pragmas(self):
        self.code_gen_dict["$PRAGMAS$"] = [
            '#pragma HLS INTERFACE axis port=cmd_to_cclo',
            '#pragma HLS INTERFACE axis port=sts_from_cclo',
            '#pragma HLS INTERFACE axis port=data_to_cclo',
            '#pragma HLS INTERFACE axis port=data_from_cclo',
            '#pragma HLS INTERFACE axis port=stream',
        ]

    def strm_decl(self):
        start_port = self.get_nodeattr("startPort")
        rank = self.get_nodeattr("rank")
        world_size = self.get_nodeattr("worldSize")
        dest = self.get_nodeattr("worldSize")

        self.code_gen_dict["$STREAMDECLARATIONS$"] = [
            'hlslib::Stream<command_word> cmd_to_cclo("cmd_to_cclo"), sts_from_cclo("sts_from_cclo");',
            'hlslib::Stream<stream_word, 512> data_from_cclo("data_from_cclo"), data_to_cclo("data_to_cclo");',
            'hls::stream<ap_uint<{}>> stream;'.format(self.get_nodeattr("streamWidth")),
            'std::vector<unsigned int> dest{9};',
            'CCLO_BFM cclo({}, {}, {}, dest, cmd_to_cclo, sts_from_cclo, data_from_cclo, data_to_cclo); cclo.run();'.format(start_port, rank, world_size, dest),
        ]

    def defines(self, mode):
        self.code_gen_dict["$DEFINES$"] = ['']

    def verify_node(self):
        ...

class ACCLOut(ACCLOp):
    def get_instream_width(self, ind=0):
        return self.get_nodeattr("streamWidth")

    def get_outstream_width(self, ind=0):
        return self.get_nodeattr("intfWidth")

    def get_folded_output_shape(self, ind=0):
        shape = list(self.get_normal_output_shape())
        itype_bits = self.get_output_datatype().bitwidth()
        intfw = self.get_nodeattr("streamWidth")
        assert (
            intfw % itype_bits == 0
        ), "Input stream width must be a multiple of datatype bits"
        elems_per_word = intfw // itype_bits
        assert shape[-1] % elems_per_word == 0, "Fold depth must be integer"
        fold_depth = shape[-1] // elems_per_word
        shape[-1] = fold_depth
        shape.append(elems_per_word)
        return tuple(shape)

    def docompute(self):
        intf_width = self.get_nodeattr("intfWidth")
        stream_width = self.get_nodeattr("streamWidth")
        fold = self.get_folded_output_shape()[-1]

        self.code_gen_dict["$DOCOMPUTE$"] = [
            'accl_out<{}, {}, {}>({}, {}, {}, cmd_to_cclo, sts_from_cclo, data_to_cclo, data_from_cclo, stream);'.format(intf_width, stream_width, fold, 0, 0, 0)
        ]

    def execute_node(self, context, graph):
        mode = self.get_nodeattr("exec_mode")
        node = self.onnx_node

        if mode != "cppsim":
            raise Exception(
                """Invalid value for attribute exec_mode! Is currently set to: {}
            has to be set to one of the following value ("cppsim")""".format(
                    mode
                )
            )

        code_gen_dir = self.get_nodeattr("code_gen_dir_cppsim")

        assert (
            str(context[node.input[0]].dtype) == "float32"
        ), """Input datatype is
        not float32 as expected."""
        expected_inp_shape = self.get_folded_output_shape()
        expected_inp_shape = (*expected_inp_shape[:-1], expected_inp_shape[-1] * self.get_input_datatype().bitwidth())

        reshaped_input = context[node.input[0]].reshape(expected_inp_shape)
        if self.get_input_datatype() == DataType["BIPOLAR"]:
            # store bipolar activations as binary
            reshaped_input = (reshaped_input + 1) / 2
            export_idt = DataType["BINARY"]
        else:
            export_idt = self.get_input_datatype()
        # make copy before saving the array
        reshaped_input = reshaped_input.copy()
        np.save(
            os.path.join(code_gen_dir, "input.npy"),
            reshaped_input,
        )

        super().exec_precompiled_singlenode_model()

    def read_npy_data(self):
        code_gen_dir = self.get_nodeattr("code_gen_dir_cppsim")
        dtype = self.get_input_datatype()
        elem_bits = dtype.bitwidth()
        packed_bits = self.get_instream_width()
        packed_hls_type = "ap_uint<%d>" % packed_bits
        elem_hls_type = dtype.get_hls_datatype_str()
        npy_type = "float"
        npy_in = "%s/input.npy" % code_gen_dir
        self.code_gen_dict["$READNPYDATA$"] = []
        # note: the innermost dim is reversed for the input
        self.code_gen_dict["$READNPYDATA$"].append(
            'npy2apintstream<%s, %s, %d, %s>("%s", stream, false);'
            % (packed_hls_type, elem_hls_type, elem_bits, npy_type, npy_in)
        )

    def save_as_npy(self):
        self.code_gen_dict["$SAVEASCNPY$"] = []

    def dataoutstrm(self):
        self.code_gen_dict["$DATAOUTSTREAM$"] = ['']

    def blackboxfunction(self):
        pass

class ACCLIn(ACCLOp):
    def get_instream_width(self, ind=0):
        return self.get_nodeattr("intfWidth")

    def get_outstream_width(self, ind=0):
        return self.get_nodeattr("streamWidth")

    def get_folded_input_shape(self, ind=0):
        shape = list(self.get_normal_input_shape())
        itype_bits = self.get_input_datatype().bitwidth()
        intfw = self.get_nodeattr("streamWidth")
        assert (
            intfw % itype_bits == 0
        ), "Input stream width must be a multiple of datatype bits"
        elems_per_word = intfw // itype_bits
        assert shape[-1] % elems_per_word == 0, "Fold depth must be integer"
        fold_depth = shape[-1] // elems_per_word
        shape[-1] = fold_depth
        shape.append(elems_per_word)
        return tuple(shape)

    def docompute(self):
        intf_width = self.get_nodeattr("intfWidth")
        stream_width = self.get_nodeattr("streamWidth")
        fold = self.get_folded_input_shape()[-1]

        self.code_gen_dict["$DOCOMPUTE$"] = [
            'accl_in<{}, {}, {}>({}, {}, {}, cmd_to_cclo, sts_from_cclo, data_to_cclo, data_from_cclo, stream);'.format(intf_width, stream_width, fold, 0, 0, 0)
        ]

    def execute_node(self, context, graph):
        mode = self.get_nodeattr("exec_mode")

        if mode != "cppsim":
            raise Exception(
                """Invalid value for attribute exec_mode! Is currently set to: {}
            has to be set to one of the following value ("cppsim")""".format(
                    mode
                )
            )

        code_gen_dir = self.get_nodeattr("code_gen_dir_cppsim")

        super().exec_precompiled_singlenode_model()
        super().npy_to_dynamic_output(context)

        if self.get_output_datatype() == DataType["BIPOLAR"]:
            out = context[node.output[0]]
            out = 2 * out - 1
            context[node.output[0]] = out
        oshape = self.get_normal_output_shape()

        assert (
            context[node.output[0]].shape == oshape
        ), """Output shape is not as expected"""

    def read_npy_data(self):
        self.code_gen_dict["$READNPYDATA$"] = ['']

    def save_as_npy(self):
        self.code_gen_dict["$SAVEASCNPY$"] = ['']

    def dataoutstrm(self):
        code_gen_dir = self.get_nodeattr("code_gen_dir_cppsim")
        dtype = self.get_output_datatype()
        if dtype == DataType["BIPOLAR"]:
            # use binary for bipolar storage
            dtype = DataType["BINARY"]
        elem_bits = dtype.bitwidth()
        packed_bits = self.get_outstream_width()
        packed_hls_type = "ap_uint<%d>" % packed_bits
        elem_hls_type = dtype.get_hls_datatype_str()
        npy_type = "float"
        npy_out = "%s/output.npy" % code_gen_dir
        shape = self.get_folded_input_shape()
        shape_cpp_str = str(shape).replace("(", "{").replace(")", "}")

        self.code_gen_dict["$DATAOUTSTREAM$"] = [
            'apintstream2npy<%s, %s, %d, %s>(stream, %s, "%s", false);'
            % (
                packed_hls_type,
                elem_hls_type,
                elem_bits,
                npy_type,
                shape_cpp_str,
                npy_out,
            )
        ]

    def blackboxfunction(self):
        pass

