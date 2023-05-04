/******************************************************************************
 * Copyright (C) 2022, Advanced Micro Devices, Inc.
 * All rights reserved.
 *
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted provided that the following conditions are met:
 *
 *  1. Redistributions of source code must retain the above copyright notice,
 *     this list of conditions and the following disclaimer.
 *
 *  2. Redistributions in binary form must reproduce the above copyright
 *     notice, this list of conditions and the following disclaimer in the
 *     documentation and/or other materials provided with the distribution.
 *
 *  3. Neither the name of the copyright holder nor the names of its
 *     contributors may be used to endorse or promote products derived from
 *     this software without specific prior written permission.
 *
 * THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
 * AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO,
 * THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR
 * PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR
 * CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL,
 * EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
 * PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS;
 * OR BUSINESS INTERRUPTION). HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY,
 * WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR
 * OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF
 * ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
 *
 * @brief	All-AXI interface adapter for thresholding module.
 * @author	Thomas B. Preußer <tpreusse@amd.com>
 *
 * @description
 *	This AXI adapter fits the core thresholding functionality:
 *	- with AXI stream data interfaces with flow control
 *	- with implicit round-robin channel rotation as used by FINN, and
 *	- performs aligned byte address to parameter word address translation.
 *****************************************************************************/

module thresholding_axi #(
	int unsigned  N =  4,	// output precision
	int unsigned  K = 16,	// input/threshold precision
	int unsigned  C = 1,	// Channels
	int unsigned  PE = 1,	// Processing Parallelism, requires C = k*PE

	bit  SIGNED = 1,	// signed inputs
	bit  FPARG  = 0,	// floating-point inputs: [sign] | exponent | mantissa
	int  BIAS   = 0,	// offsetting the output [0, 2^N-1] -> [BIAS, 2^N-1 + BIAS]

	localparam int unsigned  CF = C/PE,	// Channel Fold
	localparam int unsigned  ADDR_BITS = $clog2(CF) + $clog2(PE) + N + 2,
	localparam int unsigned  O_BITS = BIAS >= 0?
		/* unsigned */ $clog2(2**N+BIAS) :
		/* signed */ 1+$clog2(-BIAS >= 2**(N-1)? -BIAS : 2**N+BIAS)
)(
	//- Global Control ------------------
	input	logic  ap_clk,
	input	logic  ap_rst_n,

	//- AXI Lite ------------------------
	// Writing
	input	logic                  s_axilite_AWVALID,
	output	logic                  s_axilite_AWREADY,
	input	logic [ADDR_BITS-1:0]  s_axilite_AWADDR,	// lowest 2 bits (byte selectors) are ignored

	input	logic         s_axilite_WVALID,
	output	logic         s_axilite_WREADY,
	input	logic [31:0]  s_axilite_WDATA,
	input	logic [ 3:0]  s_axilite_WSTRB,

	output	logic        s_axilite_BVALID,
	input	logic        s_axilite_BREADY,
	output	logic [1:0]  s_axilite_BRESP,

	// Reading
	input	logic                  s_axilite_ARVALID,
	output	logic                  s_axilite_ARREADY,
	input	logic [ADDR_BITS-1:0]  s_axilite_ARADDR,

	output	logic         s_axilite_RVALID,
	input	logic         s_axilite_RREADY,
	output	logic [31:0]  s_axilite_RDATA,
	output	logic [ 1:0]  s_axilite_RRESP,

	//- AXI Stream - Input --------------
	output	logic  s_axis_tready,
	input	logic  s_axis_tvalid,
	input	logic [((PE*K+7)/8)*8-1:0]  s_axis_tdata,

	//- AXI Stream - Output -------------
	input	logic  m_axis_tready,
	output	logic  m_axis_tvalid,
	output	logic [((PE*O_BITS+7)/8)*8-1:0]  m_axis_tdata
);

	//-----------------------------------------------------------------------
	// AXI-lite Configuration Interface
	uwire  cfg_en;
	uwire  cfg_we;
	uwire [ADDR_BITS-1:0]  cfg_a;
	uwire [K        -1:0]  cfg_d;
	uwire  cfg_rack;
	uwire [K        -1:0]  cfg_q;
	axi4lite_if #(.ADDR_WIDTH(ADDR_BITS), .DATA_WIDTH(32), .IP_DATA_WIDTH(K)) axi (
		.aclk(ap_clk), .aresetn(ap_rst_n),

		.awready(s_axilite_AWREADY), .awvalid(s_axilite_AWVALID), .awaddr(s_axilite_AWADDR), .awprot('x),
		.wready(s_axilite_WREADY),   .wvalid(s_axilite_WVALID),   .wdata(s_axilite_WDATA),   .wstrb(s_axilite_WSTRB),
		.bready(s_axilite_BREADY),   .bvalid(s_axilite_BVALID),   .bresp(s_axilite_BRESP),

		.arready(s_axilite_ARREADY), .arvalid(s_axilite_ARVALID), .araddr(s_axilite_ARADDR), .arprot('x),
		.rready(s_axilite_RREADY),   .rvalid(s_axilite_RVALID),   .rresp(s_axilite_RRESP),   .rdata(s_axilite_RDATA),

		.ip_en(cfg_en), .ip_wen(cfg_we), .ip_addr(cfg_a), .ip_wdata(cfg_d),
		.ip_rack(cfg_rack), .ip_rdata(cfg_q)
	);

	//-----------------------------------------------------------------------
	// Kernel Implementation
	thresholding #(.N(N), .K(K), .C(C), .PE(PE), .SIGNED(SIGNED), .FPARG(FPARG), .BIAS(BIAS)) impl (
		.clk(ap_clk), .rst(!ap_rst_n),

		.cfg_en, .cfg_we, .cfg_a, .cfg_d,
		.cfg_rack, .cfg_q,

		.irdy(s_axis_tready), .ivld(s_axis_tvalid), .idat(s_axis_tdata),
		.ordy(m_axis_tready), .ovld(m_axis_tvalid), .odat(m_axis_tdata)
	);

endmodule : thresholding_axi
