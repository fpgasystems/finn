# flake8: noqa
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

# template for single node execution
from typing import Dict, List

docompute_template = """
#define AP_INT_MAX_W $AP_INT_MAX_W$
#include "cnpy.h"
#include "npy2apintstream.hpp"
#include <vector>
#include "bnn-library.h"

// includes for network parameters
$GLOBALS$

// defines for network parameters
$DEFINES$

int main(){
$PRAGMAS$

$STREAMDECLARATIONS$

$READNPYDATA$

$DOCOMPUTE$

$DATAOUTSTREAM$

$SAVEASCNPY$

}

"""

# templates for single node ip generation

# cpp file
ipgen_template = """
#define AP_INT_MAX_W $AP_INT_MAX_W$

#include "bnn-library.h"

// includes for network parameters
$GLOBALS$

// defines for network parameters
$DEFINES$

$BLACKBOXFUNCTION$
{
$PRAGMAS$
$DOCOMPUTE$
}
"""

# tcl script for IP generation
ipgentcl_template = """
set config_proj_name $PROJECTNAME$
puts "HLS project: $config_proj_name"
set config_hwsrcdir "$HWSRCDIR$"
puts "HW source dir: $config_hwsrcdir"
set config_proj_part "$FPGAPART$"
set config_bnnlibdir "$::env(FINN_ROOT)/deps/finn-hlslib"
puts "finn-hlslib dir: $config_bnnlibdir"
set config_customhlsdir "$::env(FINN_ROOT)/custom_hls"
puts "custom HLS dir: $config_customhlsdir"
set config_acclhlsdir "$::env(ACCL_ROOT)/driver/hls"
puts "ACCL HLS dir: $config_acclhlsdir"
set config_toplevelfxn "$TOPFXN$"
set config_clkperiod $CLKPERIOD$

open_project $config_proj_name
add_files $config_hwsrcdir/top_$TOPFXN$.cpp -cflags "-std=c++14 -I$config_bnnlibdir -I$config_customhlsdir -I$config_acclhlsdir"

set_top $config_toplevelfxn
open_solution sol1
set_part $config_proj_part

$DEFAULT_DIRECTIVES$
$EXTRA_DIRECTIVES$

create_clock -period $config_clkperiod -name default
csynth_design
export_design -format ip_catalog
exit 0
"""

ip_package_tcl = """
## IP Info
set Vendor      "xilinx.com"
set Library     "hls"
set IPName      "$TOPNAME$"
set Version     "1.0"
set DisplayName "$TOPNAME$"
set Description "An IP generated by Xilinx FINN"
set Device      "zynq"
set Catalog     "/UserIP"
set RootDir     "$VERILOG_DIR$"

## Variables
set Top "$TOPNAME$"
set VerilogFiles [glob -nocomplain $RootDir/*]


## Enter IP directory
cd [file dir [info script]]

## Generate sub cores
set IPs ""
set IPFiles ""

## Basic info
set core [ipx::create_core $Vendor $Library $IPName $Version]
set_property display_name $DisplayName $core
set_property description $Description $core
set_property taxonomy $Catalog $core
set_property supported_families { \
  artix7 Production \
  artix7l Production \
  kintex7 Production \
  kintex7l Production \
  kintexu Production \
  kintexuplus Production \
  versal Production \
  versalprime Production \
  virtex7 Production \
  virtexu Production \
  virtexuplus Production \
  virtexuplusHBM Production \
  zynq Production \
  zynquplus Production \
  aartix7 Production \
  azynq Production \
  qartix7 Production \
  qkintex7 Production \
  qkintex7l Production \
  qvirtex7 Production \
  qzynq Production \
} $core;

## Add verilog files
if {[llength $VerilogFiles] > 0} {
    # synthesis
    set group [ipx::add_file_group xilinx_verilogsynthesis $core]
    foreach f [concat $VerilogFiles $IPFiles] {
        set current_file [ipx::add_file $f $group]
        if {[file ext $f] == ".dat"} {
            set_property type "mif" $current_file
        }
    }
    set_property model_name $Top $group
    if {$IPs != ""} {
        set_property component_subcores $IPs $group
    }

    # simulation
    set group [ipx::add_file_group xilinx_verilogbehavioralsimulation $core]
    foreach f [concat $VerilogFiles $IPFiles] {
        set current_file [ipx::add_file $f $group]
        if {[file ext $f] == ".dat"} {
            set_property type "mif" $current_file
        }
    }
    set_property model_name $Top $group
    if {$IPs != ""} {
        set_property component_subcores $IPs $group
    }
}

## Import ports
ipx::add_ports_from_hdl \
    -top_level_hdl_file $RootDir/$Top.v \
    -top_module_name $Top \
    $core

## Infer interfaces
ipx::infer_bus_interface ap_clk xilinx.com:signal:clock_rtl:1.0 [ipx::current_core]
ipx::infer_bus_interface ap_rst_n xilinx.com:signal:reset_rtl:1.0 [ipx::current_core]
ipx::infer_bus_interface {in0_$HLS_SNAME$_TDATA in0_$HLS_SNAME$_TVALID in0_$HLS_SNAME$_TREADY} xilinx.com:interface:axis_rtl:1.0 [ipx::current_core]
ipx::infer_bus_interface {out_$HLS_SNAME$_TREADY out_$HLS_SNAME$_TDATA out_$HLS_SNAME$_TVALID} xilinx.com:interface:axis_rtl:1.0 [ipx::current_core]
ipx::associate_bus_interfaces -busif in0_$HLS_SNAME$ -clock ap_clk [ipx::current_core]
ipx::associate_bus_interfaces -busif out_$HLS_SNAME$ -clock ap_clk [ipx::current_core]

## Finalize
set_property core_revision 2 [ipx::current_core]
ipx::create_xgui_files [ipx::current_core]
ipx::update_checksums [ipx::current_core]
ipx::save_core [ipx::current_core]
ipx::archive_core $Top.zip [ipx::current_core]
"""

strm_fifo_wrapper = """
module $TOPNAME$(
ap_clk,
ap_rst_n,
count,
maxcount,
in0_$HLS_SNAME$_TDATA,
in0_$HLS_SNAME$_TVALID,
in0_$HLS_SNAME$_TREADY,
out_$HLS_SNAME$_TDATA,
out_$HLS_SNAME$_TVALID,
out_$HLS_SNAME$_TREADY
);

input   ap_clk;
input   ap_rst_n;
output $COUNT_RANGE$ count;
output $COUNT_RANGE$ maxcount;
input  $IN_RANGE$ in0_$HLS_SNAME$_TDATA;
input   in0_$HLS_SNAME$_TVALID;
output   in0_$HLS_SNAME$_TREADY;
output  $OUT_RANGE$ out_$HLS_SNAME$_TDATA;
output   out_$HLS_SNAME$_TVALID;
input   out_$HLS_SNAME$_TREADY;

Q_srl #(
.depth($DEPTH$),
.width($WIDTH$)
)
$LAYER_NAME$
(
 .clock(ap_clk),
 .reset(!ap_rst_n),
 .count(count),
 .maxcount(maxcount),
 .i_d(in0_$HLS_SNAME$_TDATA),
 .i_v(in0_$HLS_SNAME$_TVALID),
 .i_r(in0_$HLS_SNAME$_TREADY),
 .o_d(out_$HLS_SNAME$_TDATA),
 .o_v(out_$HLS_SNAME$_TVALID),
 .o_r(out_$HLS_SNAME$_TREADY)
);

endmodule
"""
